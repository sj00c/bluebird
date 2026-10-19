"""DB 작업 기록(db_log). git 대신 DB를 보는 쪽과 서로 한 일을 확인하는 용도.

- write: 1행 추가. 행 수(master·raw)는 기록 시점 값, 파일을 주면 sha256 계산
- recent: 최근 기록
- place = BB_LOG_PLACE(없으면 호스트 이름)
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


def write(*, dsn: str, action: str, note: str, file: Path | None = None, where: str | None = None) -> dict:
    digest = sha256(file) if file and file.is_file() else None
    with db.connect(dsn) as conn:
        row = conn.execute(
            """INSERT INTO db_log (place, action, note, master, raw, file, sha256)
               VALUES (%s, %s, %s, (SELECT count(*) FROM master), (SELECT count(*) FROM raw), %s, %s)
               RETURNING id, at, master, raw""",
            (where or place(), action, note, file.name if file else None, digest)).fetchone()
        conn.commit()
    return {"id": row[0], "at": row[1].isoformat(), "action": action, "master": row[2], "raw": row[3],
            "file": file.name if file else None, "sha256": digest}


def recent(*, dsn: str, limit: int = 20) -> list[tuple]:
    with db.connect(dsn) as conn:
        rows = conn.execute(
            """SELECT id, to_char(at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI'), place, action,
                      master, raw, coalesce(file, ''), note
                 FROM db_log ORDER BY at DESC, id DESC LIMIT %s""", (limit,)).fetchall()
    return rows[::-1]
