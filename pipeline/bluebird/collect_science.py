"""국립중앙과학관 공개 수상·작품 목록 메타데이터 수집. 첨부파일 제외.

- 게시판 2개 = 연도 검색 필드 상이. 설정 연도별 공식 10행 페이지네이션 준수
- 레코드 연도 = 필터로 추정 금지
- 개인 컬럼 = 마스킹용 임시 사용, CSV 미기록
"""
from __future__ import annotations

import csv
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.robotparser import RobotFileParser

from .anonymize import mask_team
from .egress import Egress

_HOST = "https://www.science.go.kr"
_BOARDS = {
    f"{_HOST}/mps/1079/bbs/423/moveBbsNttList.do": ("423", "aditfield7"),
    f"{_HOST}/mps/1075/bbs/424/moveBbsNttList.do": ("424", "aditfield1"),
}
_HEADERS = ["번호", "연도", "분야", "제목", "수상", "지도교사", "수상자"]
_FIELDS = ["key", "title", "year", "award", "source_url"]
_RECORD = re.compile(r"fn_moveBbsNttDetail\(\s*['\"](\d+)['\"]")
_SUMMARY = re.compile(r"전체\s*([\d,]+)\s*건,\s*현재 페이지\s*(\d+)\s*/\s*(\d+)")
_NON_PROJECT = re.compile(r"^\s*\(지도논문\)|수상작품\s*요약집|수상작품\s*모음집")


