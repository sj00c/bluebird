"""원본 적재: seed 파일 → 마스킹·익명 ID → core DB.

소스별 ingest_run을 남기고, 같은 파일(sha256)이 이미 성공 적재됐으면 건너뛴다.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from psycopg.types.json import Jsonb

from . import db
from .sources import ADAPTERS, AWARD_RECORD_COLUMNS, SourceSpec, file_sha256, load_sources


class IngestError(Exception):
    pass


def load_secret(path: Path) -> bytes:
    secret = path.read_bytes().strip()
    if len(secret) < 32:
        raise ValueError("anon secret must be at least 32 bytes")
    return secret


def contest_id(source_id: str, name: str, host_org: str, year: int | None) -> str:
    h = hashlib.sha256(f"{source_id}\x1f{name}\x1f{host_org}\x1f{year}".encode()).hexdigest()
    return f"C-{h[:10]}"


def _validate(r: dict, spec: SourceSpec) -> None:
    if set(r) != set(AWARD_RECORD_COLUMNS):
        raise IngestError(f"award_record columns mismatch: {sorted(set(r) ^ set(AWARD_RECORD_COLUMNS))}")
    if not r["title"]:
        raise IngestError(f"empty title for {r['idea_id']}")
    if r["source_id"] != spec.id:
        raise IngestError(f"row source {r['source_id']} != {spec.id}")


def upsert_source(conn, spec: SourceSpec, body_present: bool | None) -> None:
    conn.execute(
        """INSERT INTO core.source AS existing (id, name, license, url, layer, public_ok, export_grade, body_present,
                                    policy_approved_by, policy_approved_at, record_kind, exclude_reason)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, license=EXCLUDED.license, url=EXCLUDED.url,
             layer=EXCLUDED.layer, public_ok=EXCLUDED.public_ok, export_grade=EXCLUDED.export_grade,
             body_present=COALESCE(%s, existing.body_present), policy_approved_by=EXCLUDED.policy_approved_by,
             policy_approved_at=EXCLUDED.policy_approved_at, record_kind=EXCLUDED.record_kind,
             exclude_reason=EXCLUDED.exclude_reason, updated_at=now()""",
        (spec.id, spec.name, spec.license, spec.url, spec.layer, spec.public_ok, spec.export_grade,
         body_present if body_present is not None else False,
         spec.policy_approved_by, spec.policy_approved_at, spec.record_kind, spec.exclude_reason, body_present),
    )


def classify_contests(conn) -> int:
    """아직 미확인(unknown)인 대회에 이름 근거로 초·중·고 학생 대회 표시를 붙인다. 사람이 고친 값은 건들지 않는다. docs/IDEA_POOL.md"""
    return conn.execute(
        """WITH u AS (UPDATE core.contest SET audience = core.contest_audience(name)
                      WHERE audience = 'unknown' AND core.contest_audience(name) <> 'unknown' RETURNING 1)
           SELECT count(*) FROM u"""
    ).fetchone()[0]


def refresh_markers(conn) -> dict:
    """선별 재료 재계산: 대회 학생 표시 → 같은 제목 묶음 → 제외 후보 이유. 어느 것도 아이디어를 거르지 않는다."""
    classified = classify_contests(conn)
    dups = conn.execute("SELECT core.refresh_idea_dup()").fetchone()[0]
    reasons = conn.execute("SELECT core.refresh_idea_exclusion()").fetchone()[0]
    return {"contests_classified": classified, "dup_rows": dups, "exclusion_rows": reasons}


def _apply(conn, spec: SourceSpec, rows, run_id: int, *, allow_retire: bool = False) -> dict:
    conn.execute(
        """CREATE TEMP TABLE stage_idea (
             id text, source_id text, contest_id text, contest_name text, host_org text, year smallint,
             award text, title text, body text, used_data text[], category text, team_kind text,
             source_url text, extra jsonb) ON COMMIT DROP"""
    )
    n = with_body = 0
    with conn.cursor().copy(
        "COPY stage_idea (id, source_id, contest_id, contest_name, host_org, year, award, title, body,"
        " used_data, category, team_kind, source_url, extra) FROM STDIN"
    ) as cp:
        for r in rows:
            _validate(r, spec)
            cp.write_row((
                r["idea_id"], r["source_id"], contest_id(r["source_id"], r["contest_name"], r["host_org"], r["year"]),
                r["contest_name"], r["host_org"], r["year"], r["award"], r["title"], r["body"], r["used_data"],
                r["category"], r["team_kind"], r["source_url"], Jsonb(r["extra"]),
            ))
            n += 1
            with_body += bool(r["body"])
    dup = conn.execute("SELECT count(*) - count(DISTINCT id) FROM stage_idea").fetchone()[0]
    if dup:
        raise IngestError(f"{dup} duplicate idea ids in {spec.id}")
    upsert_source(conn, spec, body_present=with_body > 0)
    conn.execute(
        """INSERT INTO core.contest (id, source_id, name, host_org, year)
           SELECT DISTINCT contest_id, source_id, contest_name, host_org, year FROM stage_idea
           ON CONFLICT (id) DO NOTHING"""
    )
    res = conn.execute(
        """INSERT INTO core.idea (id, source_id, contest_id, year, award, title, body, used_data, category,
                                  team_kind, source_url, extra, first_ingest_id, last_ingest_id)
           SELECT id, source_id, contest_id, year, award, title, body, used_data, category, team_kind,
                  source_url, extra, %(r)s, %(r)s FROM stage_idea
           ON CONFLICT (id) DO UPDATE SET contest_id=EXCLUDED.contest_id, year=EXCLUDED.year,
             award=EXCLUDED.award, title=EXCLUDED.title, body=EXCLUDED.body, used_data=EXCLUDED.used_data,
             category=EXCLUDED.category, team_kind=EXCLUDED.team_kind, source_url=EXCLUDED.source_url,
             extra=EXCLUDED.extra, last_ingest_id=EXCLUDED.last_ingest_id, retired_at=NULL, updated_at=now()
           RETURNING (xmax = 0) AS inserted""",
        {"r": run_id},
    ).fetchall()
    inserted = sum(1 for r in res if r[0])
    # 이번 파일에 없는 기존 행은 퇴역 처리. 한 번에 절반 넘게 사라지면 파일 이상으로 보고 멈춘다(--allow-retire로만 허용).
    live = conn.execute(
        "SELECT count(*) FROM core.idea WHERE source_id=%s AND retired_at IS NULL", (spec.id,)
    ).fetchone()[0]
    gone = conn.execute(
        "SELECT count(*) FROM core.idea i WHERE i.source_id=%s AND i.retired_at IS NULL"
        " AND NOT EXISTS (SELECT 1 FROM stage_idea s WHERE s.id = i.id)", (spec.id,)
    ).fetchone()[0]
    if gone and gone * 2 > live - inserted and not allow_retire:
        sample = [r[0] for r in conn.execute(
            "SELECT i.id FROM core.idea i WHERE i.source_id=%s AND i.retired_at IS NULL"
            " AND NOT EXISTS (SELECT 1 FROM stage_idea s WHERE s.id = i.id) ORDER BY 1 LIMIT 5", (spec.id,))]
        raise IngestError(f"{spec.id}: {gone}/{live - inserted} ideas would be retired (e.g. {sample}); "
                          "check the file, or pass --allow-retire if the source really dropped them")
    conn.execute(
        "UPDATE core.idea i SET retired_at=now() WHERE i.source_id=%s AND i.retired_at IS NULL"
        " AND NOT EXISTS (SELECT 1 FROM stage_idea s WHERE s.id = i.id)", (spec.id,)
    )
    refresh_markers(conn)
    return {"rows": n, "with_body": with_body, "inserted": inserted, "updated": n - inserted, "retired": gone}


def sync_policy(*, dsn: str, configs: list[Path]) -> dict:
    """파일 없이 레지스트리의 정책 필드(공개·반출·기록 종류·제외 후보 이유)만 core.source에 맞추고 선별 재료를 다시 계산한다.
    이미 적재된 소스만 갱신한다(새 소스는 적재가 만든다). 수집(collect) 소스는 파일이 seed에 없어 이 길만 있다."""
    with db.pipeline_run(dsn, "policy") as stats, db.connect(dsn) as conn:
        known = {r[0] for r in conn.execute("SELECT id FROM core.source")}
        synced, skipped = [], []
        for config in configs:
            for spec in load_sources(config, Path("/nonexistent")):
                if spec.id not in known:
                    skipped.append(spec.id)
                    continue
                upsert_source(conn, spec, body_present=None)
                synced.append(spec.id)
        markers = refresh_markers(conn)
        conn.commit()
        stats.update({"synced": len(synced), "skipped": len(skipped), **markers})
    print(f"[policy] synced {len(synced)} sources, markers {markers}"
          + (f", not yet ingested: {skipped}" if skipped else ""))
    return {"synced": synced, "skipped": skipped, **markers}


def ingest(*, dsn: str, config: Path, seed_dir: Path, secret_path: Path, only: str | None = None,
           force: bool = False, allow_retire: bool = False) -> list[dict]:
    """force = 같은 파일도 다시 적재. allow_retire = 절반 넘게 사라지는 퇴역도 허용(원천이 실제로 줄었을 때만).
    퇴역한 ID에 걸린 사람 판단(진단·승인)은 지우지 않고 공개에서만 빠진다."""
    secret = load_secret(secret_path)
    results = []
    with db.pipeline_run(dsn, "ingest") as stats:
        for spec in load_sources(config, seed_dir):
            if only and spec.id != only:
                continue
            if not spec.path.exists():
                print(f"[ingest] skip {spec.id}: {spec.path.name} not in seed dir", file=sys.stderr)
                results.append({"source": spec.id, "status": "missing_file"})
                continue
            digest = file_sha256(spec.path)
            with db.connect(dsn) as conn:
                # FK를 위해 소스 행을 먼저 보장(정책 필드는 적재 성공 시 다시 갱신)
                upsert_source(conn, spec, body_present=None)
                if not force and conn.execute(
                    "SELECT 1 FROM core.ingest_run WHERE source_id=%s AND file_sha256=%s AND status='ok'",
                    (spec.id, digest),
                ).fetchone():
                    conn.commit()
                    print(f"[ingest] {spec.id}: unchanged")
                    results.append({"source": spec.id, "status": "unchanged"})
                    continue
                run_id = conn.execute(
                    "INSERT INTO core.ingest_run (source_id, file_sha256, status) VALUES (%s,%s,'running') RETURNING id",
                    (spec.id, digest),
                ).fetchone()[0]
                conn.commit()
            try:
                with db.connect(dsn) as conn:
                    r = _apply(conn, spec, ADAPTERS[spec.adapter](spec, secret), run_id, allow_retire=allow_retire)
                    conn.execute(
                        "UPDATE core.ingest_run SET status='ok', rows=%s, finished_at=now() WHERE id=%s",
                        (r["rows"], run_id),
                    )
                    conn.commit()
            except Exception as e:
                with db.connect(dsn) as conn:
                    conn.execute(
                        "UPDATE core.ingest_run SET status='failed', error=%s, finished_at=now() WHERE id=%s",
                        (f"{type(e).__name__}: {e}", run_id),
                    )
                    conn.commit()
                raise
            print(f"[ingest] {spec.id}: {r}")
            results.append({"source": spec.id, "status": "ok", **r})
        stats["sources"] = results
    return results
