"""정제 DB(bluebird_master) 원본 적재: raw = 받은 그대로.

- 파일 소스: 수집해 둔 CSV·xlsx 행을 원본 헤더 그대로 payload로. 소스 단위 교체.
- API 소스: 응답 레코드 전체를 다시 받아 payload로. (source, key) 단위 갱신.
- 외부 호출 = egress(허용 호스트·감사 기록). 키 = 환경변수.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import time
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import openpyxl

from . import budget_detail, db
from .egress import Egress, EgressTransportError, KeyMissing
from .html_text import block, th_sections

Row = tuple[str, dict]   # (key, payload)


def registry(configs: list[Path]) -> list[dict]:
    """레지스트리 TOML들의 [[source]] 전부(id 중복 = 오류)."""
    out: dict[str, dict] = {}
    for path in configs:
        for s in tomllib.loads(path.read_text(encoding="utf-8")).get("source", []):
            if s["id"] in out:
                raise ValueError(f"duplicate source id {s['id']} in {path}")
            out[s["id"]] = s
    return list(out.values())


def _key(env: str) -> str:
    value = os.environ.get(env, "").strip()
    if not value:
        raise KeyMissing(f"{env} not set")
    return value


def _upsert(conn, source: str, rows: list[Row], fetched: datetime) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO raw (source, key, payload, fetched) VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (source, key) DO UPDATE SET payload = EXCLUDED.payload, fetched = EXCLUDED.fetched",
            [(source, k, json.dumps(p, ensure_ascii=False), fetched) for k, p in rows],
        )


# ---------------------------------------------------------------- 파일

def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("neither UTF-8 nor CP949")


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def read_file(path: Path) -> list[Row]:
    """첫 행 = 헤더. 'key' 열이 있으면(수집기 산출 CSV) 그 값, 없으면 데이터 행 번호(1부터)가 key."""
    if path.suffix == ".xlsx":
        sheet = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
        table = [[_cell(v) for v in row] for row in sheet.iter_rows(values_only=True)]
    else:
        table = list(csv.reader(io.StringIO(_decode(path.read_bytes()), newline="")))
    if not table:
        raise ValueError(f"{path.name}: empty")
    header = table[0]   # 원본 그대로(앞뒤 공백 포함, 레지스트리 매핑 = 정확한 헤더)
    if len(set(header)) != len(header):
        raise ValueError(f"{path.name}: duplicate header {header}")
    rows: list[Row] = []
    seen: set[str] = set()
    for n, values in enumerate(table[1:], start=1):
        if not any(v.strip() for v in values):
            continue
        if len(values) > len(header) and any(v.strip() for v in values[len(header):]):
            raise ValueError(f"{path.name}: row {n} has {len(values)} cells for {len(header)} headers")
        payload = dict(zip(header, values + [""] * (len(header) - len(values))))
        key = payload["key"] if "key" in payload else str(n)
        if key in seen:
            raise ValueError(f"{path.name}: duplicate key {key}")
        seen.add(key)
        rows.append((key, payload))
    return rows


def load_files(*, dsn: str, sources: list[dict], dirs: list[Path], only: str | None = None) -> list[dict]:
    """API 소스 제외 전부. 파일은 dirs 순서대로 찾음. 소스별 raw 행 교체."""
    results = []
    for s in sources:
        if s.get("collector") in API_COLLECTORS or "file" not in s or (only and s["id"] != only):
            continue
        path = next((d / s["file"] for d in dirs if (d / s["file"]).is_file()), None)
        if path is None:
            results.append({"source": s["id"], "status": "missing", "file": s["file"]})
            continue
        rows = read_file(path)
        fetched = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        with db.connect(dsn) as conn:
            conn.execute("DELETE FROM raw WHERE source = %s", (s["id"],))
            _upsert(conn, s["id"], rows, fetched)
            conn.commit()
        results.append({"source": s["id"], "status": "ok", "rows": len(rows), "file": path.name})
    return results


# ---------------------------------------------------------------- API

_SEOUL = "http://openapi.seoul.go.kr:8088"
_SEOUL_PAGE = 1000


def _seoul(egress: Egress, service: str, key_of: Callable[[dict], str]) -> Iterator[Row]:
    key = _key("SEOUL_OPENAPI_KEY")
    start, total = 1, None
    while total is None or start <= total:
        end = start + _SEOUL_PAGE - 1
        response = egress.get("collect", f"{_SEOUL}/{key}/json/{service}/{start}/{end}/",
                              path_template=f"/{{KEY}}/json/{service}/{{start}}/{{end}}/")
        data = response.json().get(service) if response.status == 200 else None
        if not data or data.get("RESULT", {}).get("CODE") != "INFO-000":
            raise ValueError(f"seoul {service} HTTP {response.status}: {response.text[:200]!r}")
        total = int(data["list_total_count"])
        for row in data.get("row") or []:
            yield key_of(row), row
        start = end + 1


def _seoul_budget(egress: Egress) -> Iterator[Row]:
    """접수(bizSuggAcceptInfo). 선정(bizSuggSelectionInfo)은 별도 소스 seoul_budget_selected로 같은 호출에서."""
    yield from _seoul(egress, "bizSuggAcceptInfo", lambda r: f"{r['FIS_YEAR']}:{r['SUGG_NO']}")


def _seoul_budget_selected(egress: Egress) -> Iterator[Row]:
    yield from _seoul(egress, "bizSuggSelectionInfo", lambda r: f"{r['FIS_YEAR']}:{r['SUGG_NO']}")


def _seoul_law(egress: Egress) -> Iterator[Row]:
    yield from _seoul(egress, "LawsystemIdeaImporvement", lambda r: str(r["SEQ"]))


def _seoul_free(egress: Egress) -> Iterator[Row]:
    yield from _seoul(egress, "ChunmanFreeSuggestions", lambda r: str(int(float(r["SN"]))))


_GG = "https://openapi.gg.go.kr/tbggrpbudgresdntprpbizl"
_GG_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _gg(egress: Egress) -> Iterator[Row]:
    """API에 고유번호 없음(NO = 0). key = 레코드 내용 해시(같은 내용 = 같은 행)."""
    key = _key("GG_OPENAPI_KEY")
    page, total, seen = 1, None, 0
    while total is None or seen < total:
        response = egress.get("collect", _GG, params={"Type": "json", "pIndex": str(page), "pSize": "1000"},
                              secret_params={"KEY": key}, secret_headers={"User-Agent": _GG_UA},
                              path_template="/tbggrpbudgresdntprpbizl")
        blocks = response.json().get("tbggrpbudgresdntprpbizl") if response.status == 200 else None
        if not blocks:
            raise ValueError(f"gg HTTP {response.status}: {response.text[:200]!r}")
        head = {k: v for h in blocks[0]["head"] for k, v in h.items()}
        if head.get("RESULT", {}).get("CODE") != "INFO-000":
            raise ValueError(f"gg: {head.get('RESULT')}")
        total = int(head["list_total_count"])
        chunk = blocks[1].get("row", []) if len(blocks) > 1 else []
        if not chunk:
            raise ValueError(f"gg: empty page {page} at {seen}/{total}")
        for row in chunk:
            stable = {k: v for k, v in row.items() if k != "DATA_COLCT_DE"}
            yield hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16], row
        seen += len(chunk)
        page += 1


_KIPRIS = "http://plus.kipris.or.kr/openapi/rest/IdeaDBInfoService/ideaDBInfo"
_CN = re.compile(r"[?&]CN=(\d{6,})")


def _kipris(egress: Egress) -> Iterator[Row]:
    """전수 387회 호출(키 호출 한도 없음). key = 도면 링크 CN, 없으면 레코드 해시."""
    key = _key("KIPRIS_PLUS_KEY")
    start, total = 1, None
    while total is None or start <= total:
        # 서버가 끊기거나 200으로 HTML 오류 페이지를 주는 경우가 있음 → 같은 페이지 재시도.
        for wait in (3, 10, 30, 60, 120, None):
            problem = None
            try:
                response = egress.get("collect", _KIPRIS, params={"ideaName": "%", "docsCount": "100",
                                                                  "docsStart": str(start)},
                                      secret_params={"accessKey": key},
                                      path_template="/openapi/rest/IdeaDBInfoService/ideaDBInfo")
                if response.status != 200:
                    problem = f"HTTP {response.status}"
                else:
                    root = ET.fromstring(response.text)
                    count = root.findtext(".//totalCount")
                    items = root.findall(".//ideaDBInfo")
                    if not (count or "").strip().isdigit() or not items:
                        problem = f"no records: {response.text[:200]!r}"
            except (EgressTransportError, ET.ParseError) as exc:
                problem = f"{type(exc).__name__}: {exc}"
            if problem is None:
                break
            if wait is None:
                raise ValueError(f"kipris page {start}: {problem}")
            time.sleep(wait)
        total = int(count)
        for item in items:
            row = {c.tag: c.text or "" for c in item}
            cn = _CN.search(row.get("drawingPath", ""))
            yield (cn.group(1) if cn else
                   "h:" + hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]), row
        start += 100


_ACRC = "http://apis.data.go.kr/1140100/OpenProposalService2"


def _acrc(egress: Egress, *, have: set[str], budget: int, years: range) -> Iterator[Row]:
    """국민신문고 공개제안. 목록(연 단위) → 건별 상세. 일 한도 → budget 회까지, 이미 받은 건(have) 건너뜀.
    상세가 없는 건(E03, 주로 이전 연도) = 목록 항목을 payload로."""
    key = _key("DATA_GO_KR_KEY")
    calls = 0

    def call(op: str, params: dict) -> dict | None:
        nonlocal calls
        calls += 1
        response = egress.get("collect", f"{_ACRC}/{op}", params=params, secret_params={"serviceKey": key},
                              path_template=f"/1140100/OpenProposalService2/{op}")
        try:
            return response.json() if response.status == 200 else None
        except ValueError:
            return None   # XML 오류 응답(한도 초과 등)

    for year in reversed(years):
        page, pages = 1, 1
        while page <= pages:
            if calls >= budget:
                return
            listing = call("OpenProposalList", {"regFrom": f"{year}0101", "regTo": f"{year}1231",
                                                "recordCountPerPage": "100", "firstIndex": str(page)})
            if not listing or listing.get("resultCode") != "S00":
                raise ValueError(f"acrc list {year} page {page}: {str(listing)[:200]}")
            pages = -(-int(listing["resultCount"]) // 100)
            for entry in listing.get("resultList") or []:
                peti = str(entry.get("petiNo", "")).strip()
                if not peti or peti in have:
                    continue
                if calls >= budget:
                    return
                item = call("OpenProposalItem", {"petiNo": peti})
                if item is None:
                    raise ValueError(f"acrc item {peti}: no JSON (quota?)")
                have.add(peti)
                yield peti, item["resultData"] if item.get("resultCode") == "S00" else entry
            page += 1


# 레지스트리 collector → (raw source, 수집 함수). 서울 시민참여예산 = 접수 + 선정 2개 소스.
API: dict[str, list[tuple[str, Callable[[Egress], Iterator[Row]]]]] = {
    "seoul_budget": [("seoul_budget_proposals", _seoul_budget), ("seoul_budget_selected", _seoul_budget_selected)],
    "seoul_law_proposal": [("seoul_law_proposals", _seoul_law)],
    "seoul_free_suggestion": [("seoul_free_suggestions", _seoul_free)],
    "gg_budget": [("gyeonggi_budget_proposals", _gg)],
    "kipris_idea_db": [("kipris_idea_api", _kipris)],
}
API_COLLECTORS = frozenset({*API, "acrc_open_proposal"})


# ---------------------------------------------------------------- 상세 페이지 본문
# 목록(API·크롤링)에 본문이 없는 소스 = 공식 상세 페이지에서 본문 영역 텍스트만.
# raw source = "<소스>.detail", key = 원 행 key, payload = {"url", "body"}(없으면 ""). 받은 key는 다시 안 받음.


_KIDP_FEATURE = re.compile(r"상품 주요특징\s*</th>\s*<td[^>]*>\s*한글\s*</td>\s*<td[^>]*>(.*?)</td>", re.DOTALL)


def _kidp_body(page: str) -> str:
    m = _KIDP_FEATURE.search(page)
    return html.unescape(re.sub(r"<[^>]+>", "\n", m.group(1))).strip() if m else ""


# 소스 → (허용 호스트, 원 행에서 상세 URL, 페이지에서 본문)
_KIDP = ("award.kidp.or.kr", lambda p: p.get("source_url", ""), _kidp_body)
# 과학관: 탐구·제작 요약(write-contents)만. 학교·수상자·지도교사 칸·첨부 = 받지 않음
_SCIENCE = ("www.science.go.kr", lambda p: p.get("source_url", ""),
            lambda page: block(page, "div", "write-contents"))
_GWANGJU = "https://yesan.gwangju.go.kr/pg/pgHomePPView.do?bpSn={}&pageId=yesan22"   # 제안순번 = bpSn
DETAIL: dict[str, tuple[str, Callable[[dict], str], Callable[[str], str]]] = {
    "seoul_free_suggestions": ("idea.seoul.go.kr", lambda p: p.get("CONTENT", ""),
                               lambda page: block(page, "div", "txt-block")),
    "kidp_good_design_projects": _KIDP,
    "kidp_korea_design_projects": _KIDP,
    "kidp_youth_design_projects": _KIDP,
    "science_exhibition_archive_2015_onward": _SCIENCE,
    "science_invention_archive_2015_onward": _SCIENCE,
    "gwangju_budget_proposals": ("yesan.gwangju.go.kr", lambda p: _GWANGJU.format(p.get("제안순번", "")),
                                 lambda page: th_sections(page, ("사업목적", "사업내용", "사업효과"))),
}


def load_detail(*, dsn: str, egress: Egress, only: str | None = None, workers: int = 4) -> list[dict]:
    results = []
    for source, (host, url_of, body_of) in DETAIL.items():
        if only and source != only:
            continue
        target = f"{source}.detail"
        with db.connect(dsn) as conn:
            todo = [(k, url_of(p)) for k, p in conn.execute(
                "SELECT r.key, r.payload FROM raw r WHERE r.source = %s AND NOT EXISTS"
                " (SELECT 1 FROM raw d WHERE d.source = %s AND d.key = r.key)", (source, target))]
        bad = [k for k, u in todo if urlsplit(u).hostname != host]
        if bad:
            raise ValueError(f"{source}: {len(bad)} rows without an official {host} URL (e.g. {bad[0]})")

        def fetch(item: tuple[str, str], body_of=body_of) -> Row | None:
            """삭제된 글(404) = 빈 본문으로 기록. 제한·장애(400·429·5xx·연결) = 기록 안 함 → 다음 실행에서 다시."""
            key, url = item
            for wait in (5, 30, 120, 300, None):
                try:
                    response = egress.get("collect", url, path_template=urlsplit(url).path)
                    if response.status == 200:
                        return key, {"url": url, "body": body_of(response.text)}
                    if response.status == 404:
                        return key, {"url": url, "body": ""}
                except EgressTransportError:
                    pass
                if wait is None:
                    return None
                time.sleep(wait)
            return None

        done = empty = failed = 0
        with db.connect(dsn) as conn, ThreadPoolExecutor(workers) as pool:
            batch: list[Row] = []
            for row in pool.map(fetch, todo):
                if row is None:
                    failed += 1
                    continue
                batch.append(row)
                empty += not row[1]["body"]
                if len(batch) >= 200:
                    _upsert(conn, target, batch, datetime.now(UTC))
                    conn.commit()
                    done += len(batch)
                    batch = []
            _upsert(conn, target, batch, datetime.now(UTC))
            conn.commit()
            done += len(batch)
        results.append({"source": target, "status": "ok" if not failed else "partial", "fetched": done,
                        "empty": empty, "failed": failed})
    for source, (host, crawl, fields_of, pair) in budget_detail.SOURCES.items():
        if only and source != only:
            continue
        # 사이트 번호 ≠ 원 행 key → 매번 사이트 전수 수집 후 다시 매칭(소스 단위 교체)
        target = f"{source}.detail"
        with db.connect(dsn) as conn:
            rows = [(k, fields_of(p)) for k, p in conn.execute("SELECT key, payload FROM raw WHERE source = %s",
                                                               (source,))]
        cands = crawl(egress, workers)
        if any(urlsplit(c["url"]).hostname != host for c in cands):
            raise ValueError(f"{source}: candidate URL outside {host}")
        paired = pair(rows, cands)
        out = [(k, {"url": c["url"] if c else "", "body": c["body"] if c else "", "match": how})
               for k, (c, how) in paired.items()]
        with db.connect(dsn) as conn:
            conn.execute("DELETE FROM raw WHERE source = %s", (target,))
            _upsert(conn, target, out, datetime.now(UTC))
            conn.commit()
        by_how: dict[str, int] = {}
        for _k, p in out:
            by_how[p["match"]] = by_how.get(p["match"], 0) + 1
        results.append({"source": target, "status": "ok", "site": len(cands), "rows": len(rows), **by_how,
                        "empty": sum(not p["body"] for _k, p in out)})
    return results


def load_api(*, dsn: str, egress: Egress, sources: list[dict], only: str | None = None,
             acrc_budget: int = 9000) -> list[dict]:
    results = []
    for s in sources:
        collector = s.get("collector")
        if only and s["id"] != only:
            continue
        if collector == "acrc_open_proposal":
            with db.connect(dsn) as conn:
                have = {k for (k,) in conn.execute("SELECT key FROM raw WHERE source = %s", (s["id"],))}
            before = len(have)
            batch: list[Row] = []
            fetched = datetime.now(UTC)
            with db.connect(dsn) as conn:
                for row in _acrc(egress, have=have, budget=acrc_budget,
                                 years=range(int(s["acrc_from_year"]), int(s["acrc_to_year"]) + 1)):
                    batch.append(row)
                    if len(batch) >= 200:   # 중간 중단(한도·장애)에도 받은 만큼 보존
                        _upsert(conn, s["id"], batch, fetched)
                        conn.commit()
                        batch = []
                _upsert(conn, s["id"], batch, fetched)
                conn.commit()
            results.append({"source": s["id"], "status": "ok", "new": len(have) - before, "total": len(have)})
            continue
        for source, fetch in API.get(collector, []):
            # 1,000건마다 커밋(중간 중단에도 받은 만큼 보존). 끝까지 받은 뒤에만 이번에 없던 행 삭제.
            fetched = datetime.now(UTC)
            keys: set[str] = set()
            listed = 0
            batch: dict[str, dict] = {}
            with db.connect(dsn) as conn:
                for key, payload in fetch(egress):
                    listed += 1
                    keys.add(key)
                    batch[key] = payload   # 같은 key 반복 = 마지막 값
                    if len(batch) >= 1000:
                        _upsert(conn, source, list(batch.items()), fetched)
                        conn.commit()
                        batch = {}
                _upsert(conn, source, list(batch.items()), fetched)
                stale = conn.execute("DELETE FROM raw WHERE source = %s AND fetched < %s", (source, fetched)).rowcount
                conn.commit()
            results.append({"source": source, "status": "ok", "rows": len(keys), "repeated": listed - len(keys),
                            "removed": stale})
    return results
