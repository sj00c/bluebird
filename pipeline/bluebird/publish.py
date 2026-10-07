"""업무망 → DMZ 공개용 DB 한 방향 반영(push). 연결은 항상 업무망(backend-jobs)이 연다.

절차(계획 §3.8)
1. core에서 승인·공개 허용분만 모은다(열 허용목록 = 템플릿).
2. 템플릿 sha256이 meta.publish_template에 등록된 값과 같은지 확인한다(다르면 거부).
3. publish_next 스키마를 템플릿으로 만들고 적재한다(별도 트랜잭션, 무거운 작업).
4. 짧은 트랜잭션: GRANT(portal) → RENAME publish→publish_prev, publish_next→publish → meta.snapshot_log 기록.
5. publish_prev DROP(lock_timeout + 재시도).
"""

from __future__ import annotations

import hashlib
import sys
import time
from importlib import resources

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from . import db

TEMPLATE_VERSION = "v1"
PORTAL_ROLE = "bb_portal"


class PublishError(Exception):
    pass


def template(version: str = TEMPLATE_VERSION) -> tuple[str, str]:
    text = resources.files("bluebird.publish_template").joinpath(f"{version}.sql").read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()


def register_template(migrator_dsn: str, version: str = TEMPLATE_VERSION) -> str:
    """migrator 권한으로 템플릿 버전·체크섬 등록. 같은 버전이 다른 체크섬으로 이미 있으면 실패."""
    _, sha = template(version)
    with db.connect(migrator_dsn) as conn:
        row = conn.execute("SELECT sha256 FROM meta.publish_template WHERE version=%s", (version,)).fetchone()
        if row and row[0] != sha:
            raise PublishError(f"template {version} already registered with different sha256; bump the version")
        if not row:
            conn.execute("INSERT INTO meta.publish_template (version, sha256) VALUES (%s, %s)", (version, sha))
        conn.commit()
    return sha


