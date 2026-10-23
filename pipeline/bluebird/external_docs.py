"""최근 공식 자료 → external.doc(1건 = 1행, 출처 칸에 기관·서비스·번호).

- 정책뉴스 = 문화체육관광부 정책브리핑 정책뉴스(공공데이터포털 15095335). 조회 기간 3일 이하만 허용 → 3일씩
- 국회 법률안 = 국회사무처 열린국회정보 국회의원 발의법률안(nzmimeepazxkubdpn), 제안 이유 = 법제처 국민참여입법센터
  국회입법현황 페이지(의안번호별, 「제안이유 및 주요내용」 칸). 발의일이 범위 안인 것만
- 재실행 = 같은 id 덮어쓰기. 이미 받은 법률안 제안 이유는 다시 안 받음
"""

from __future__ import annotations

import html
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from . import db
from .egress import Egress
from .html_text import th_value

SOURCE = {
    "정책뉴스": "문화체육관광부 정책브리핑 정책뉴스 · 공공데이터포털 15095335(policyNewsService2/policyNewsList2)",
    "법률안": "국회사무처 열린국회정보 국회의원 발의법률안(nzmimeepazxkubdpn) · 제안 이유 = 법제처 국민참여입법센터 "
             "국회입법현황(opinion.lawmaking.go.kr/gcom/nsmLmSts/out/{의안번호}/detailRP)",
}
NEWS_API = "https://apis.data.go.kr/1371000/policyNewsService2/policyNewsList2"
BILL_API = "https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn"
BILL_PAGE = "https://opinion.lawmaking.go.kr/gcom/nsmLmSts/out/{no}/detailRP"
COLS = ("source", "id", "title", "date", "org", "url", "body")


def text_of(fragment: str | None) -> str | None:
    """HTML 조각 → 글. <br>·</p> = 줄바꿈, 태그 제거, 공백 정리."""
    t = re.sub(r"(?i)<br\s*/?>|</p>", "\n", fragment or "")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = "\n".join(" ".join(line.split()) for line in t.splitlines())
    return re.sub(r"\n{2,}", "\n", t).strip() or None


def _upsert(dsn: str, rows: list[tuple]) -> None:
    with db.connect(dsn) as conn:
        conn.cursor().executemany(
            f"INSERT INTO external.doc ({', '.join(COLS)}) VALUES ({', '.join(['%s'] * len(COLS))})"
            " ON CONFLICT (source, id) DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in COLS[2:])
            + ", fetched = now()", rows)
        conn.commit()


def news_rows(xml: bytes) -> list[tuple]:
    root = ET.fromstring(xml)
    code = root.findtext(".//resultCode")
    if code != "0":
        raise RuntimeError(f"정책뉴스 API {code} {root.findtext('.//resultMsg')}")
    out = []
    for it in root.iter("NewsItem"):
        g = lambda tag, it=it: (it.findtext(tag) or "").strip()
        when = datetime.strptime(g("ApproveDate"), "%m/%d/%Y %H:%M:%S").date() if g("ApproveDate") else None  # noqa: DTZ007
        body = "\n".join(x for x in (text_of(g("SubTitle1")), text_of(g("DataContents"))) if x) or None
        out.append((SOURCE["정책뉴스"], g("NewsItemId"), text_of(g("Title")) or g("NewsItemId"), when,
                    g("MinisterCode") or None, g("OriginalUrl") or None, body))
    return out


def news(*, dsn: str, egress: Egress, since: date, until: date, workers: int = 4) -> dict:
    spans = []
    d = since
    while d <= until:
        spans.append((d, min(d + timedelta(days=2), until)))
        d += timedelta(days=3)

    def one(span):
        # 초당 요청 제한(HTTP 429, 공공데이터포털) = 잠시 쉬고 다시
        for wait in (1, 3, 10, 30, None):
            r = egress.get("collect", NEWS_API,
                           params={"startDate": f"{span[0]:%Y%m%d}", "endDate": f"{span[1]:%Y%m%d}"},
                           secret_params={"serviceKey": os.environ["DATA_GO_KR_KEY"]})
            if r.status != 429 or wait is None:
                return news_rows(r.content)
            time.sleep(wait)
    with ThreadPoolExecutor(workers) as pool:
        rows = {r[1]: r for chunk in pool.map(one, spans) for r in chunk if r[1]}
    _upsert(dsn, list(rows.values()))
    return {"source": "정책뉴스", "status": "ok", "calls": len(spans), "rows": len(rows)}


def bills(*, dsn: str, egress: Egress, since: date, until: date, workers: int = 4) -> dict:
    key = os.environ["ASSEMBLY_KEY"]
    rows, page = [], 1
    while True:     # 발의일 최신순 → 범위 이전이 나오면 멈춤
        got = egress.get("collect", BILL_API, params={"Type": "json", "pIndex": page, "pSize": 1000, "AGE": "22"},
                         secret_params={"KEY": key}).json()["nzmimeepazxkubdpn"]
        items = got[1]["row"] if len(got) > 1 else []
        for b in items:
            when = date.fromisoformat(b["PROPOSE_DT"]) if b.get("PROPOSE_DT") not in (None, "None") else None
            if when and since <= when <= until:
                rows.append((SOURCE["법률안"], b["BILL_ID"], b["BILL_NAME"], when, b.get("PROPOSER"),
                             b.get("DETAIL_LINK"), None, b["BILL_NO"]))
        if not items or (items and min(r.get("PROPOSE_DT") or "9" for r in items) < f"{since}"):
            break
        page += 1
    with db.connect(dsn) as conn:
        have = {r[0] for r in conn.execute("SELECT id FROM external.doc WHERE source = %s AND body IS NOT NULL",
                                           (SOURCE["법률안"],))}

    def reason(row):
        if row[1] in have:
            return None
        page_ = egress.get("collect", BILL_PAGE.format(no=row[7])).text
        return row[:6] + (th_value(page_, "제안이유 및 주요내용") or None,)
    with ThreadPoolExecutor(workers) as pool:
        filled = [r for r in pool.map(reason, rows) if r]
    _upsert(dsn, filled)
    return {"source": "법률안", "status": "ok", "listed": len(rows), "rows": len(filled),
            "with_reason": sum(1 for r in filled if r[6])}


def collect(*, dsn: str, egress: Egress, since: date, until: date, kinds: tuple[str, ...] = tuple(SOURCE),
            workers: int = 4) -> list[dict]:
    out = []
    if "정책뉴스" in kinds:
        out.append(news(dsn=dsn, egress=egress, since=since, until=until, workers=workers))
    if "법률안" in kinds:
        out.append(bills(dsn=dsn, egress=egress, since=since, until=until, workers=workers))
    return out
