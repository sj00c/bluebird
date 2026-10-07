"""DB 연결과 SQL 파일 기반 마이그레이션. 스키마 소유자는 이 디렉터리 하나다.

적용된 마이그레이션은 sha256과 함께 기록한다. 이미 적용된 파일 내용이 바뀌면 실패한다(0001 재작성 후에는 0002+ 추가만).
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from importlib import resources

import psycopg

TARGETS = ("core", "publish")


class MigrationChecksumError(RuntimeError):
    pass


def connect(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, autocommit=False)


def migration_files(target: str) -> list[tuple[str, str, str]]:
    """(파일명, sha256, SQL) 목록, 파일명 순."""
    if target not in TARGETS:
        raise ValueError(f"unknown migration target {target!r}")
    out = []
    for f in resources.files("bluebird.db.migrations").joinpath(target).iterdir():
        if f.name.endswith(".sql"):
            sql = f.read_text(encoding="utf-8")
            out.append((f.name, hashlib.sha256(sql.encode()).hexdigest(), sql))
    return sorted(out)


def migrate(dsn: str, target: str) -> list[str]:
    files = migration_files(target)
    applied: list[str] = []
    with connect(dsn) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS migrations")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS migrations.applied (target text, version text, sha256 text NOT NULL,"
            " applied_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (target, version))"
        )
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('bluebird.migrate'))")
        done = dict(conn.execute("SELECT version, sha256 FROM migrations.applied WHERE target = %s", (target,)))
        for name, sha, sql in files:
            if name in done:
                if done[name] != sha:
                    raise MigrationChecksumError(
                        f"{target}/{name} changed after it was applied ({done[name][:12]} -> {sha[:12]}); "
                        "add a new migration instead"
                    )
                continue
            conn.execute(sql)
            conn.execute("INSERT INTO migrations.applied (target, version, sha256) VALUES (%s, %s, %s)",
                         (target, name, sha))
            applied.append(name)
        conn.commit()
    return applied


@contextmanager
def pipeline_run(dsn: str, stage: str):
    """core.pipeline_run에 단계 실행 기록. 본 작업과 별도 커넥션이라 실패도 남는다."""
    with connect(dsn) as conn:
        run_id = conn.execute(
            "INSERT INTO core.pipeline_run (stage, status) VALUES (%s, 'running') RETURNING id", (stage,)
        ).fetchone()[0]
        conn.commit()
    stats: dict = {}
    try:
        yield stats
    except BaseException as e:
        with connect(dsn) as conn:
            conn.execute(
                "UPDATE core.pipeline_run SET status='failed', finished_at=now(), stats=%s, error=%s WHERE id=%s",
                (json.dumps(stats, ensure_ascii=False, default=str), f"{type(e).__name__}: {e}", run_id),
            )
            conn.commit()
        raise
    with connect(dsn) as conn:
        conn.execute(
            "UPDATE core.pipeline_run SET status='ok', finished_at=now(), stats=%s WHERE id=%s",
            (json.dumps(stats, ensure_ascii=False, default=str), run_id),
        )
        conn.commit()
