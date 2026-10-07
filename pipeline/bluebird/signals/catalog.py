"""바뀐 것 D 신호의 이벤트 쪽: 공공데이터포털 목록개방현황(15062804) 스냅샷과 diff (계획 §3.4).

- 스냅샷 #0 = 우리가 처음 받은 목록. 그 안의 행은 모두 portal_registered(포털 등록일만 표기).
- 이후 스냅샷에서 처음 나타난 데이터셋:
    · (org_code, title_norm)이 이전 행과 같으면 재등록 → rereg_of 지정, 신규로 세지 않음
    · registered_at ≥ 기준 스냅샷일 − 7일 이면 observed_new("파랑새 관측 신규")
    · 아니면 reappeared(오래전에 등록됐는데 이번에 목록에 다시 나타남, 약한 근거)
- observed_new·reappeared는 core.condition_change(kind='dataset_opened')를 만든다.
날짜만으로 과거의 부재를 주장하지 않는다(금지 문구는 wording.py). 판별은 missing_data 의미 일치 + 판정 + 사람 승인으로 한다.
"""

from __future__ import annotations

import csv
import io
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .. import db
from ..sources import file_sha256

CATALOG_PK = "15062804"
CATALOG_DETAIL_PK = "uddi:53db1572-bcd7-497c-86c4-b200cb73ee63"
PORTAL = "https://www.data.go.kr"
NEW_WINDOW = timedelta(days=7)
KST = timezone(timedelta(hours=9))


def today_kst() -> date:
    return datetime.now(KST).date()

COLS = {  # 헤더 이름 → 키
    "목록키": "pk", "목록유형": "kind", "목록명": "title", "분류체계": "category", "제공기관코드": "org_code",
    "제공기관": "org", "키워드": "keywords", "등록일": "registered_at", "수정일": "modified_at", "설명": "description",
    "이용허락범위": "license", "목록 URL": "url",
}

_SUFFIX = re.compile(r"_?\d{8}$")
_YEAR = re.compile(r"(19|20)\d{2}(년도?)?")
_STRIP = re.compile(r"[\s_()\[\]（）·,.\-]+")


def title_norm(title: str) -> str:
    t = unicodedata.normalize("NFKC", title or "")
    t = _SUFFIX.sub("", t)
    t = _YEAR.sub("", t)
    return _STRIP.sub("", t).lower()


def _date(s: str) -> date | None:
    s = (s or "").strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def parse(path: Path) -> list[dict]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp949")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [h for h in COLS if h not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"catalog header missing {missing}")
    rows: dict[str, dict] = {}
    for r in reader:
        d = {k: (r.get(h) or "").strip() for h, k in COLS.items()}
        if not d["pk"] or not d["title"]:
            continue
        d["registered_at"] = _date(d["registered_at"])
        d["modified_at"] = _date(d["modified_at"])
        d["title_norm"] = title_norm(d["title"])
        d["url"] = d["url"] if d["url"].startswith("http") else f"{PORTAL}/data/{d['pk']}/fileData.do"
        rows.setdefault(d["pk"], d)  # 같은 목록키가 여러 유형(FILE/API)으로 나오면 첫 행
    return list(rows.values())


