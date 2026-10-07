"""DB 연결과 SQL 파일 기반 마이그레이션. 스키마 소유자는 이 디렉터리 하나다."""

from __future__ import annotations

import json
from contextlib import contextmanager
from importlib import resources

import psycopg

TARGETS = ("core", "publish")


def connect(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, autocommit=False)


def migrate(dsn: str, target: str) -> list[str]:
    if target not in TARGETS:
        raise ValueError(f"unknown migration target {target!r}")
    files = sorted(
        (f for f in resources.files("bluebird.db.migrations").joinpath(target).iterdir() if f.name.endswith(".sql")),
        key=lambda f: f.name,
    )
    applied: list[str] = []
    with connect(dsn) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS public.schema_migrations "
            "(target text, version text, applied_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (target, version))"
        )
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('bluebird.migrate'))")
        done = {r[0] for r in conn.execute("SELECT version FROM public.schema_migrations WHERE target = %s", (target,))}
        for f in files:
            if f.name in done:
                continue
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO public.schema_migrations (target, version) VALUES (%s, %s)", (target, f.name))
            applied.append(f.name)
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
                (json.dumps(stats, ensure_ascii=False), f"{type(e).__name__}: {e}", run_id),
            )
            conn.commit()
        raise
    with connect(dsn) as conn:
        conn.execute(
            "UPDATE core.pipeline_run SET status='ok', finished_at=now(), stats=%s WHERE id=%s",
            (json.dumps(stats, ensure_ascii=False), run_id),
        )
        conn.commit()
