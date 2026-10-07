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

from . import db, wording

TEMPLATE_VERSION = "v2"
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
# 아이디어 공개(카드·진단·S)가 살아 있음. 반려·철회된 아이디어의 바뀐 것·weekly_top이 남지 않게 한다.
# + 지금도 5단계(승인 + 0–4단계 통과)인 아이디어만(collect가 만드는 pg_temp.stage5).
_IDEA_LIVE = """(SELECT count(DISTINCT pi.scope) FROM core.publication pi
        WHERE pi.target_type = 'idea' AND pi.target_id = {idea} AND pi.revoked_at IS NULL
          AND pi.scope IN ('card', 'diagnosis', 'timeliness')) = 3
        AND {idea} IN (SELECT idea_id FROM pg_temp.stage5)"""
# 매칭 m이 지금도 3단계를 채우고(core.match_eligible), 아이디어 공개가 살아 있음
_LIVE_FIT = ("""core.match_eligible(m.id, coalesce((SELECT max(id) FROM core.catalog_snapshot), -1))
        AND """ + _IDEA_LIVE.format(idea="m.idea_id"))

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
             JOIN core.source s ON s.id = i.source_id AND s.public_ok AND i.retired_at IS NULL AND i.withheld_at IS NULL
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
             JOIN core.idea i ON i.id = d.idea_id AND i.retired_at IS NULL AND i.withheld_at IS NULL
             JOIN core.source s ON s.id = i.source_id AND s.public_ok
             JOIN core.publication p ON p.target_type = 'idea' AND p.target_id = d.idea_id
                                    AND p.scope = 'diagnosis' AND p.revoked_at IS NULL
            WHERE """ + _IDEA_LIVE.format(idea="d.idea_id") + """
            ORDER BY 1""",
    ),
    "change": (
        ("id", "idea_id", "kind", "tier", "occurred_at", "registered_at", "title", "url", "what_changed", "how_now",
         "evidence_ids"),
        """SELECT m.id, m.idea_id, c.kind, c.tier, c.occurred_at,
                  (SELECT sd.registered_at FROM core.signal_dataset sd
                    WHERE c.kind = 'dataset_opened' AND sd.public_data_pk = c.ref_id),
                  c.title, c.url, m.what_changed, m.how_now,
                  ARRAY(SELECT x.evidence_id FROM core.x_evidence x
                         WHERE x.target_type = 'change_match' AND x.target_id = m.id::text ORDER BY 1)
             FROM core.change_match m
             JOIN core.condition_change c ON c.id = m.change_id AND c.kind <> 'announcement'
             JOIN core.idea i ON i.id = m.idea_id AND i.retired_at IS NULL AND i.withheld_at IS NULL
             JOIN core.source s ON s.id = i.source_id AND s.public_ok
             JOIN core.publication p ON p.target_type = 'change_match' AND p.target_id = m.id::text
                                    AND p.scope = 'change' AND p.revoked_at IS NULL
            WHERE m.status = 'approved' AND """ + _LIVE_FIT + """
            ORDER BY 1""",
    ),
    "timeliness": (
        ("idea_id", "as_of", "tech", "data", "regulation", "policy", "n_scored", "s", "verdict", "resolve_condition",
         "evidence_ids"),
        """SELECT DISTINCT ON (t.idea_id) t.idea_id, t.as_of, t.tech, t.data, t.regulation, t.policy, t.n_scored,
                  t.s, t.verdict, t.resolve_condition,
                  ARRAY(SELECT x.evidence_id FROM core.x_evidence x
                         WHERE x.target_type = 'timeliness' AND x.target_id = t.idea_id || '@' || t.as_of::text
                         ORDER BY 1)
             FROM core.timeliness t
             JOIN core.idea i ON i.id = t.idea_id AND i.retired_at IS NULL AND i.withheld_at IS NULL
             JOIN core.source s ON s.id = i.source_id AND s.public_ok
             JOIN core.publication p ON p.target_type = 'idea' AND p.target_id = t.idea_id
                                    AND p.scope = 'timeliness' AND p.revoked_at IS NULL
            WHERE t.verdict IN ('now', 'conditional') AND """ + _IDEA_LIVE.format(idea="t.idea_id") + """
            ORDER BY t.idea_id, t.as_of DESC""",
    ),
    "weekly_top": (
        ("week", "rank", "idea_id", "s"),
        """SELECT w.week, w.rank, w.idea_id, w.s
             FROM core.weekly_top w
             JOIN core.idea i ON i.id = w.idea_id AND i.retired_at IS NULL AND i.withheld_at IS NULL
             JOIN core.source s ON s.id = i.source_id AND s.public_ok
            WHERE w.week = (SELECT max(week) FROM core.weekly_top) AND """ + _IDEA_LIVE.format(idea="w.idea_id") + """
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
                           WHERE c.kind = 'announcement' AND c.ref_id = a.id AND m.status = 'approved'
                             AND """ + _LIVE_FIT + """)
            ORDER BY a.id""",
    ),
    "announcement_match": (
        ("announcement_id", "idea_id", "rank", "similarity", "how_now"),
        """SELECT c.ref_id, m.idea_id,
                  row_number() OVER (PARTITION BY c.ref_id ORDER BY m.similarity DESC NULLS LAST, m.idea_id),
                  m.similarity, m.how_now
             FROM core.change_match m
             JOIN core.condition_change c ON c.id = m.change_id AND c.kind = 'announcement'
             JOIN core.idea i ON i.id = m.idea_id AND i.retired_at IS NULL AND i.withheld_at IS NULL
             JOIN core.source s ON s.id = i.source_id AND s.public_ok
             JOIN core.publication p ON p.target_type = 'change_match' AND p.target_id = m.id::text
                                    AND p.scope = 'change' AND p.revoked_at IS NULL
            WHERE m.status = 'approved' AND """ + _LIVE_FIT,
    ),
}
# 적재 순서(FK)
ORDER = ("source", "idea", "evidence", "diagnosis", "change", "timeliness", "weekly_top", "announcement",
         "announcement_match")
EVIDENCE_COLUMNS = ("id", "kind", "url", "title", "excerpt", "observed_at")


def collect(core_conn) -> dict[str, list[tuple]]:
    # 승인 뒤 단계 조건이 깨지면(확인 안 된 바뀐 것, 미래 시행일, S 낮아짐) 진단·바뀐 것·S·Top은 나가지 않는다.
    core_conn.execute("DROP TABLE IF EXISTS pg_temp.stage5")
    core_conn.execute(
        """CREATE TEMP TABLE stage5 AS SELECT idea_id FROM core.funnel_stage(
             coalesce((SELECT max(id) FROM core.catalog_snapshot), -1)) WHERE s5""")
    data: dict[str, list[tuple]] = {}
    for table, (_, q) in QUERIES.items():
        data[table] = [tuple(r) for r in core_conn.execute(q)]
    data["announcement_match"] = [r for r in data["announcement_match"] if r[2] <= 5]
    ev_ids = sorted({e for t in ("diagnosis", "change", "timeliness") for r in data[t] for e in r[-1]})
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
    # S: 채점한 축 수(n_scored)만큼 근거가 있어야 한다(score_set이 축마다 별도 근거 행을 만든다). 2차 방어선.
    short = [r[0] for r in data["timeliness"] if len(r[-1]) < r[6]]
    if short:
        raise PublishError(f"timeliness: {len(short)} row(s) with fewer evidence than scored axes, e.g. {short[:3]}")
    # 우리가 쓴 글(카드 요약·진단·바뀐 것·S 조건)에 금지 표현이 있으면 반영하지 않는다(원문 인용·제목은 제외).
    for t, cols in OWN_TEXT.items():
        idx = [columns(t).index(c) for c in cols]
        for r in data[t]:
            for i in idx:
                vals = r[i] if isinstance(r[i], list) else [r[i]]
                for v in vals:
                    if hit := wording.find(v if isinstance(v, str) else None):
                        raise PublishError(f"{t}.{columns(t)[i]} of {r[0]}: forbidden wording {hit!r}")
    return data


# 공개되는 우리 글(내부 작성). evidence.excerpt·원문 제목·본문은 인용이라 범위 밖.
OWN_TEXT = {
    "idea": ("problem", "solution"),
    "diagnosis": ("rationale",),
    "change": ("what_changed", "how_now"),
    "timeliness": ("resolve_condition",),
    "announcement_match": ("how_now",),
}


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
        # DMZ 커밋이 끝난 뒤에만 반영 완료로 기록(단계 6은 이 기록과 revived_ids를 본다)
        changed = {r[1] for r in data["change"]} | {r[1] for r in data["announcement_match"]}  # 둘 다 idea_id
        revived = sorted({r[0] for r in data["diagnosis"]} & {r[0] for r in data["timeliness"]} & changed)
        with db.connect(core_dsn) as core:
            core.execute("UPDATE core.publish_snapshot SET applied_at=now(), revived_ids=%s WHERE id=%s",
                         (revived, snap_id))
            core.commit()
        stats.update({"snapshot_id": snap_id, **counts})
    print(f"[publish] snapshot {snap_id}: {counts}")
    return {"snapshot_id": snap_id, **counts}