# ---------------------------------------------------------------- core 쪽 수집
# 각 표: (publish 테이블, 열 목록, core 조회 SQL). 열 목록은 템플릿과 같아야 한다(test_publish가 검사).
QUERIES: dict[str, tuple[tuple[str, ...], str]] = {
    "source": (
        ("id", "name", "license", "url"),
        "SELECT id, name, license, url FROM core.source WHERE public_ok ORDER BY id",
    ),
    "idea": (
        ("id", "source_id", "contest_name", "host_org", "year", "award", "title", "body", "used_data", "category",
         "source_url", "card_kind", "problem", "solution", "trace_status", "external_search"),
        """SELECT i.id, i.source_id, c.name, c.host_org, i.year, i.award, i.title, i.body, i.used_data, i.category,
                  i.source_url, k.card_kind,
                  CASE WHEN pc.target_id IS NOT NULL THEN k.problem END,
                  CASE WHEN pc.target_id IS NOT NULL THEN k.solution END,
                  t.status, t.external_search
             FROM core.idea i
             JOIN core.contest c ON c.id = i.contest_id
             JOIN core.source s ON s.id = i.source_id AND s.public_ok AND i.retired_at IS NULL
             LEFT JOIN core.idea_card k ON k.idea_id = i.id
             LEFT JOIN core.trace_verdict t ON t.idea_id = i.id
             LEFT JOIN core.publication pc ON pc.target_type = 'idea' AND pc.target_id = i.id
                                          AND pc.scope = 'card' AND pc.revoked_at IS NULL
            ORDER BY i.id""",
    ),
    "diagnosis": (
        ("idea_id", "cause", "secondary", "rationale", "evidence_ids"),
        """SELECT d.idea_id, d."primary", d.secondary, d.rationale,
                  ARRAY(SELECT x.evidence_id FROM core.x_evidence x
                         WHERE x.target_type = 'diagnosis' AND x.target_id = d.idea_id ORDER BY 1)
             FROM core.diagnosis d
             JOIN core.idea i ON i.id = d.idea_id AND i.retired_at IS NULL
             JOIN core.source s ON s.id = i.source_id AND s.public_ok
             JOIN core.publication p ON p.target_type = 'idea' AND p.target_id = d.idea_id
                                    AND p.scope = 'diagnosis' AND p.revoked_at IS NULL
            ORDER BY 1""",
    ),
    "change": (
        ("id", "idea_id", "kind", "tier", "occurred_at", "title", "url", "what_changed", "how_now", "evidence_ids"),
        """SELECT m.id, m.idea_id, c.kind, c.tier, c.occurred_at, c.title, c.url, m.what_changed, m.how_now,
                  ARRAY(SELECT x.evidence_id FROM core.x_evidence x
                         WHERE x.target_type = 'change_match' AND x.target_id = m.id::text ORDER BY 1)
             FROM core.change_match m
             JOIN core.condition_change c ON c.id = m.change_id AND c.kind <> 'announcement'
             JOIN core.idea i ON i.id = m.idea_id AND i.retired_at IS NULL
             JOIN core.source s ON s.id = i.source_id AND s.public_ok
             JOIN core.publication p ON p.target_type = 'change_match' AND p.target_id = m.id::text
                                    AND p.scope = 'change' AND p.revoked_at IS NULL
            WHERE m.status = 'approved'
            ORDER BY 1""",
    ),
    "timeliness": (
        ("idea_id", "as_of", "tech", "data", "regulation", "policy", "n_scored", "s", "verdict", "resolve_condition"),
        """SELECT DISTINCT ON (t.idea_id) t.idea_id, t.as_of, t.tech, t.data, t.regulation, t.policy, t.n_scored,
                  t.s, t.verdict, t.resolve_condition
             FROM core.timeliness t
             JOIN core.idea i ON i.id = t.idea_id AND i.retired_at IS NULL
             JOIN core.source s ON s.id = i.source_id AND s.public_ok
             JOIN core.publication p ON p.target_type = 'idea' AND p.target_id = t.idea_id
                                    AND p.scope = 'timeliness' AND p.revoked_at IS NULL
            WHERE t.verdict IN ('now', 'conditional')
            ORDER BY t.idea_id, t.as_of DESC""",
    ),
    "weekly_top": (
        ("week", "rank", "idea_id", "s"),
        """SELECT w.week, w.rank, w.idea_id, w.s
             FROM core.weekly_top w
             JOIN core.idea i ON i.id = w.idea_id AND i.retired_at IS NULL
             JOIN core.source s ON s.id = i.source_id AND s.public_ok
            WHERE w.week = (SELECT max(week) FROM core.weekly_top)
            ORDER BY w.rank""",
    ),
    "announcement": (
        ("id", "title", "org", "apply_from", "apply_to", "url"),
        """SELECT a.id, a.title, a.org, a.apply_from, a.apply_to, a.url
             FROM core.announcement a
            WHERE EXISTS (SELECT 1 FROM core.change_match m
                            JOIN core.condition_change c ON c.id = m.change_id
                            JOIN core.publication p ON p.target_type = 'change_match' AND p.target_id = m.id::text
                                                   AND p.scope = 'change' AND p.revoked_at IS NULL
                           WHERE c.kind = 'announcement' AND c.ref_id = a.id AND m.status = 'approved')
            ORDER BY a.id""",
    ),
    "announcement_match": (
        ("announcement_id", "idea_id", "rank", "similarity", "how_now"),
        """SELECT c.ref_id, m.idea_id,
                  row_number() OVER (PARTITION BY c.ref_id ORDER BY m.similarity DESC NULLS LAST, m.idea_id),
                  m.similarity, m.how_now
             FROM core.change_match m
             JOIN core.condition_change c ON c.id = m.change_id AND c.kind = 'announcement'
             JOIN core.idea i ON i.id = m.idea_id AND i.retired_at IS NULL
             JOIN core.source s ON s.id = i.source_id AND s.public_ok
             JOIN core.publication p ON p.target_type = 'change_match' AND p.target_id = m.id::text
                                    AND p.scope = 'change' AND p.revoked_at IS NULL
            WHERE m.status = 'approved'""",
    ),
}
# 적재 순서(FK)
ORDER = ("source", "idea", "evidence", "diagnosis", "change", "timeliness", "weekly_top", "announcement",
         "announcement_match")
EVIDENCE_COLUMNS = ("id", "kind", "url", "title", "excerpt", "observed_at")


