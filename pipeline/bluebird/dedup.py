"""master 중복 표시(행 삭제 없음). 규칙 = docs/DEDUP_PLAN.md, 사유 뜻 = exclusion_reason.

- 같은 글: 제목+본문 완전 일치(공백 제거). 대구 참여예산 제외(본문 = 정형 문구) → 먼저 낸 것이 대표
- 같은 장소: 제목+지번 완전 일치 → 나중 것이 대표
- 같은 출품작(한 작품이 여러 출처에 실림): 대회명+제목(6자 이상)+수상 등급 일치, 연도 차 1 이내, 소스 다름
  → 본문 긴 것 → 수상 있음 → 이른 연도
- 순서 같은 글 → 같은 장소 → 같은 출품작. 뒤 단계는 앞 단계 대표끼리. 모든 중복 행은 최종 대표를 가리킴
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable

from . import db, quality

Key = tuple[str, str]   # (api, key)

DAEGU = "daegu_budget_project_proposals"
# 지번 칸(원본 헤더). 칸 없는 소스 = D2 대상 아님
LOT: dict[str, str] = {DAEGU: "사업 지번주소"}
# 먼저/나중 판단용 원본 날짜 칸. 없으면 year
DATE: dict[str, str] = {
    "seoul_budget_proposals": "WRITE_DT",
    "seoul_free_suggestions": "REG_DATE",
    "seoul_law_proposals": "RDATE",
    "acrc_open_proposals": "regDate",
    "kipris_idea_api": "openingDate",
    "sejong_education_public_proposals": "등록일시",
    "ulsan_open_data_contest_entries": "등록일",
}
ENTRY_TITLE_MIN = 6   # D3 제목 키 최소 길이(기존 core 0015)
_REVERSE = str.maketrans("0123456789", "9876543210")


def title_key(t: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t or "").lower()


def body_key(t: str | None) -> str:
    return re.sub(r"\s", "", t or "")


def contest_key(t: str | None) -> str:
    return re.sub(r"제?\s*[0-9]+\s*회|[0-9]{4}|\s", "", t or "")


def when(date: str | None, year: int | None) -> str | None:
    """정렬용 14자리(YYYYMMDDhhmmss). 날짜 칸 우선, 없으면 연도 1월 1일, 둘 다 없으면 None."""
    digits = re.sub(r"\D", "", date or "")
    if len(digits) >= 8:
        return digits[:14].ljust(14, "0")
    return f"{year:04d}0101000000" if year else None


def plan(rows: Iterable[dict]) -> dict[Key, tuple[Key, str]]:
    """행(api, key, title, body, contest, year, award, date, lot) → {중복 행: (최종 대표, 규칙)}."""
    rows = {(r["api"], r["key"]): r for r in rows}
    for r in rows.values():
        r["tk"], r["bk"], r["ck"] = title_key(r["title"]), body_key(r["body"]), contest_key(r["contest"])
        r["when"] = when(r.get("date"), r["year"])
    parent: dict[Key, tuple[Key, str]] = {}

    def collapse(groups: Iterable[list[Key]], rule: str, rank: Callable[[Key], tuple]) -> None:
        for g in groups:
            if len(g) > 1:
                head = min(g, key=rank)
                parent.update({k: (head, rule) for k in g if k != head})

    def alive() -> list[dict]:
        return [r for k, r in rows.items() if k not in parent]

    def earliest(k: Key) -> tuple:   # 날짜 모르는 행 = 맨 뒤
        return rows[k]["when"] is None, rows[k]["when"] or "", k

    def latest(k: Key) -> tuple:
        return rows[k]["when"] is None, (rows[k]["when"] or "").translate(_REVERSE), k

    d1: dict[tuple[str, str], list[Key]] = defaultdict(list)
    for r in alive():
        if r["api"] != DAEGU and r["tk"] and r["bk"]:
            d1[(r["tk"], r["bk"])].append((r["api"], r["key"]))
    collapse(d1.values(), "같은 글", earliest)

    d2: dict[tuple[str, str, str], list[Key]] = defaultdict(list)
    for r in alive():
        lot = body_key(r.get("lot"))
        if r["api"] in LOT and r["tk"] and lot:
            d2[(r["api"], r["tk"], lot)].append((r["api"], r["key"]))
    collapse(d2.values(), "같은 장소", latest)

    entry: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in alive():
        if r["ck"] and len(r["tk"]) >= ENTRY_TITLE_MIN and r["year"] is not None:
            entry[(r["ck"], r["tk"], " ".join((r["award"] or "").split()))].append(r)
    link: dict[Key, Key] = {}

    def find(k: Key) -> Key:
        while link.get(k, k) != k:
            k = link[k]
        return k

    for group in entry.values():
        for i, x in enumerate(group):
            for y in group[i + 1:]:
                if x["api"] != y["api"] and abs(x["year"] - y["year"]) <= 1:
                    a, b = find((x["api"], x["key"])), find((y["api"], y["key"]))
                    if a != b:
                        link[max(a, b)] = min(a, b)
    d3: dict[Key, list[Key]] = defaultdict(list)
    for k in {k for pair in link.items() for k in pair}:
        d3[find(k)].append(k)
    collapse(d3.values(), "같은 출품작",
             lambda k: (-len(rows[k]["bk"]), rows[k]["award"] is None, rows[k]["year"], k))

    out = {}
    for k, (head, rule) in parent.items():
        while head in parent:
            head = parent[head][0]
        out[k] = (head, rule)
    return out


def mark(*, dsn: str) -> dict:
    """exclude_reasons 재계산: duplicate(위 규칙, canonical = 최종 대표) + 품질 사유(quality.refresh)."""
    cases = lambda m: " ".join("WHEN %s THEN r.payload->>%s" for _ in m)
    sql = (f"SELECT m.api, m.key, m.title, m.body, m.contest, m.year, m.award,"
           f" CASE m.api {cases(DATE)} END, CASE m.api {cases(LOT)} END"
           " FROM master m JOIN raw r ON r.source = m.api AND r.key = m.key")
    params = [x for pair in (*DATE.items(), *LOT.items()) for x in pair]
    cols = ("api", "key", "title", "body", "contest", "year", "award", "date", "lot")
    with db.connect(dsn) as conn:
        result = plan(dict(zip(cols, row, strict=True)) for row in conn.execute(sql, params))
        with conn.cursor() as cur:
            cur.execute("UPDATE master SET exclude_reasons = array_remove(exclude_reasons, 'duplicate'),"
                        " canonical_api = NULL, canonical_key = NULL"
                        " WHERE 'duplicate' = ANY(exclude_reasons) OR canonical_api IS NOT NULL")
            cur.execute("CREATE TEMP TABLE dup (api text, key text, capi text, ckey text,"
                        " PRIMARY KEY (api, key)) ON COMMIT DROP")
            with cur.copy("COPY dup FROM STDIN") as cp:
                for (api, key), ((capi, ckey), _rule) in result.items():
                    cp.write_row((api, key, capi, ckey))
            cur.execute("UPDATE master m SET exclude_reasons = m.exclude_reasons || '{duplicate}',"
                        " canonical_api = d.capi, canonical_key = d.ckey"
                        " FROM dup d WHERE m.api = d.api AND m.key = d.key")
            quality_counts = quality.refresh(cur)
        conn.commit()
    by_rule: dict[str, int] = defaultdict(int)
    for _head, rule in result.values():
        by_rule[rule] += 1
    return {"status": "ok", "duplicate": len(result), **dict(sorted(by_rule.items())), **quality_counts}
