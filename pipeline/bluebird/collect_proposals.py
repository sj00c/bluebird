"""시민·국민 제안 OpenAPI 수집기 → mapped_contest_csv용 CSV. 제안자 성명·연락처 미기록.

- seoul_budget: 서울 시민참여예산 접수(bizSuggAcceptInfo) + 선정(bizSuggSelectionInfo) → award. 키 = URL 경로(감사 기록 제외)
- seoul_law_proposal: 서울 법령제도개선 제안(LawsystemIdeaImporvement). 현황·문제점 + 개선방안 본문
- seoul_free_suggestion: 상상대로 서울 자유제안(ChunmanFreeSuggestions). 제목·분야·상세 URL만(본문 = 상세 페이지)
- acrc_open_proposal: 국민권익위 공개제안(15059423). 목록(연 단위 창) → 건별 조회. 일 한도 → 호출 예산 내 증분, 이전 CSV와 병합
- gg_budget: 경기 주민참여예산 제안사업. 브라우저 UA 필수. 선정여부·편성사업명
"""
from __future__ import annotations

import csv
import html
import os
import re
from collections.abc import Callable
from pathlib import Path

from .anonymize import mask_contacts
from .egress import Egress, KeyMissing

_FIELDS = ["key", "title", "year", "award", "category", "body"]
_YEAR = re.compile(r"^(19|20)\d{2}$")


