"""참여예산 원본 사이트 상세 본문: 목록 전수 → 상세 전수 → 원 행과 매칭(사이트 번호 ≠ 원 행 key).

raw '<소스>.detail' = 원 행마다 1행. payload = {url, body, match}
- match: exact(매칭 칸 전부 같음, 1:1) · order(같은 칸 여러 건 = 번호 순 짝) · loose(마지막 칸 빼고 유일) ·
  position(목록 순서 = 원 행 순서, 제목 확인) · none(사이트에 없음, url·body 빈 값)
- 매칭 칸 비교 = 글자·숫자만 소문자(dedup.title_key)
"""

from __future__ import annotations

import html
import re
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from urllib.parse import urlsplit

from .dedup import title_key
from .egress import Egress, EgressTransportError, Response
from .html_text import th_sections, th_value

Cand = dict   # id, url, body, fields(tuple) — fields = 매칭 칸(원 행과 같은 순서)


def _fetch(egress: Egress, url: str, *, params: dict | None = None, form: dict | None = None) -> Response | None:
    """제한·장애 = 재시도, 끝내 실패 = None."""
    for wait in (5, 30, 120, None):
        try:
            if form is None:
                r = egress.get("collect", url, params=params, path_template=urlsplit(url).path)
            else:
                r = egress.post_form("collect", url, form, path_template=urlsplit(url).path)
            if r.status == 200:
                return r
        except EgressTransportError:
            pass
        if wait is None:
            return None
        time.sleep(wait)
    return None


def _pages(fetch_page: Callable[[int], list], limit: int = 1000) -> list:
    """1쪽부터 빈 쪽이 나올 때까지."""
    out = []
    for page in range(1, limit):
        items = fetch_page(page)
        if not items:
            break
        out += items
    return out


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


# ---------------------------------------------------------------- 경기
_GG_LIST = "https://www.gg.go.kr/yesan/suggSttus/rceptBizList.do"
_GG_VIEW = "https://www.gg.go.kr/yesan/suggSttus/rceptBizInfo.do?suggNo={}&fisYear={}"


def gg_candidates(egress: Egress, years: range, workers: int) -> list[Cand]:
    ids = []
    for year in years:
        def page_ids(page: int, year=year) -> list:
            r = _fetch(egress, _GG_LIST, params={"fisYear": year, "pageIndex": page, "order": "rnum"})
            return re.findall(r"goRceptBizInfo\('(\d+)',\s*'(\d{4})'\)", r.text) if r else []
        ids += _pages(page_ids)

    def detail(item) -> Cand | None:
        sugg, year = item
        url = _GG_VIEW.format(sugg, year)
        r = _fetch(egress, url)
        if r is None:
            return None
        page = r.text
        return {"id": f"{year}:{sugg}", "url": url,
                "body": th_sections(page, ("사업목적", "사업내용", "사업효과")),
                "fields": (year, title_key(th_value(page, "제안명")), title_key(th_value(page, "사업지역")),
                           _digits(th_value(page, "소요예산(천원)")))}
    with ThreadPoolExecutor(workers) as pool:
        return [c for c in pool.map(detail, sorted(set(ids))) if c]


def gg_fields(p: dict) -> tuple:
    expn = p.get("BIZ_EXPN")
    return (str(p.get("RCPT_YR") or "").strip(), title_key(p.get("BIZ_NM")), title_key(p.get("BIZ_LOC")),
            str(int(float(expn))) if expn not in (None, "") else "")


# ---------------------------------------------------------------- 울산
_US_LIST = "https://www.ulsan.go.kr/s/jumin/bsnes/bsnesStatus/list.ulsan"
_US_VIEW = "https://www.ulsan.go.kr/s/jumin/bsnes/bsnesStatus/view.ulsan?mId=001003002000000000&bsnesId={}"


def ulsan_candidates(egress: Egress, years: range, workers: int) -> list[Cand]:
    ids = []
    for year in years:
        def page_ids(page: int, year=year) -> list:
            r = _fetch(egress, _US_LIST, params={"mId": "001003002000000000", "page": page, "bsnesYear": year})
            return [(i, str(year)) for i in dict.fromkeys(re.findall(r"bsnesId=(\d+)", r.text))] if r else []
        ids += _pages(page_ids)

    def detail(item) -> Cand | None:
        bid, year = item
        url = _US_VIEW.format(bid)
        r = _fetch(egress, url)
        if r is None:
            return None
        page = r.text
        return {"id": bid, "url": url, "body": th_sections(page, ("필요성", "사업내용", "기대효과")),
                "fields": (year, title_key(th_value(page, "사업명")), title_key(th_value(page, "사업위치")))}
    with ThreadPoolExecutor(workers) as pool:
        return [c for c in pool.map(detail, ids) if c]