def collect(core_conn) -> dict[str, list[tuple]]:
    data: dict[str, list[tuple]] = {}
    for table, (_, q) in QUERIES.items():
        data[table] = [tuple(r) for r in core_conn.execute(q)]
    data["announcement_match"] = [r for r in data["announcement_match"] if r[2] <= 5]
    ev_ids = sorted({e for t in ("diagnosis", "change") for r in data[t] for e in r[-1]})
    data["evidence"] = [
        tuple(r) for r in core_conn.execute(
            "SELECT id, kind, url, title, excerpt, observed_at FROM core.evidence WHERE id = ANY(%s) ORDER BY id",
            (ev_ids,),
        )
    ]
    # 공개 이외 근거가 섞이지 않았는지, 비-U 진단·바뀐 것에 근거가 비지 않았는지 반영 전에 막는다(G9).
    for t in ("diagnosis", "change"):
        empty = [r[0] for r in data[t] if not r[-1] and not (t == "diagnosis" and r[1] == "U")]
        if empty:
            raise PublishError(f"{t}: {len(empty)} row(s) without evidence, e.g. {empty[:3]}")
    return data


def columns(table: str) -> tuple[str, ...]:
    return EVIDENCE_COLUMNS if table == "evidence" else QUERIES[table][0]


# ---------------------------------------------------------------- DMZ 쪽 교체
def _drop_prev(conn, attempts: int = 5) -> None:
    for i in range(attempts):
        try:
            conn.execute("SET lock_timeout = '3s'")
            conn.execute("DROP SCHEMA IF EXISTS publish_prev CASCADE")
            conn.commit()
            return
        except psycopg.errors.LockNotAvailable:
            conn.rollback()
            time.sleep(2 ** i)
    print("[publish] publish_prev still locked; will drop on next run", file=sys.stderr)


def push(*, core_dsn: str, publish_dsn: str, version: str = TEMPLATE_VERSION) -> dict:
    text, sha = template(version)
    with db.pipeline_run(core_dsn, "publish") as stats:
        with db.connect(core_dsn) as core:
            data = collect(core)
            counts = {t: len(data[t]) for t in ORDER}
            snap_id = core.execute(
                "INSERT INTO core.publish_snapshot (template_version, template_sha256, rows) VALUES (%s,%s,%s)"
                " RETURNING id",
                (version, sha, Jsonb(counts)),
            ).fetchone()[0]
            core.commit()

        with db.connect(publish_dsn) as pub:
            reg = pub.execute("SELECT sha256 FROM meta.publish_template WHERE version=%s", (version,)).fetchone()
            if not reg or reg[0] != sha:
                raise PublishError(f"template {version} sha256 {sha[:12]} is not the registered one")
            last = pub.execute("SELECT max(snapshot_id) FROM meta.snapshot_log").fetchone()[0]
            if last is not None and snap_id <= last:
                raise PublishError(f"snapshot {snap_id} is not newer than applied {last}")
            _drop_prev(pub)

            # 3. publish_next 생성·적재
            pub.execute("DROP SCHEMA IF EXISTS publish_next CASCADE")
            pub.execute("CREATE SCHEMA publish_next")
            pub.execute("SET LOCAL search_path = publish_next, public")
            pub.execute(text)
            for t in ORDER:
                cols = columns(t)
                with pub.cursor().copy(
                    sql.SQL("COPY publish_next.{} ({}) FROM STDIN").format(
                        sql.Identifier(t), sql.SQL(", ").join(map(sql.Identifier, cols)))
                ) as cp:
                    for r in data[t]:
                        cp.write_row(r)
            pub.commit()

            # 4. 짧은 교체 트랜잭션: GRANT → RENAME → 기록
            pub.execute("SET LOCAL lock_timeout = '5s'")
            pub.execute(sql.SQL("GRANT USAGE ON SCHEMA publish_next TO {}").format(sql.Identifier(PORTAL_ROLE)))
            pub.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA publish_next TO {}").format(
                sql.Identifier(PORTAL_ROLE)))
            if pub.execute("SELECT 1 FROM pg_namespace WHERE nspname='publish'").fetchone():
                pub.execute("ALTER SCHEMA publish RENAME TO publish_prev")
            pub.execute("ALTER SCHEMA publish_next RENAME TO publish")
            pub.execute(
                "INSERT INTO meta.snapshot_log (snapshot_id, template_version, created_at, stats)"
                " VALUES (%s, %s, now(), %s)",
                (snap_id, version, Jsonb(counts)),
            )
            pub.commit()
            _drop_prev(pub)
        stats.update({"snapshot_id": snap_id, **counts})
    print(f"[publish] snapshot {snap_id}: {counts}")
    return {"snapshot_id": snap_id, **counts}
