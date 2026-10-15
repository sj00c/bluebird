"""KIPRIS Plus 아이디어DB(ideaDBInfo) 전수 수집 → kipris_idea_api 어댑터용 CSV.

- `ideaName=%` 와일드카드 = 전체. docsStart 1부터 docsCount(≤100)씩. 38,563건 ≈ 387회(키 호출 한도 없음)
- 키 = drawingPath의 CN(관리번호) → 없으면 h:해시(원문 링크·제목·공모전·연도·주최). 해시 충돌(다른 내용) = 본문 해시 덧붙임
- 성명 필드 없음. originalLink = 원 공모전 상세 URL(허용 호스트만, 그 외 빈 값)
"""
from __future__ import annotations

import csv
import hashlib
import html
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

from .egress import Egress, EgressTransportError, KeyMissing

_URL = "http://plus.kipris.or.kr/openapi/rest/IdeaDBInfoService/ideaDBInfo"
_PAGE = 100
_CN = re.compile(r"[?&]CN=(\d{6,})")
_RETRY_WAIT = (3, 10, 30)   # 서버 끊김·5xx 재시도 간격(초)
FIELDS = ["key", "title", "year", "award", "contest", "host", "category", "body", "source_url", "ipc", "patent_applno"]
LINK_HOSTS = frozenset({"www.science.go.kr", "science.go.kr", "www.ssp.re.kr", "ssp.re.kr", "www.ip-edu.net", "ip-edu.net",
                        "www.kipa.org", "kipa.org"})


def _text(item: ET.Element, tag: str) -> str:
    value = html.unescape(item.findtext(tag) or "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(" ".join(line.split()) for line in value.split("\n")).strip()


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:16]


def _record(item: ET.Element) -> dict[str, str] | None:
    title = _text(item, "ideaName")
    if not title:
        return None
    year = _text(item, "contestYear")
    if not re.fullmatch(r"(19|20)\d{2}", year):
        year = ""
    link = _text(item, "originalLink")
    cn = _CN.search(_text(item, "drawingPath") or "")
    contest, host = _text(item, "contestName"), _text(item, "hostInstitution").replace("|", ", ")
    key = cn.group(1) if cn else "h:" + _digest(link, title, contest, year, host)
    source_url = link if link and urlsplit(link).hostname in LINK_HOSTS else ""
    award = _text(item, "awardInformation")
    return {
        "key": key, "title": title, "year": year, "award": "" if award == "-" else award,
        "contest": contest, "host": host, "category": _text(item, "technologyClassification"),
        "body": _text(item, "ideaContent"), "source_url": source_url,
        "ipc": ";".join(x.strip() for x in _text(item, "ipcCode").split(";") if x.strip()),
        "patent_applno": ";".join(x.strip() for x in _text(item, "interfaceApplicationNumber").split(";") if x.strip()),
    }


def download(*, source: dict, destination: Path, egress: Egress, previous: Path | None = None) -> dict:
    key = os.environ.get("KIPRIS_PLUS_KEY", "").strip()
    if not key:
        raise KeyMissing("KIPRIS_PLUS_KEY not set")
    interval = float(os.environ.get("BB_KIPRIS_INTERVAL", "0.3"))
    records: dict[str, dict[str, str]] = {}
    start, total, listed, untitled, calls = 1, None, 0, 0, 0
    while total is None or start <= total:
        time.sleep(interval)
        for attempt, wait in enumerate((*_RETRY_WAIT, None)):
            calls += 1
            try:
                response = egress.get("collect", _URL, params={"ideaName": "%", "docsCount": str(_PAGE), "docsStart": str(start)},
                                      secret_params={"accessKey": key}, path_template="/openapi/rest/IdeaDBInfoService/ideaDBInfo")
            except EgressTransportError as exc:
                if wait is None:
                    raise ValueError(f"KIPRIS ideaDBInfo transport failed at docsStart={start}: {exc}") from None
                time.sleep(wait)
                continue
            if response.status == 200:
                break
            if wait is None or response.status < 500:
                raise ValueError(f"KIPRIS ideaDBInfo HTTP {response.status} at docsStart={start}")
            time.sleep(wait)
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise ValueError(f"KIPRIS ideaDBInfo non-XML at docsStart={start}: {exc}") from None
        count_text = root.findtext(".//totalCount")
        if not count_text or not count_text.strip().isdigit():
            raise ValueError(f"KIPRIS ideaDBInfo missing totalCount: {response.text[:200]!r}")
        count = int(count_text)
        if total is not None and count != total:
            raise ValueError("KIPRIS ideaDBInfo totalCount changed during collection")
        total = count
        items = root.findall(".//ideaDBInfo")
        if len(items) != min(_PAGE, total - start + 1):
            raise ValueError(f"KIPRIS ideaDBInfo incomplete page at docsStart={start}: {len(items)}")
        for item in items:
            listed += 1
            record = _record(item)
            if record is None:
                untitled += 1
                continue
            if record["key"] in records:
                if records[record["key"]] == record:
                    continue
                if not record["key"].startswith("h:"):
                    raise ValueError(f"KIPRIS ideaDBInfo conflicting records for CN {record['key']}")
                record["key"] += ":" + _digest(record["body"], record["award"], record["category"])
                if record["key"] in records and records[record["key"]] != record:
                    raise ValueError(f"KIPRIS ideaDBInfo conflicting records for key {record['key']}")
            records[record["key"]] = record
        start += _PAGE
    if listed != total or not records:
        raise ValueError(f"KIPRIS ideaDBInfo listed {listed} of {total}")
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for k in sorted(records):
            writer.writerow(records[k])
    return {"rows": len(records), "listed": listed, "untitled": untitled, "duplicate_keys": listed - untitled - len(records),
            "calls": calls, "with_link": sum(1 for r in records.values() if r["source_url"]),
            "scope": "idea title/body/award/contest/classification/original link; no people"}