def ulsan_fields(p: dict) -> tuple:
    return (_digits(p.get("년도", ""))[:4], title_key(p.get("사업명")), title_key(p.get("사업위치")))


# ---------------------------------------------------------------- 대전 유성구
_YS = "https://www.yuseong.go.kr/prog/bsnsPropse/yesan/sub02_01/{}.do"
YUSEONG_ROUND = "23"   # 2026년 주민참여예산 정기접수 = 공공데이터 파일 580행과 같은 회차


def yuseong_candidates(egress: Egress, workers: int) -> list[Cand]:
    def page_items(page: int) -> list:
        r = _fetch(egress, _YS.format("list"), form={"searchPssrpNo": YUSEONG_ROUND, "pageIndex": str(page)})
        return re.findall(r"fn_search_view\((\d+)\);\s*return false;\">([^<]*)</button>", r.text) if r else []
    items = _pages(page_items)

    def detail(item) -> Cand | None:
        no, title = item
        r = _fetch(egress, _YS.format("view"), form={"propseNo": no})
        if r is None:
            return None
        return {"id": no, "url": f"{_YS.format('view')}?propseNo={no}",
                "body": th_sections(r.text, ("불편한점", "개선방안", "기대효과")),
                "fields": (title_key(html.unescape(title)),)}
    with ThreadPoolExecutor(workers) as pool:
        return [c for c in pool.map(detail, items) if c]


def yuseong_fields(p: dict) -> tuple:
    return (title_key(p.get("제안사업명")),)


# ---------------------------------------------------------------- 매칭
def _natural(key: str) -> tuple:
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"(\d+)", key))


def match(rows: list[tuple[str, tuple]], cands: list[Cand]) -> dict[str, tuple[Cand | None, str]]:
    """원 행(key, 매칭 칸) ↔ 후보. 같은 칸 묶음끼리 번호 순 1:1, 남으면 마지막 칸 빼고 유일한 것만."""
    out: dict[str, tuple[Cand | None, str]] = {}
    by_full: dict[tuple, list[Cand]] = defaultdict(list)
    for c in sorted(cands, key=lambda c: _natural(c["id"])):
        by_full[c["fields"]].append(c)
    rows_by: dict[tuple, list[str]] = defaultdict(list)
    for key, f in rows:
        rows_by[f].append(key)
    used: set[str] = set()
    left = []
    for f, keys in rows_by.items():
        pool = by_full.get(f, [])
        how = "exact" if len(keys) == 1 and len(pool) == 1 else "order"
        for key, c in zip(sorted(keys, key=_natural), pool, strict=False):
            out[key] = (c, how)
            used.add(c["id"])
        left += [(k, f) for k in sorted(keys, key=_natural)[len(pool):]]
    if left and len(left[0][1]) > 1:
        loose: dict[tuple, list[Cand]] = defaultdict(list)
        for c in cands:
            if c["id"] not in used:
                loose[c["fields"][:-1]].append(c)
        for key, f in left:
            pool = loose.get(f[:-1], [])
            if len(pool) == 1:
                out[key] = (pool.pop(), "loose")
    for key, _f in rows:
        out.setdefault(key, (None, "none"))
    return out


def match_position(rows: list[tuple[str, tuple]], cands: list[Cand]) -> dict[str, tuple[Cand | None, str]]:
    """목록 순서 = 원 행 순서(key 1..n)일 때 같은 자리끼리 짝. 제목 같음 또는 한쪽이 다른 쪽을 포함해야 함
    (사이트에서 제목 보완: '관내 학생을 위한 경제교육' → '관평동 … 경제 교육 (관내 학생을 위한 경제교육)'). 나머지 = 제목 매칭."""
    ordered = sorted(rows, key=lambda r: _natural(r[0]))
    if len(ordered) != len(cands):
        return match(rows, cands)
    out: dict[str, tuple[Cand | None, str]] = {}
    left_rows, left_cands = [], []
    for (key, f), c in zip(ordered, cands, strict=True):
        a, b = f[0], c["fields"][0]
        if a and b and (a == b or a in b or b in a):
            out[key] = (c, "position")
        else:
            left_rows.append((key, f))
            left_cands.append(c)
    return {**out, **match(left_rows, left_cands)}


SOURCES: dict[str, tuple[str, Callable[[Egress, int], list[Cand]], Callable[[dict], tuple], Callable]] = {
    "gyeonggi_budget_proposals": ("www.gg.go.kr",
                                  lambda eg, w: gg_candidates(eg, range(2017, datetime.now(UTC).year + 2), w),
                                  gg_fields, match),
    "ulsan_budget_proposals": ("www.ulsan.go.kr",
                               lambda eg, w: ulsan_candidates(eg, range(2019, datetime.now(UTC).year + 2), w),
                               ulsan_fields, match),
    "yuseong_budget_proposals": ("www.yuseong.go.kr", yuseong_candidates, yuseong_fields, match_position),
}
