"""DB 작업 기록(db_log). git 대신 DB를 보는 쪽과 서로 한 일을 확인하는 용도.

- write: 1행 추가. 행 수(master·raw)는 기록 시점 값, 파일이 있으면 sha256 계산
- merge: 다른 DB(복원 전 기존 DB)의 기록 중 없는 행을 옮김. 같은 행 = (at, place, action, note)
- recent: 최근 기록
- place = BB_LOG_PLACE(없으면 호스트 이름). 적는 방식 = 0009 마이그레이션의 표 주석(COMMENT ON TABLE db_log)
"""
from __future__ import annotations

import hashlib
import os
import socket
from pathlib import Path

from . import db


def place() -> str:
    return os.environ.get("BB_LOG_PLACE") or socket.gethostname()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write(*, dsn: str, action: str, note: str, file: Path | None = None, digest: str | None = None,
          where: str | None = None, at: str | None = None) -> dict:
    """dump = 덤프 전에 적음(파일 이름만). restore = 파일 또는 digest로 sha256 필수(DB 제약)."""
    digest = digest or (sha256(file) if file and file.is_file() else None)
    with db.connect(dsn) as conn:
        row = conn.execute(
            """INSERT INTO db_log (at, place, action, note, master, raw, file, sha256)
               VALUES (coalesce(%s::timestamptz, now()), %s, %s, %s,
                       (SELECT count(*) FROM master), (SELECT count(*) FROM raw), %s, %s)
               RETURNING id, at, master, raw""",
            (at, where or place(), action, note, file.name if file else None, digest)).fetchone()
        conn.commit()
    return {"id": row[0], "at": row[1].isoformat(), "action": action, "master": row[2], "raw": row[3],
            "file": file.name if file else None, "sha256": digest}


def merge(*, dsn: str, src_dsn: str) -> dict:
    cols = "at, place, action, note, master, raw, file, sha256"
    with db.connect(src_dsn) as src:
        rows = src.execute(f"SELECT {cols} FROM db_log ORDER BY at, id").fetchall()
    with db.connect(dsn) as conn:
        have = set(conn.execute("SELECT at, place, action, note FROM db_log").fetchall())
        new = [r for r in rows if r[:4] not in have]
        with conn.cursor() as cur:
            cur.executemany(f"INSERT INTO db_log ({cols}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", new)
        conn.commit()
    return {"status": "ok", "source_rows": len(rows), "added": len(new)}


def recent(*, dsn: str, limit: int = 20) -> list[tuple]:
    with db.connect(dsn) as conn:
        rows = conn.execute(
            """SELECT id, to_char(at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI'), place, action,
                      master, raw, coalesce(file, ''), note
                 FROM db_log ORDER BY at DESC, id DESC LIMIT %s""", (limit,)).fetchall()
    return rows[::-1]