def _clean(value) -> str:
    """HTML 엔티티 해제, 줄바꿈 통일, 공백 정리. 분할 필드 연결 전후 공용."""
    text = html.unescape(str(value if value is not None else ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(" ".join(line.split()) for line in text.split("\n")).strip()


def _sections(parts: list[tuple[str, list[str]]]) -> str:
    """[라벨] 분할 조각 순서대로 연결(구분자 없음). 빈 섹션 생략."""
    out = []
    for label, pieces in parts:
        text = _clean("".join(str(p or "") for p in pieces))
        if text:
            out.append(f"[{label}] {text}")
    return mask_contacts("\n".join(out)) or ""


def _write(destination: Path, rows: list[dict[str, str]], fields: list[str] = _FIELDS) -> None:
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _key(env: str) -> str:
    key = os.environ.get(env, "").strip()
    if not key:
        raise KeyMissing(f"{env} not set")
    return key


# ---------------------------------------------------------------- 서울
_SEOUL = "http://openapi.seoul.go.kr:8088"
_SEOUL_PAGE = 1000
_SEOUL_SECTIONS = [
    ("제안취지", ["PRO_INTENT", "PRO_INTENT1", "PRO_INTENT2"]),
    ("사업내용", [f"BIZ_CONTENT{i}" for i in range(1, 8)]),
    ("사업효과", ["BIZ_EFFECT", "BIZ_EFFECT1", "BIZ_EFFECT2"]),
    ("기타", ["BIZ_ETC", "BIZ_ETC1", "BIZ_ETC2"]),
    ("협치기대효과", ["GOVE_EFFECT", "GOVE_EFFECT1", "GOVE_EFFECT2"]),
    ("협의공론과정", ["PROC_OPINION", "PROC_OPINION1", "PROC_OPINION2"]),
]


def _seoul_rows(egress: Egress, key: str, service: str) -> list[dict]:
    rows, start, total = [], 1, None
    while total is None or start <= total:
        end = start + _SEOUL_PAGE - 1
        response = egress.get("collect", f"{_SEOUL}/{key}/json/{service}/{start}/{end}/",
                              path_template=f"/{{KEY}}/json/{service}/{{start}}/{{end}}/")
        if response.status != 200:
            raise ValueError(f"seoul {service} HTTP {response.status}")
        data = response.json().get(service)
        if not data or data.get("RESULT", {}).get("CODE") != "INFO-000":
            raise ValueError(f"seoul {service}: {response.json()}")
        count = int(data["list_total_count"])
        if total is not None and count != total:
            raise ValueError(f"seoul {service}: total changed during collection")
        total = count
        page = data.get("row") or []
        if len(page) != min(_SEOUL_PAGE, total - start + 1):
            raise ValueError(f"seoul {service}: incomplete page at {start}")
        rows.extend(page)
        start = end + 1
    if len(rows) != total:
        raise ValueError(f"seoul {service}: {len(rows)} rows for total {total}")
    return rows


def download_seoul(*, source: dict, destination: Path, egress: Egress, previous: Path | None = None) -> dict:
    key = _key("SEOUL_OPENAPI_KEY")
    accepted = _seoul_rows(egress, key, "bizSuggAcceptInfo")
    selected = _seoul_rows(egress, key, "bizSuggSelectionInfo")
    chosen = {(str(r.get("FIS_YEAR")), str(r.get("SUGG_NO"))) for r in selected}
    records, awards = [], 0
    for r in accepted:
        year, no = str(r.get("FIS_YEAR", "")).strip(), str(r.get("SUGG_NO", "")).strip()
        title = mask_contacts(_clean(r.get("BIZ_NM"))) or ""
        if not _YEAR.match(year) or not no or not title:
            continue
        award = ""
        if (year, no) in chosen:
            award = "선정"
        elif (year, str(r.get("MASTER_NO", "")).strip()) in chosen:
            award = "통폐합 선정"
        awards += bool(award)
        records.append({
            "key": f"{year}-{no}", "title": title, "year": year, "award": award,
            "category": _clean(r.get("SUBCOMM_NM")),
            "body": _sections([(label, [r.get(f) for f in fields]) for label, fields in _SEOUL_SECTIONS]),
        })
    if not records:
        raise ValueError("seoul bizSuggAcceptInfo returned no titled proposals")
    records.sort(key=lambda x: x["key"])
    _write(destination, records)
    return {"rows": len(records), "listed": len(accepted), "selected": len(selected), "awarded": awards,
            "scope": "proposal text/category/selection only; no proposer, contact, department reviewer fields"}


def download_seoul_law(*, source: dict, destination: Path, egress: Egress, previous: Path | None = None) -> dict:
    key = _key("SEOUL_OPENAPI_KEY")
    rows = _seoul_rows(egress, key, "LawsystemIdeaImporvement")
    records = []
    for r in rows:
        seq, title = str(r.get("SEQ", "")).strip(), mask_contacts(_clean(r.get("TITLE"))) or ""
        year = str(r.get("RDATE", ""))[:4]
        if not seq or not title or not _YEAR.match(year):
            continue
        records.append({
            "key": seq, "title": title, "year": year, "award": "",
            "category": _clean(r.get("INSTITUTION")) or _clean(r.get("GOVERNMENT1")),
            "body": _sections([("현황및문제점", [r.get("CONTROVERSIAL")]), ("개선방안", [r.get("IMPROVEMENT")])]),
        })
    if not records:
        raise ValueError("seoul LawsystemIdeaImporvement returned no titled proposals")
    records.sort(key=lambda x: x["key"])
    _write(destination, records)
    return {"rows": len(records), "listed": len(rows),
            "scope": "proposal title/body/law only; no proposer, attachment names, progress remarks"}


_SEOUL_IDEA = "https://idea.seoul.go.kr/front/freeSuggest/view.do?sn="


def download_seoul_free(*, source: dict, destination: Path, egress: Egress, previous: Path | None = None) -> dict:
    key = _key("SEOUL_OPENAPI_KEY")
    rows = _seoul_rows(egress, key, "ChunmanFreeSuggestions")
    records = []
    for r in rows:
        sn = r.get("SN")   # API가 202969.0처럼 float로 줌
        sn = str(int(sn)) if isinstance(sn, (int, float)) and sn == int(sn) else str(sn or "").strip()
        title, year = mask_contacts(_clean(r.get("TITLE"))) or "", str(r.get("REG_DATE", ""))[:4]
        if not sn.isdecimal() or not title or not _YEAR.match(year):
            continue
        link = _clean(r.get("CONTENT"))
        records.append({
            "key": sn, "title": title, "year": year, "award": "",
            "category": _clean(r.get("VISIOIN_TXT")), "body": "",
            "source_url": link if link == f"{_SEOUL_IDEA}{sn}" else f"{_SEOUL_IDEA}{sn}",
        })
    if not records:
        raise ValueError("seoul ChunmanFreeSuggestions returned no titled proposals")
    records.sort(key=lambda x: int(x["key"]))
    _write(destination, records, [*_FIELDS, "source_url"])
    return {"rows": len(records), "listed": len(rows),
            "scope": "title/category/official detail URL only; body not fetched"}


# ---------------------------------------------------------------- 권익위
_ACRC = "http://apis.data.go.kr/1140100/OpenProposalService2"
_ACRC_PAGE = 100
_ACRC_SECTIONS = [("요약", "summary"), ("제안내용", "content"), ("개선방안", "improveIdea"),
                  ("기대효과", "effect"), ("기여", "contribution")]


class _Budget:
    def __init__(self, limit: int):
        self.limit, self.used = limit, 0

    def take(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


def _acrc_call(egress: Egress, key: str, op: str, params: dict) -> dict | None:
    """응답 JSON dict(resultCode 포함). 한도 초과·장애(HTTP 오류, XML 오류 응답) = None → 호출자가 진행분 보존 후 중단."""
    response = egress.get("collect", f"{_ACRC}/{op}", params=params, secret_params={"serviceKey": key},
                          path_template=f"/1140100/OpenProposalService2/{op}")
    if response.status != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None  # XML 오류 응답(한도 초과 22 등)


def _acrc_ok(data: dict | None) -> bool:
    return bool(data) and data.get("resultCode") == "S00"


def _acrc_record(item: dict) -> dict[str, str] | None:
    peti = str(item.get("petiNo", "")).strip()
    title = mask_contacts(_clean(item.get("title"))) or ""
    year = str(item.get("regDate", ""))[:4]
    if not peti or not title or not _YEAR.match(year):
        return None
    return {"key": peti, "title": title, "year": year, "award": "",
            "category": _clean(item.get("ancName")),
            "body": _sections([(label, [item.get(field)]) for label, field in _ACRC_SECTIONS])}


def download_acrc(*, source: dict, destination: Path, egress: Egress, previous: Path | None = None) -> dict:
    key = _key("DATA_GO_KR_KEY")
    start, end = int(source["acrc_from_year"]), int(source["acrc_to_year"])
    if not 2000 <= start <= end <= 2100:
        raise ValueError("acrc_from_year/acrc_to_year must be a sane range")
    budget = _Budget(int(os.environ.get("BB_ACRC_CALL_BUDGET", "9000")))
    stored: dict[str, dict[str, str]] = {}
    if previous is not None and previous.is_file():
        with previous.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                stored[row["key"]] = {f: row.get(f, "") for f in _FIELDS}
    before = len(stored)
    fetched, missing, stopped, incomplete = 0, 0, None, []
    for year in range(end, start - 1, -1):
        have = sum(1 for r in stored.values() if r["year"] == str(year))
        window = {"regFrom": f"{year}0101", "regTo": f"{year}1231", "recordCountPerPage": str(_ACRC_PAGE)}
        if not budget.take():
            stopped = "call budget exhausted"
            incomplete.append(year)
            continue
        first = _acrc_call(egress, key, "OpenProposalList", {**window, "firstIndex": "1"})
        if not _acrc_ok(first):
            if not stored and not fetched:
                raise ValueError("ACRC OpenProposalList failed on the first call (key, quota or service)")
            stopped = f"list {year} failed"
            incomplete.append(year)
            break
        total = int(first["resultCount"])
        if have >= total:
            continue
        page_size = len(first.get("resultList") or [])
        pages = (total + page_size - 1) // page_size if page_size else 0
        page, done = 1, False
        while page <= pages and not done:
            listing = first if page == 1 else None
            if listing is None:
                if not budget.take():
                    stopped = "call budget exhausted"
                    break
                listing = _acrc_call(egress, key, "OpenProposalList", {**window, "firstIndex": str(page)})
                if not _acrc_ok(listing):
                    stopped = f"list {year} page {page} failed"
                    break
            for entry in listing.get("resultList") or []:
                peti = str(entry.get("petiNo", "")).strip()
                if not peti or peti in stored:
                    continue
                if not budget.take():
                    stopped = "call budget exhausted"
                    done = True
                    break
                item = _acrc_call(egress, key, "OpenProposalItem", {"petiNo": peti})
                if item is None:
                    stopped = f"item {peti} failed"
                    done = True
                    break
                record = _acrc_record(item.get("resultData") or {}) if _acrc_ok(item) else None
                if record is None:
                    # E03(삭제·비공개 등) = 제목 없는 자리표시 행. 어댑터는 건너뛰고, 다음 실행에서 재조회 안 함
                    record = {"key": peti, "title": "", "year": str(entry.get("regDate", ""))[:4],
                              "award": "", "category": "", "body": ""}
                    missing += 1
                stored[peti] = record
                fetched += 1
            page += 1
        if stopped:
            incomplete.append(year)
            break
    if not stored:
        raise ValueError("ACRC collection produced no proposals")
    _write(destination, sorted(stored.values(), key=lambda r: r["key"]))
    titled = sum(1 for r in stored.values() if r["title"])
    return {"rows": titled, "placeholders": len(stored) - titled, "previous_rows": before, "fetched": fetched,
            "unavailable": missing, "calls": budget.used,
            "years": f"{start}-{end}", "incomplete_years": incomplete, "stopped": stopped,
            "scope": "proposal text/agency only; peterName, answers and attachments dropped"}


# ---------------------------------------------------------------- 경기
_GG = "https://openapi.gg.go.kr/tbggrpbudgresdntprpbizl"
_GG_PAGE = 1000
_GG_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def download_gg(*, source: dict, destination: Path, egress: Egress, previous: Path | None = None) -> dict:
    key = _key("GG_OPENAPI_KEY")
    rows, page, total = [], 1, None
    while total is None or (page - 1) * _GG_PAGE < total:
        response = egress.get("collect", _GG, params={"Type": "json", "pIndex": str(page), "pSize": str(_GG_PAGE)},
                              secret_params={"KEY": key}, secret_headers={"User-Agent": _GG_UA},
                              path_template="/tbggrpbudgresdntprpbizl")
        if response.status != 200:
            raise ValueError(f"gg HTTP {response.status}")
        try:
            payload = response.json()
        except ValueError:
            raise ValueError("gg returned non-JSON (WAF block or key error)") from None
        blocks = payload.get("tbggrpbudgresdntprpbizl")
        if not blocks:
            raise ValueError(f"gg: {str(payload)[:200]}")
        head = {k: v for h in blocks[0].get("head", []) for k, v in h.items()}
        if head.get("RESULT", {}).get("CODE") != "INFO-000":
            raise ValueError(f"gg: {head.get('RESULT')}")
        count = int(head["list_total_count"])
        if total is not None and count != total:
            raise ValueError("gg: total changed during collection")
        total = count
        chunk = blocks[1].get("row", []) if len(blocks) > 1 else []
        if len(chunk) != min(_GG_PAGE, total - (page - 1) * _GG_PAGE):
            raise ValueError(f"gg: incomplete page {page}")
        rows.extend(chunk)
        page += 1
    records, awards = [], 0
    for r in rows:
        title, year = mask_contacts(_clean(r.get("BIZ_NM"))) or "", _clean(r.get("RCPT_YR"))
        if not title or not _YEAR.match(year):
            continue
        award = _clean(r.get("SLCTN_YN_DIV"))
        awards += bool(award)
        formed, formed_year = _clean(r.get("FORMTN_BIZ_NM")), _clean(r.get("BUDGET_FORMTN_YR"))
        body = ""
        if formed:
            body = _sections([("편성사업명", [formed]), ("예산편성연도", [formed_year])])
        category = " / ".join(x for x in (_clean(r.get("PRP_DIV_NM")), _clean(r.get("BIZ_LOC"))) if x)
        records.append({"key": "", "title": title, "year": year, "award": award, "category": category, "body": body})
    if not records:
        raise ValueError("gg returned no titled proposals")
    _write(destination, records)
    return {"rows": len(records), "listed": len(rows), "awarded": awards,
            "scope": "proposal title/type/region/selection/formed project only; no people"}


COLLECTORS: dict[str, Callable[..., dict]] = {
    "seoul_budget": download_seoul,
    "seoul_law_proposal": download_seoul_law,
    "seoul_free_suggestion": download_seoul_free,
    "acrc_open_proposal": download_acrc,
    "gg_budget": download_gg,
}