def import_snapshot(*, dsn: str, path: Path, taken_at: date) -> dict:
    sha = file_sha256(path)
    rows = parse(path)
    with db.pipeline_run(dsn, "signals-catalog") as stats, db.connect(dsn) as conn:
        if conn.execute("SELECT 1 FROM core.catalog_snapshot WHERE file_sha256=%s", (sha,)).fetchone():
            print(f"[catalog] {path.name}: already imported", file=sys.stderr)
            stats["skipped"] = "same sha256"
            return {"skipped": True}
        last = conn.execute("SELECT max(taken_at) FROM core.catalog_snapshot").fetchone()[0]
        if last and taken_at <= last:
            raise ValueError(f"snapshot date {taken_at} must be after last snapshot {last}")
        snap_id = conn.execute("SELECT coalesce(max(id) + 1, 0) FROM core.catalog_snapshot").fetchone()[0]
        conn.execute(
            "INSERT INTO core.catalog_snapshot (id, taken_at, file_name, file_sha256, rows, weekday)"
            " VALUES (%s,%s,%s,%s,%s,%s)",
            (snap_id, taken_at, path.name, sha, len(rows), taken_at.isoweekday()),
        )
        conn.execute(
            """CREATE TEMP TABLE stage_ds (pk text, org_code text, org text, title text, title_norm text,
                 category text, keywords text, description text, registered_at date, modified_at date,
                 license text, url text) ON COMMIT DROP"""
        )
        with conn.cursor().copy("COPY stage_ds FROM STDIN") as cp:
            for d in rows:
                cp.write_row((d["pk"], d["org_code"], d["org"], d["title"], d["title_norm"], d["category"],
                              d["keywords"], d["description"], d["registered_at"], d["modified_at"],
                              d["license"], d["url"]))
        base = conn.execute("SELECT taken_at FROM core.catalog_snapshot WHERE id = 0").fetchone()[0]
        # 이미 아는 데이터셋: 마지막 관측·메타 갱신
        updated = conn.execute(
            """UPDATE core.signal_dataset s SET last_seen_snapshot_id=%(id)s, title=t.title, org=t.org,
                 modified_at=t.modified_at, description=t.description, keywords=t.keywords, license=t.license
               FROM stage_ds t WHERE t.pk = s.public_data_pk""",
            {"id": snap_id},
        ).rowcount
        # 새로 나타난 데이터셋
        inserted = conn.execute(
            """INSERT INTO core.signal_dataset (public_data_pk, org_code, org, title, title_norm, category, keywords,
                 description, registered_at, modified_at, license, url, first_seen_snapshot_id,
                 last_seen_snapshot_id, first_seen_at, tier, rereg_of)
               SELECT t.pk, t.org_code, t.org, t.title, t.title_norm, t.category, t.keywords, t.description,
                      t.registered_at, t.modified_at, t.license, t.url, %(id)s, %(id)s, %(at)s,
                      CASE WHEN %(id)s = 0 THEN 'portal_registered'
                           WHEN t.registered_at >= %(cut)s THEN 'observed_new'
                           ELSE 'reappeared' END,
                      CASE WHEN %(id)s = 0 THEN NULL ELSE
                        (SELECT s.public_data_pk FROM core.signal_dataset s
                          WHERE s.org_code = t.org_code AND s.title_norm = t.title_norm
                          ORDER BY s.first_seen_at, s.public_data_pk LIMIT 1) END
                 FROM stage_ds t
                WHERE NOT EXISTS (SELECT 1 FROM core.signal_dataset s WHERE s.public_data_pk = t.pk)""",
            {"id": snap_id, "at": taken_at, "cut": base - NEW_WINDOW if snap_id else taken_at},
        ).rowcount
        changes = conn.execute(
            """INSERT INTO core.condition_change (id, kind, ref_id, occurred_at, tier, url, title)
               SELECT 'dataset:' || public_data_pk, 'dataset_opened', public_data_pk, first_seen_at, tier, url, title
                 FROM core.signal_dataset
                WHERE first_seen_snapshot_id = %s AND tier IN ('observed_new', 'reappeared') AND rereg_of IS NULL
               ON CONFLICT (kind, ref_id) DO NOTHING""",
            (snap_id,),
        ).rowcount
        tiers = dict(conn.execute(
            "SELECT tier || CASE WHEN rereg_of IS NULL THEN '' ELSE '_rereg' END, count(*)"
            " FROM core.signal_dataset WHERE first_seen_snapshot_id=%s GROUP BY 1", (snap_id,)))
        conn.commit()
        res = {"snapshot_id": snap_id, "taken_at": str(taken_at), "rows": len(rows), "updated": updated,
               "new": inserted, "tiers": tiers, "condition_changes": changes}
        stats.update(res)
    print(f"[catalog] {res}")
    return res


def fetch(*, egress, out_dir: Path) -> Path:
    """data.go.kr에서 최신 목록개방현황 파일을 egress로 받는다(키 불필요)."""
    r = egress.post_form(
        "signal", f"{PORTAL}/tcs/dss/selectFileDataDownload.do",
        {"publicDataPk": CATALOG_PK, "publicDataDetailPk": CATALOG_DETAIL_PK, "publicDataTyCode": "PR0051"},
        path_template="/tcs/dss/selectFileDataDownload.do",
    )
    meta = r.json()
    if not meta.get("atchFileId"):
        raise RuntimeError(f"catalog download token missing: status={meta.get('status')}")
    name = (meta.get("dataSetFileDetailInfo") or {}).get("dataNm") or "catalog"
    f = egress.get("signal", f"{PORTAL}/cmm/cmm/fileDownload.do",
                   params={"atchFileId": meta["atchFileId"], "fileDetailSn": meta["fileDetailSn"],
                           "insertDataPrcus": "N"},
                   path_template="/cmm/cmm/fileDownload.do")
    if f.status != 200 or len(f.content) < 1_000_000:
        raise RuntimeError(f"catalog download failed: HTTP {f.status}, {len(f.content)} bytes")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}_{today_kst().isoformat()}.csv"
    path.write_bytes(f.content)
    print(f"[catalog] fetched {path} ({len(f.content):,} bytes)")
    return path