class _ArchivePage(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headers: list[str] = []
        self.records: list[tuple[str, list[str]]] = []
        self.summary: list[str] = []
        self._summary_depth = 0
        self._table = False
        self._key: str | None = None
        self._cells: list[str] = []
        self._cell: list[str] | None = None
        self._cell_tag = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            if self._summary_depth:
                self._summary_depth += 1
            elif "top-value" in attrs.get("class", "").split():
                self._summary_depth = 1
        if tag == "table" and attrs.get("id") == "bbsNttTable":
            self._table = True
        if not self._table:
            return
        if tag == "tbody":
            match = _RECORD.search(attrs.get("onclick", ""))
            self._key = match[1] if match else None
            self._cells = []
        elif tag == "th" or (tag == "td" and self._key is not None):
            self._cell = []
            self._cell_tag = tag
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data):
        if self._summary_depth:
            self.summary.append(data)
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "div" and self._summary_depth:
            self._summary_depth -= 1
        if not self._table:
            return
        if tag == self._cell_tag and self._cell is not None:
            value = " ".join("".join(self._cell).split())
            if tag == "th":
                self.headers.append(value)
            else:
                self._cells.append(value)
            self._cell = None
            self._cell_tag = ""
        elif tag == "tbody":
            if self._key is not None:
                self.records.append((self._key, self._cells))
            self._key = None
        elif tag == "table":
            self._table = False

    def counts(self) -> tuple[int, int, int]:
        match = _SUMMARY.search(" ".join(self.summary))
        if not match or self.headers != _HEADERS:
            raise ValueError("science archive list schema or pagination changed")
        total, page, pages = (int(value.replace(",", "")) for value in match.groups())
        if pages != max(1, (total + 9) // 10) or pages > 1000:
            raise ValueError("science archive pagination exceeds verified ten-row layout")
        if not 1 <= page <= pages:
            raise ValueError("science archive returned invalid current page")
        expected = min(10, max(0, total - (page - 1) * 10))
        if len(self.records) != expected or any(len(cells) != len(_HEADERS) for _, cells in self.records):
            raise ValueError("science archive returned incomplete or malformed records")
        return total, page, pages


def download(*, source: dict, destination: Path, egress: Egress) -> dict:
    """결정적 후보 CSV 작성. 검증·교체 = 수집 래퍼."""
    url = source["url"]
    if url not in _BOARDS:
        raise ValueError("science_archive requires a verified National Science Museum board URL")
    board, year_field = _BOARDS[url]
    start = source["science_start_year"]
    end = source["science_end_year"]
    if type(start) is not int or type(end) is not int or not 2015 <= start <= end <= 2100:
        raise ValueError("science archive requires an explicit 2015-or-later year range")
    robots_url = f"{_HOST}/robots.txt"
    response = egress.get("collect", robots_url)
    requests = 1
    interval = 1.0
    robots = None
    if response.status == 200:
        robots = RobotFileParser(robots_url)
        robots.parse(response.content.decode("utf-8", errors="strict").splitlines())
        if not robots.can_fetch("bluebird-egress/1", url):
            raise ValueError("science archive collection disallowed by robots.txt")
        interval = max(interval, robots.crawl_delay("bluebird-egress/1") or 0)
        rate = robots.request_rate("bluebird-egress/1")
        if rate:
            interval = max(interval, rate.seconds / rate.requests)
    elif response.status != 404:
        raise ValueError(f"science archive robots.txt HTTP {response.status}")

    rows: dict[str, dict[str, str]] = {}
    years: list[dict] = []
    for year in range(start, end + 1):
        page_no, pages, total = 1, 1, None
        scanned = skipped = duplicates = 0
        page_keys: set[tuple[str, ...]] = set()
        before = len(rows)
        while page_no <= pages:
            params = {"searchKrwd2": "entry", "searchCnd": year_field,
                      "searchKrwd": str(year), "page": page_no}
            if robots:
                from urllib.parse import urlencode
                if not robots.can_fetch("bluebird-egress/1", f"{url}?{urlencode(params)}"):
                    raise ValueError("science archive filtered page disallowed by robots.txt")
            time.sleep(interval)
            response = egress.get("collect", url, params=params)
            requests += 1
            if response.status != 200 or len(response.content) > 2 * 1024 * 1024:
                raise ValueError(f"science archive invalid response: HTTP {response.status}")
            parsed = _ArchivePage()
            parsed.feed(response.content.decode("utf-8", errors="strict"))
            found_total, current, found_pages = parsed.counts()
            if current != page_no or (total is not None and total != found_total):
                raise ValueError("science archive pagination changed during collection")
            total, pages = found_total, found_pages
            keys = tuple(key for key, _ in parsed.records)
            if keys in page_keys:
                raise ValueError("science archive repeated a page")
            page_keys.add(keys)
            for record_id, cells in parsed.records:
                scanned += 1
                _, raw_year, _, title, award, teacher, recipient = cells
                if raw_year and raw_year != str(year):
                    raise ValueError("science archive year filter returned an out-of-scope record")
                if not title:
                    raise ValueError("science archive project title is empty")
                if _NON_PROJECT.search(title):
                    skipped += 1
                    continue
                # 공식 셀 줄바꿈 = 이름별 분리 처리
                for people in (teacher, recipient):
                    title = mask_team(title, ",".join(re.split(r"[\s,，、·/]+", people)))
                key = f"{board}:{record_id}"
                row = {"key": key, "title": title, "year": raw_year, "award": award,
                       "source_url": url.replace("moveBbsNttList.do", "moveBbsNttDetail.do")
                                     + f"?nttSn={record_id}"}
                if key in rows:
                    if rows[key] != row:
                        raise ValueError("science archive stable record ID has conflicting metadata")
                    duplicates += 1
                else:
                    rows[key] = row
            page_no += 1
        if scanned != total:
            raise ValueError("science archive annual record count mismatch")
        years.append({"year_filter": year, "listed": total, "pages": pages,
                      "rows": len(rows) - before, "excluded_non_projects": skipped,
                      "duplicate_records": duplicates})
    if not rows:
        raise ValueError("science archive scope contains no public projects")
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDS, lineterminator="\n")
        writer.writeheader()
        for key in sorted(rows, key=lambda value: int(value.split(":", 1)[1])):
            writer.writerow(rows[key])
    return {"rows": len(rows), "source_url": url, "requests": requests, "years": years,
            "scope": "public entry-list metadata only; no attachments, people or school fields"}
