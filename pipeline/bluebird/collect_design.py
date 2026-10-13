"""KIDP 공개 수상 갤러리 수집. 프로젝트 메타데이터만. 인물·이미지 제외."""
from __future__ import annotations

import csv
import html
import re
import time
from pathlib import Path
from urllib.robotparser import RobotFileParser

from .anonymize import mask_team
from .egress import Egress

_HOST = "https://award.kidp.or.kr"
_ENDPOINT = f"{_HOST}/Exhibit/selectHistorySearchList.json"
_GROUPS = {
    "1": {"우수디자인(GD)상품선정"},
    "2": {"대한민국디자인전람회"},
    "3": {"한국청소년디자인전람회", "대한민국디자인전람회(청소년)"},
}
_CATEGORIES = {"제품디자인", "공간/환경 디자인", "서비스/경험 디자인", "산업공예 디자인"}
_PRIZES = {"1": "대상", "2": "금상", "3": "은상", "4": "동상", "5": "특선"}
_FIELDS = ["key", "title", "year", "award", "contest", "category", "source_url"]


def _text(value) -> str:
    return " ".join(html.unescape(str(value or "")).split())


def _record(item: dict, group: str) -> dict[str, str] | None:
    key = str(item["idx_exhibit"])
    year = _text(item["year_info"])
    contest, category = _text(item["cdGubun"]), _text(item["exhibitCate1"])
    if not key.isdecimal() or not re.fullmatch(r"20\d{2}", year):
        raise ValueError("KIDP project ID/year schema changed")
    if contest not in _GROUPS[group] or category not in _CATEGORIES:
        raise ValueError("KIDP gallery returned an out-of-scope contest/category")
    title = _text(item["exhibit_title"])
    if not title:
        return None
    people = _text(item.get("apply_nm"))
    title = mask_team(title, ",".join(re.split(r"[\s,，、·/]+", people)))
    # 라벨 = 공식 갤러리 winners.js 그대로. 추정 순위 아님
    selected = "선정" if str(item.get("tp_awards")) == "1" else "입선"
    prize = _text(item.get("new_prize_nm"))
    if prize:
        prize = {"Special": "특선", "Winner": selected}.get(prize, prize)
    else:
        prize = _PRIZES.get(str(item.get("cd_prize")), "")
        if str(item.get("cd_prize")) == "6":
            prize = selected
    if not prize:
        raise ValueError("KIDP gallery record lacks a verified award label")
    return {"key": key, "title": title, "year": year, "award": prize,
            "contest": contest, "category": category,
            "source_url": f"{_HOST}/Exhibit/index_gd_view.do?idx_exhibit={key}"}


def download(*, source: dict, destination: Path, egress: Egress) -> dict:
    group = str(source["design_group"])
    if group not in _GROUPS or source["url"] != f"{_HOST}/Exhibit/winners.do?cd_gubun={group}":
        raise ValueError("kidp_awards requires a verified official gallery")
    response = egress.get("collect", f"{_HOST}/robots.txt")
    if response.status != 200:
        raise ValueError(f"KIDP robots.txt HTTP {response.status}")
    robots = RobotFileParser(f"{_HOST}/robots.txt")
    robots.parse(response.text.splitlines())
    if not robots.can_fetch("bluebird-egress/1", _ENDPOINT):
        raise ValueError("KIDP collection disallowed by robots.txt")
    interval = max(1.0, robots.crawl_delay("bluebird-egress/1") or 0)
    rate = robots.request_rate("bluebird-egress/1")
    if rate:
        interval = max(interval, rate.seconds / rate.requests)
    page, pages, expected_total = 1, 1, None
    records: dict[str, dict[str, str] | None] = {}
    while page <= pages:
        time.sleep(interval)
        response = egress.post_form("collect", _ENDPOINT, {
            "rows": "100", "page": str(page), "cdGubunList": group,
            "exhibitCate1List": "A,D,F,G",
        })
        if response.status != 200:
            raise ValueError(f"KIDP gallery HTTP {response.status}")
        data = response.json()
        total, page_count = int(data["realTotal"]), int(data["total"])
        if (int(data["page"]) != page or not 0 < page_count <= 1000
                or page_count != (total + 99) // 100
                or (expected_total is not None and total != expected_total)):
            raise ValueError("KIDP gallery pagination changed during collection")
        expected_total, pages = total, page_count
        rows = data["rows"]
        if not isinstance(rows, list) or len(rows) != min(100, total - (page - 1) * 100):
            raise ValueError("KIDP gallery returned an incomplete page")
        for item in rows:
            key = str(item["idx_exhibit"])
            if key in records:
                raise ValueError("KIDP gallery repeated a stable record ID")
            records[key] = _record(item, group)
        page += 1
    without_title = sum(record is None for record in records.values())
    if without_title == len(records) or len(records) != expected_total:
        raise ValueError("KIDP gallery record count mismatch or no titled projects")
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDS, lineterminator="\n")
        writer.writeheader()
        for key in sorted(records, key=int):
            if records[key] is not None:
                writer.writerow(records[key])
    return {"rows": len(records) - without_title, "listed": len(records),
            "excluded_without_title": without_title, "source_url": source["url"], "pages": pages,
            "categories": sorted(_CATEGORIES),
            "scope": "public project/award metadata; no people, contact details, images or attachments"}
