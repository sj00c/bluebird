"""로컬에서 만든 검색 자료 → 다른 정제 DB(서버)로 옮기기. 절차 = docs/TRANSFER_PLAN.md

옮기는 것(행 삭제 없음, 대상 DB에 마이그레이션 0016~0019 적용 후):
- master: embedding_input·embedding·search_tokens(사용 대상만). 대상 master 기본 19칸이 원본과 같을 때만(체크섬)
- external.law · external.doc: 전체 행. 대상 표가 비어 있을 때만
- db_log: 원본에만 있는 기록(때·곳·작업·내용이 같은 행 = 이미 있음)

파일 = 바이너리 COPY(pgvector halfvec 그대로) + manifest.json(행 수·파일 sha256·내용 체크섬).
가져오기 = 한 트랜잭션(확인 실패·행 수 다름 = 아무것도 안 바뀜). 확인 = 옮긴 내용 체크섬이 원본과 같은지
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from . import db, dblog

# master 기본 19칸(0014_slim 이후). 원본·대상이 같은 바탕인지 보는 체크섬 대상
BASE_COLS = ("api", "key", "title", "body", "kind", "field", "program", "award", "year", "url", "exclude_reasons",
             "label", "item_type", "goal", "solution", "features", "domain", "evidence", "verified")
SEARCH_COLS = ("api", "key", "embedding_input", "embedding", "search_tokens")
SEARCH_WHERE = "exclude_reasons = '{}' AND (embedding_input IS NOT NULL OR search_tokens IS NOT NULL)"
TABLES = {"external.law": "kind, id", "external.doc": "source, id"}   # 표 → 정렬 키(기본 키)
LOG_COLS = ("at", "place", "action", "note", "master", "raw", "file", "sha256")
CHUNK = 1 << 20


def _md5_rows(conn, cols: tuple[str, ...], table: str, where: str, order: str) -> str:
    """행마다 md5 → 순서대로 이은 것의 md5(벡터가 커서 행 글자를 그대로 이으면 1GB 한도 넘음)."""
    joined = "||'|'||".join(f"coalesce({c}::text, '')" for c in cols)
    sql = f"SELECT md5(string_agg(md5({joined}), '' ORDER BY {order})) FROM {table} WHERE {where}"
    return conn.execute(sql).fetchone()[0] or ""


def checksums(conn) -> dict[str, str]:
    """바탕(master 19칸) + 옮기는 내용 체크섬. 날짜 글자 = UTC·ISO로 고정(서버 설정과 무관)."""
    conn.execute("SET TimeZone = 'UTC'")
    conn.execute("SET DateStyle = 'ISO, YMD'")
    out = {"base": _md5_rows(conn, BASE_COLS, "master", "true", "api, key"),
           "master": _md5_rows(conn, SEARCH_COLS, "master", SEARCH_WHERE, "api, key")}
    for table, order in TABLES.items():
        out[table] = _md5_rows(conn, tuple(_columns(conn, table)), table, "true", order)
    return out


def _columns(conn, table: str) -> list[str]:
    schema, name = table.split(".")
    return [r[0] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = %s"
                                       " AND table_name = %s ORDER BY ordinal_position", (schema, name))]


def _copy_out(conn, sql: str, path: Path) -> str:
    digest = hashlib.sha256()
    with conn.cursor().copy(f"COPY ({sql}) TO STDOUT (FORMAT binary)") as cp, path.open("wb") as f:
        for data in cp:
            f.write(data)
            digest.update(data)
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def export(*, dsn: str, out: Path) -> dict:
    """원본 DB → out 폴더(파일 3개 + manifest.json). out은 비어 있어야 함. 파일 전부 같은 시점(REPEATABLE READ)."""
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise RuntimeError(f"{out}: 빈 폴더가 아님")
    files: dict[str, dict] = {}
    with db.connect(dsn) as conn:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        sums = checksums(conn)
        rows = conn.execute(f"SELECT count(*) FROM master WHERE {SEARCH_WHERE}").fetchone()[0]
        sql = f"SELECT {', '.join(SEARCH_COLS)} FROM master WHERE {SEARCH_WHERE} ORDER BY api, key"
        files["master"] = {"file": "master_search.bin", "columns": list(SEARCH_COLS), "rows": rows,
                           "sha256": _copy_out(conn, sql, out / "master_search.bin")}
        for table in TABLES:
            cols = _columns(conn, table)
            name = table.replace(".", "_") + ".bin"
            files[table] = {"file": name, "columns": cols,
                            "rows": conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0],
                            "sha256": _copy_out(conn, f"SELECT {', '.join(cols)} FROM {table}", out / name)}
        log = [[v.isoformat() if isinstance(v, datetime) else v for v in r]
               for r in conn.execute(f"SELECT {', '.join(LOG_COLS)} FROM db_log ORDER BY at, id")]
        migrations = [r[0] for r in conn.execute("SELECT version FROM migrations.applied WHERE target = 'master'"
                                                 " ORDER BY version")]
        conn.rollback()
    manifest = {"made_at": datetime.now(UTC).isoformat(timespec="seconds"), "checksums": sums,
                "migrations": migrations, "files": files, "db_log": log}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"status": "ok", "out": str(out), **{k: v["rows"] for k, v in files.items()}, "db_log": len(log)}


def _copy_in(cur, sql: str, path: Path) -> None:
    with cur.copy(sql) as cp, path.open("rb") as f:
        while chunk := f.read(CHUNK):
            cp.write(chunk)


def _manifest(src: Path) -> dict:
    return json.loads((src / "manifest.json").read_text(encoding="utf-8"))


def check(*, dsn: str, src: Path) -> list[str]:
    """가져오기 전 확인(읽기만). 문제 목록, 빈 목록 = 가져와도 됨."""
    manifest = _manifest(src)
    problems = [f"{item['file']}: sha256 다름(파일 손상·바뀜)" for item in manifest["files"].values()
                if _sha256(src / item["file"]) != item["sha256"]]
    with db.connect(dsn) as conn:
        if not conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone():
            problems.append("대상 DB에 pgvector 확장 없음(관리자: 이미지 교체 + CREATE EXTENSION vector)")
        have = {r[0] for r in conn.execute("SELECT version FROM migrations.applied WHERE target = 'master'")}
        if missing := [m for m in manifest["migrations"] if m not in have]:
            problems.append(f"대상 DB 마이그레이션 없음: {', '.join(missing)} (bluebird migrate --target master 먼저)")
            return problems
        if checksums(conn)["base"] != manifest["checksums"]["base"]:
            problems.append("대상 master 기본 19칸이 원본과 다름(같은 바탕이 아니면 옮기지 않음)")
        for table in TABLES:
            if n := conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                problems.append(f"{table}: 이미 {n}행 있음(빈 표에만 넣음)")
        conn.rollback()
    return problems


def import_(*, dsn: str, src: Path) -> dict:
    """src 폴더 → 대상 DB. 확인 실패 = 아무것도 안 바꿈. 성공 = 한 트랜잭션으로 반영 + db_log restore 1줄."""
    if problems := check(dsn=dsn, src=src):
        return {"status": "blocked", "problems": problems}
    manifest = _manifest(src)
    files = manifest["files"]
    with db.connect(dsn) as conn, conn.cursor() as cur:
        m = files["master"]
        cur.execute("CREATE TEMP TABLE transfer_master (api text, key text, embedding_input text,"
                    " embedding halfvec(1536), search_tokens text) ON COMMIT DROP")
        _copy_in(cur, "COPY transfer_master FROM STDIN (FORMAT binary)", src / m["file"])
        updated = cur.execute("UPDATE master t SET embedding_input = s.embedding_input, embedding = s.embedding,"
                              " search_tokens = s.search_tokens FROM transfer_master s"
                              " WHERE t.api = s.api AND t.key = s.key AND t.exclude_reasons = '{}'").rowcount
        if updated != m["rows"]:
            raise RuntimeError(f"master 갱신 {updated}행 ≠ 파일 {m['rows']}행 → 되돌림")
        counts = {"master": updated}
        for table in TABLES:
            item = files[table]
            _copy_in(cur, f"COPY {table} ({', '.join(item['columns'])}) FROM STDIN (FORMAT binary)", src / item["file"])
            counts[table] = cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            if counts[table] != item["rows"]:
                raise RuntimeError(f"{table} {counts[table]}행 ≠ 파일 {item['rows']}행 → 되돌림")
        have = set(cur.execute("SELECT at, place, action, note FROM db_log").fetchall())
        new = [r for r in manifest["db_log"] if (datetime.fromisoformat(r[0]), *r[1:4]) not in have]
        cur.executemany(f"INSERT INTO db_log ({', '.join(LOG_COLS)}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", new)
        note = (f"검색 자료 옮김(manifest {manifest['made_at']}): master 검색 칸 {counts['master']}행, "
                f"external.law {counts['external.law']}행, external.doc {counts['external.doc']}행, "
                f"원본 db_log {len(new)}줄")
        cur.execute("INSERT INTO db_log (place, action, note, master, raw, file, sha256) VALUES (%s, 'restore', %s,"
                    " (SELECT count(*) FROM master), (SELECT count(*) FROM raw), 'manifest.json', %s)",
                    (dblog.place(), note, _sha256(src / "manifest.json")))
        conn.commit()
    return {"status": "ok", **counts, "db_log_added": len(new)}


def verify(*, dsn: str, src: Path) -> dict:
    """옮긴 뒤: 대상 DB 체크섬(바탕 + 옮긴 내용 3개)이 원본(manifest)과 같은지."""
    want = _manifest(src)["checksums"]
    with db.connect(dsn) as conn:
        got = checksums(conn)
        conn.rollback()
    same = {k: got[k] == want[k] for k in want}
    return {"status": "ok" if all(same.values()) else "different", **same}
