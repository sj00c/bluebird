"""구역별 실행 단계.

z1  collect         : 파일 소스 → 마스킹·익명 ID → collect 번들(outbox)
z2  import-core     : collect 번들 검증 → core DB 적재
z2  publish         : core의 공개 허용분 → publish 번들(outbox). 컬럼 허용목록 고정
z3  import-publish  : publish 번들 검증 → publish DB 스냅샷 교체
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from psycopg.types.json import Jsonb

from . import db
from .bundle import (
    BundleError,
    archive,
    load_private_key,
    load_public_key,
    pending_bundles,
    read_bundle,
    write_bundle,
)
from .collector.sources import ADAPTERS, file_sha256, load_sources

# Z2 → Z3 반출 허용 컬럼. 여기에 없는 컬럼은 공개존으로 나가지 않는다(테스트로 고정).
PUBLISH_COLUMNS: dict[str, tuple[str, ...]] = {
    "source": ("id", "name", "license", "url"),
    "idea": (
        "id", "source_id", "contest_name", "host_org", "year", "award",
        "title", "body", "used_data", "category", "source_url",
    ),
}

AWARD_RECORD_COLUMNS = (
    "idea_id", "source_id", "contest_name", "host_org", "year", "award", "title", "body",
    "used_data", "category", "team_kind", "source_url", "extra",
)


# ---------------------------------------------------------------- z1 collect
def collect(*, config: Path, seed_dir: Path, state_dir: Path, outbox: Path, key_path: Path,
            secret_path: Path, force: bool = False) -> list[Path]:
    key = load_private_key(key_path)
    secret = secret_path.read_bytes().strip()
    if len(secret) < 32:
        raise ValueError("anon secret must be at least 32 bytes")
    state_file = state_dir / "collect_state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    out = []
    for spec in load_sources(config, seed_dir):
        if not spec.path.exists():
            print(f"[collect] skip {spec.id}: {spec.path} not found", file=sys.stderr)
            continue
        digest = file_sha256(spec.path)
        if not force and state.get(spec.id) == digest:
            print(f"[collect] {spec.id}: unchanged")
            continue
        rows = ADAPTERS[spec.adapter](spec, secret)
        path = write_bundle(
            outbox, zone="z1", kind="collect", source=spec.id, key=key,
            tables={"source": [spec.meta_row()], "award_record": rows},
            meta={"file_sha256": digest},
        )
        state[spec.id] = digest
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2))
        print(f"[collect] {spec.id}: {path.name}")
        out.append(path)
    return out


# ---------------------------------------------------------------- z2 import-core
def _contest_id(source_id: str, name: str, host_org: str, year: int | None) -> str:
    h = hashlib.sha256(f"{source_id}\x1f{name}\x1f{host_org}\x1f{year}".encode()).hexdigest()
    return f"C-{h[:10]}"


def _validate_award_record(r: dict) -> None:
    if set(r) != set(AWARD_RECORD_COLUMNS):
        raise BundleError(f"award_record columns mismatch: {sorted(set(r) ^ set(AWARD_RECORD_COLUMNS))}")
    if not r["title"]:
        raise BundleError(f"empty title for {r['idea_id']}")


def _apply_collect(conn, bundle) -> dict:
    m = bundle.manifest
    if conn.execute("SELECT 1 FROM core.bundle_log WHERE bundle_id=%s", (bundle.bundle_id,)).fetchone():
        return {"skipped": "already applied"}
    conn.execute(
        "INSERT INTO core.bundle_log (bundle_id, zone, kind, source, created_at) VALUES (%s,%s,%s,%s,%s)",
        (bundle.bundle_id, m["zone"], m["kind"], m["source"], m["created_at"]),
    )
    for s in bundle.rows("source"):
        if s["id"] != m["source"]:
            raise BundleError(f"source row {s['id']} does not match manifest source {m['source']}")
        conn.execute(
            """INSERT INTO core.source (id, name, license, url, layer, public_ok) VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, license=EXCLUDED.license, url=EXCLUDED.url,
                 layer=EXCLUDED.layer, public_ok=EXCLUDED.public_ok, updated_at=now()""",
            (s["id"], s["name"], s["license"], s["url"], s["layer"], s["public_ok"]),
        )

    conn.execute(
        """CREATE TEMP TABLE stage_idea (
             id text, source_id text, contest_id text, contest_name text, host_org text, year smallint,
             award text, title text, body text, used_data text[], category text, team_kind text,
             source_url text, extra jsonb) ON COMMIT DROP"""
    )
    n = 0
    with conn.cursor().copy(
        "COPY stage_idea (id, source_id, contest_id, contest_name, host_org, year, award, title, body,"
        " used_data, category, team_kind, source_url, extra) FROM STDIN"
    ) as cp:
        for r in bundle.rows("award_record"):
            _validate_award_record(r)
            if r["source_id"] != m["source"]:
                raise BundleError(f"row source {r['source_id']} != manifest source {m['source']}")
            cid = _contest_id(r["source_id"], r["contest_name"], r["host_org"], r["year"])
            cp.write_row((
                r["idea_id"], r["source_id"], cid, r["contest_name"], r["host_org"], r["year"], r["award"],
                r["title"], r["body"], r["used_data"], r["category"], r["team_kind"], r["source_url"],
                Jsonb(r["extra"]),
            ))
            n += 1
    dup = conn.execute("SELECT count(*) - count(DISTINCT id) FROM stage_idea").fetchone()[0]
    if dup:
        raise BundleError(f"{dup} duplicate idea ids in bundle")
    conn.execute(
        """INSERT INTO core.contest (id, source_id, name, host_org, year)
           SELECT DISTINCT contest_id, source_id, contest_name, host_org, year FROM stage_idea
           ON CONFLICT (id) DO NOTHING"""
    )
    res = conn.execute(
        """INSERT INTO core.idea (id, source_id, contest_id, year, award, title, body, used_data, category,
                                  team_kind, source_url, extra, first_bundle_id, last_bundle_id)
           SELECT id, source_id, contest_id, year, award, title, body, used_data, category, team_kind,
                  source_url, extra, %(b)s, %(b)s FROM stage_idea
           ON CONFLICT (id) DO UPDATE SET contest_id=EXCLUDED.contest_id, year=EXCLUDED.year,
             award=EXCLUDED.award, title=EXCLUDED.title, body=EXCLUDED.body, used_data=EXCLUDED.used_data,
             category=EXCLUDED.category, team_kind=EXCLUDED.team_kind, source_url=EXCLUDED.source_url,
             extra=EXCLUDED.extra, last_bundle_id=EXCLUDED.last_bundle_id, updated_at=now()
           RETURNING (xmax = 0) AS inserted""",
        {"b": bundle.bundle_id},
    ).fetchall()
    inserted = sum(1 for r in res if r[0])
    stats = {"rows": n, "inserted": inserted, "updated": n - inserted}
    conn.execute("UPDATE core.bundle_log SET stats=%s WHERE bundle_id=%s", (Jsonb(stats), bundle.bundle_id))
    return stats


def _import_dir(*, inbox: Path, done_dir: Path, quarantine_dir: Path, public_key_path: Path,
                expect_zone: str, expect_kind: str, dsn: str, apply) -> list[dict]:
    pub = load_public_key(public_key_path)
    results = []
    for path in pending_bundles(inbox):
        try:
            bundle = read_bundle(path, public_key=pub, expect_zone=expect_zone, expect_kind=expect_kind)
            with db.connect(dsn) as conn:
                stats = apply(conn, bundle)
                conn.commit()
        except BundleError as e:
            archive(path, quarantine_dir)
            print(f"[import] QUARANTINE {path.name}: {e}", file=sys.stderr)
            results.append({"bundle": path.name, "status": "quarantined", "error": str(e)})
            continue
        archive(path, done_dir)
        print(f"[import] {bundle.bundle_id}: {stats}")
        results.append({"bundle": bundle.bundle_id, "status": "ok", **stats})
    return results


class QuarantinedBundlesError(Exception):
    """일부 번들이 격리됨. 정상 번들은 이미 적재됐고, 단계 기록은 failed로 남는다."""

    def __init__(self, results: list[dict]):
        self.results = results
        bad = [r["bundle"] for r in results if r["status"] != "ok"]
        super().__init__(f"{len(bad)} bundle(s) quarantined: {', '.join(bad)}")


def import_core(*, inbox: Path, done_dir: Path, quarantine_dir: Path, public_key_path: Path, dsn: str) -> list[dict]:
    with db.pipeline_run(dsn, "import-core") as stats:
        results = _import_dir(inbox=inbox, done_dir=done_dir, quarantine_dir=quarantine_dir,
                              public_key_path=public_key_path, expect_zone="z1", expect_kind="collect",
                              dsn=dsn, apply=_apply_collect)
        stats["bundles"] = results
        if any(r["status"] != "ok" for r in results):
            raise QuarantinedBundlesError(results)
    return results


# ---------------------------------------------------------------- z2 publish
def publish(*, dsn: str, outbox: Path, key_path: Path) -> Path:
    """공개 허용 소스(public_ok)의 아이디어 풀 스냅샷. 진단·점수는 승인 게이트 구현 후 추가한다."""
    key = load_private_key(key_path)
    with db.pipeline_run(dsn, "publish") as stats, db.connect(dsn) as conn:
        cur = conn.cursor()
        sources = [
            dict(zip(PUBLISH_COLUMNS["source"], r))
            for r in cur.execute("SELECT id, name, license, url FROM core.source WHERE public_ok ORDER BY id")
        ]
        cur.execute(
            """SELECT i.id, i.source_id, c.name, c.host_org, i.year, i.award, i.title, i.body, i.used_data,
                      i.category, i.source_url
               FROM core.idea i JOIN core.contest c ON c.id = i.contest_id
               JOIN core.source s ON s.id = i.source_id
               WHERE s.public_ok ORDER BY i.id"""
        )
        ideas = [dict(zip(PUBLISH_COLUMNS["idea"], r)) for r in cur]
        path = write_bundle(outbox, zone="z2", kind="publish", source="snapshot", key=key,
                            tables={"source": sources, "idea": ideas}, meta={"mode": "full_snapshot"})
        stats.update({"bundle": path.name, "sources": len(sources), "ideas": len(ideas)})
    print(f"[publish] {path.name}: sources={len(sources)} ideas={len(ideas)}")
    return path


# ---------------------------------------------------------------- z3 import-publish
def _apply_publish(conn, bundle) -> dict:
    if bundle.manifest.get("meta", {}).get("mode") != "full_snapshot":
        raise BundleError("publish bundle must be a full_snapshot")
    if set(bundle.tables) != set(PUBLISH_COLUMNS):
        raise BundleError(f"unexpected publish tables {bundle.tables}")
    if conn.execute("SELECT 1 FROM publish.snapshot_log WHERE bundle_id=%s", (bundle.bundle_id,)).fetchone():
        return {"skipped": "already applied"}
    latest = conn.execute("SELECT max(created_at) FROM publish.snapshot_log").fetchone()[0]
    if latest is not None and latest.isoformat() >= bundle.manifest["created_at"]:
        raise BundleError(f"stale snapshot: {bundle.manifest['created_at']} <= applied {latest.isoformat()}")

    conn.execute("TRUNCATE publish.idea, publish.source")
    counts = {}
    for table in ("source", "idea"):
        cols = PUBLISH_COLUMNS[table]
        n = 0
        with conn.cursor().copy(f"COPY publish.{table} ({', '.join(cols)}) FROM STDIN") as cp:
            for r in bundle.rows(table):
                if tuple(r) != cols:
                    raise BundleError(f"publish.{table} columns not in allowlist: {sorted(set(r) ^ set(cols))}")
                cp.write_row(tuple(r[c] for c in cols))
                n += 1
        counts[table] = n
    conn.execute(
        "INSERT INTO publish.snapshot_log (bundle_id, created_at, stats) VALUES (%s,%s,%s)",
        (bundle.bundle_id, bundle.manifest["created_at"], Jsonb(counts)),
    )
    return counts


def import_publish(*, inbox: Path, done_dir: Path, quarantine_dir: Path, public_key_path: Path,
                   dsn: str) -> list[dict]:
    return _import_dir(inbox=inbox, done_dir=done_dir, quarantine_dir=quarantine_dir,
                       public_key_path=public_key_path, expect_zone="z2", expect_kind="publish",
                       dsn=dsn, apply=_apply_publish)
