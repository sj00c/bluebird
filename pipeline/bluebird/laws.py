"""국가법령정보 → external.law(법령·자치법규가 바뀐 기록, 한 표).

- 법령 = 법령 변경이력 목록(target=lsHstInf)을 하루씩 조회 → 연혁 포함 공포 1건 = 1행(번호 = 법령일련번호).
  변경일 = 법제처 DB 수정일이라 옛 연혁(1948년 공포 등)도 섞여 옴 → 공포일·시행일 중 하나가 범위 안인 것만 저장
- 자치법규 = 자치법규 목록(target=ordin) 시행일 범위 조회. 이 API는 현행본만 줌 → 같은 조례가 범위 안에서 두 번
  바뀌면 마지막 것만 남음(연혁 목록 API 없음)
- 개정 이유 = 법령의 제정·일부개정·전부개정만 상세 조회(타법개정 = 다른 법 따라 바뀐 것, 자치법규 = API에 없음)
- 링크 = 공개 페이지 주소로 다시 만듦(API 응답 링크에 인증 코드 OC가 들어 있음 → 저장 안 함)
- 출처 = 행마다 source 칸에 기관·서비스·호출 이름
- 재실행 = 같은 공포 번호 덮어쓰기. 이미 받은 개정 이유는 다시 안 받음
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from . import db
from .egress import Egress

API = "https://www.law.go.kr/DRF/"
PAGE = 100
# 종류 → (검색 target, 응답 최상위 키, 목록 키, 칸 이름들, 공개 링크)
KINDS = {
    "법령": ("lsHstInf", "LawSearch", "law",
            {"id": "법령일련번호", "name": "법령명한글", "form": "법령구분명", "change": "제개정구분명",
             "org": "소관부처명", "announced": "공포일자", "effective": "시행일자"},
            "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={id}"),
    "자치법규": ("ordin", "OrdinSearch", "law",
             {"id": "자치법규일련번호", "name": "자치법규명", "form": "자치법규종류", "change": "제개정구분명",
              "org": "지자체기관명", "announced": "공포일자", "effective": "시행일자"},
             "https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq={id}"),
}
REASON_CHANGES = ("제정", "일부개정", "전부개정")
COLS = ("kind", "id", "name", "form", "change", "org", "announced", "effective", "url", "source")
# 행마다 출처 표기(external.law.source)
SOURCE = {
    "법령": "법제처 국가법령정보 공동활용 Open API · 법령 변경이력 목록(lawSearch, target=lsHstInf, 변경일별)"
           " · 개정 이유 = 법령 본문(lawService, target=law, MST=법령일련번호)",
    "자치법규": "법제처 국가법령정보 공동활용 Open API · 자치법규 목록(lawSearch, target=ordin, 시행일 범위, 현행본)",
}


def _date(v: str | None) -> date | None:
    v = (v or "").strip()
    return date(int(v[:4]), int(v[4:6]), int(v[6:])) if len(v) == 8 and v.isdigit() else None


def _get(eg: Egress, path: str, params: dict) -> dict:
    r = eg.get("collect", API + path, params={**params, "type": "JSON"}, secret_params={"OC": os.environ["LAW_OC"]})
    if r.status != 200:
        raise RuntimeError(f"law.go.kr HTTP {r.status}")
    return r.json()


def rows_of(kind: str, items: list[dict]) -> list[tuple]:
    """API 목록 항목 → external.law 행. 같은 번호가 여러 번 나오면 하나."""
    _t, _r, _l, f, link = KINDS[kind]
    out: dict[str, tuple] = {}
    for it in items:
        rid = str(it.get(f["id"]) or "").strip()
        if rid:
            out[rid] = (kind, rid, (it.get(f["name"]) or "").strip(), it.get(f["form"]) or None,
                        it.get(f["change"]) or None, it.get(f["org"]) or None, _date(it.get(f["announced"])),
                        _date(it.get(f["effective"])), link.format(id=rid), SOURCE[kind])
    return list(out.values())


def reason_text(detail: dict) -> str | None:
    """상세 응답의 제개정이유 → 한 덩어리 글(줄 단위 이음)."""
    body = (detail.get("법령") or detail).get("제개정이유") or {}
    lines: list[str] = []

    def walk(v):
        if isinstance(v, str):
            if v.strip():
                lines.append(v.strip())
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    walk(body)
    return "\n".join(lines) or None


def collect(*, dsn: str, egress: Egress, since: date, until: date, kinds: tuple[str, ...] = tuple(KINDS),
            workers: int = 4) -> list[dict]:
    results = []
    for kind in kinds:
        target, root, key, _f, _l = KINDS[kind]
        # 법령 = 변경일 하루씩, 자치법규 = 시행일 범위 한 번
        queries = ([{"regDt": f"{since + timedelta(d):%Y%m%d}"} for d in range((until - since).days + 1)]
                   if kind == "법령" else [{"efYd": f"{since:%Y%m%d}~{until:%Y%m%d}"}])

        def listing(q: dict, target=target, root=root, key=key) -> list[dict]:
            out, n = [], 1
            while True:
                got = _get(egress, "lawSearch.do", {"target": target, **q, "display": PAGE, "page": n})[root]
                items = got.get(key) or []
                out += items if isinstance(items, list) else [items]
                if n * PAGE >= int(got.get("totalCnt") or 0):
                    return out
                n += 1
        with ThreadPoolExecutor(workers) as pool:
            items = [it for chunk in pool.map(listing, queries) for it in chunk]
        rows = [r for r in rows_of(kind, items)
                if any(d and since <= d <= until for d in (r[6], r[7])) or (r[7] and r[7] > until and r[6] and r[6] >= since)]
        with db.connect(dsn) as conn:
            conn.cursor().executemany(
                f"INSERT INTO external.law ({', '.join(COLS)}) VALUES ({', '.join(['%s'] * len(COLS))})"
                " ON CONFLICT (kind, id) DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in COLS[2:])
                + ", fetched = now()", rows)
            conn.commit()
        results.append({"source": kind, "status": "ok", "queries": len(queries), "rows": len(rows)})
    # 개정 이유: 법령 중 제정·일부개정·전부개정, 아직 없는 것만
    with db.connect(dsn) as conn:
        todo = [r[0] for r in conn.execute(
            "SELECT id FROM external.law WHERE kind = '법령' AND reason IS NULL AND change = ANY(%s)",
            (list(REASON_CHANGES),))]

    def reason(mst: str) -> tuple[str | None, str]:
        return reason_text(_get(egress, "lawService.do", {"target": "law", "MST": mst})), mst
    with ThreadPoolExecutor(workers) as pool, db.connect(dsn) as conn:
        got = [r for r in pool.map(reason, todo) if r[0]]
        conn.cursor().executemany("UPDATE external.law SET reason = %s WHERE kind = '법령' AND id = %s", got)
        conn.commit()
    results.append({"source": "개정 이유", "status": "ok", "asked": len(todo), "rows": len(got)})
    return results
