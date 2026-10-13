import csv
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from bluebird import collect_proposals
from bluebird.anonymize import mask_contacts
from bluebird.egress import Egress, KeyMissing, Policy
from bluebird.sources import load_sources, mapped_contest_csv


def _egress(handler, calls=None):
    return Egress(policy=Policy({}), recorder=lambda call: (calls.append(call) if calls is not None else None),
                  proxy="", transport=httpx.MockTransport(handler))


def _rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_mask_contacts_keeps_ordinary_sentences():
    assert mask_contacts("제안자 본인이 직접 운영. 담당자에게 문의") == "제안자 본인이 직접 운영. 담당자에게 문의"
    assert mask_contacts("제안자: 홍길동, 010-1234-5678, x@y.kr") == "제안자 ○○, [전화], [이메일]"
    assert mask_contacts("신청인 이향자 외 8인") == "신청인 ○○ 외 8인"


# ------------------------------------------------------------------ 서울
def _seoul_page(service, rows, start, end, total):
    return {service: {"list_total_count": total, "RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"},
                      "row": rows[start - 1:end]}}


def test_seoul_joins_selection_and_merges_split_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("SEOUL_OPENAPI_KEY", "SECRETKEY")
    accepted = [
        {"FIS_YEAR": "2024", "SUGG_NO": "00001", "BIZ_NM": "골목길 &apos;안전&apos; 펜스", "SUBCOMM_NM": "교통",
         "PRO_INTENT": "보행자 안전", "PRO_INTENT1": "을 위한 제안\r\n제안자: 김민수 010-1111-2222",
         "BIZ_CONTENT1": "펜스 설치 1,000자", "BIZ_CONTENT2": "이어지는 내용", "MASTER_NO": ""},
        {"FIS_YEAR": "2024", "SUGG_NO": "00002", "BIZ_NM": "통폐합된 제안", "SUBCOMM_NM": "복지",
         "PRO_INTENT": "", "MASTER_NO": "00001"},
        {"FIS_YEAR": "2024", "SUGG_NO": "00003", "BIZ_NM": "", "SUBCOMM_NM": "복지"},
    ]
    selected = [{"FIS_YEAR": "2024", "SUGG_NO": "00001"}]
    calls = []

    def handler(request):
        assert "SECRETKEY" in request.url.path
        _, _, _, service, start, end, _ = request.url.path.split("/")
        rows = accepted if service == "bizSuggAcceptInfo" else selected
        return httpx.Response(200, json=_seoul_page(service, rows, int(start), int(end), len(rows)))

    destination = tmp_path / "seoul.csv"
    with _egress(handler, calls) as eg:
        result = collect_proposals.download_seoul(source={}, destination=destination, egress=eg)
    rows = _rows(destination)
    assert result["rows"] == 2 and result["awarded"] == 2 and len(rows) == 2
    first, second = rows
    assert first["key"] == "2024-00001" and first["title"] == "골목길 '안전' 펜스" and first["award"] == "선정"
    assert first["body"] == "[제안취지] 보행자 안전을 위한 제안\n제안자 ○○ [전화]\n[사업내용] 펜스 설치 1,000자이어지는 내용"
    assert second["award"] == "통폐합 선정" and second["body"] == ""
    text = destination.read_text(encoding="utf-8")
    assert "김민수" not in text and "010-1111" not in text and "SECRETKEY" not in text
    assert all("SECRETKEY" not in c.path_template and "{KEY}" in c.path_template for c in calls)


def test_seoul_requires_key(tmp_path, monkeypatch):
    monkeypatch.delenv("SEOUL_OPENAPI_KEY", raising=False)
    with _egress(lambda r: httpx.Response(500)) as eg, pytest.raises(KeyMissing):
        collect_proposals.download_seoul(source={}, destination=tmp_path / "x.csv", egress=eg)


# ------------------------------------------------------------------ 권익위
def _acrc_items(year, n):
    return {f"1AB-{year % 100:02d}01-{i:07d}": {
        "petiNo": f"1AB-{year % 100:02d}01-{i:07d}", "title": f"제안 {year}-{i}", "regDate": f"{year}.03.0{i % 9 + 1}. 10:00:00",
        "ancName": "보건복지부", "peterName": "박영희", "content": "현황", "improveIdea": "개선", "effect": "효과",
        "answerList": [{"ansContent": "박영희님 감사합니다"}], "fileList": None} for i in range(1, n + 1)}


def _acrc_handler(items, page_size=2, fail_after=None, unavailable=()):
    state = {"calls": 0}

    def handler(request):
        state["calls"] += 1
        if request.url.params.get("petiNo") in unavailable:
            return httpx.Response(200, json={"resultCode": "E03", "resultMessage": "조회된 데이터가 없습니다."})
        if fail_after is not None and state["calls"] > fail_after:
            return httpx.Response(200, text="<OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>22"
                                            "</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")
        q = request.url.params
        assert q.get("serviceKey") == "DGK"
        if request.url.path.endswith("OpenProposalList"):
            year = int(q["regFrom"][:4])
            listing = [v for v in items.values() if v["regDate"].startswith(str(year))]
            page = int(q["firstIndex"])
            chunk = listing[(page - 1) * page_size: page * page_size]
            return httpx.Response(200, json={"resultCode": "S00", "resultCount": str(len(listing)),
                                             "resultList": [{"petiNo": v["petiNo"], "title": v["title"][:5] + "..",
                                                             "regDate": v["regDate"]} for v in chunk]})
        return httpx.Response(200, json={"resultCode": "S00", "resultData": items[q["petiNo"]]})

    return handler, state


def test_acrc_fills_newest_year_first_and_merges_previous(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "DGK")
    monkeypatch.setenv("BB_ACRC_CALL_BUDGET", "6")
    items = {**_acrc_items(2025, 3), **_acrc_items(2024, 2)}
    handler, _ = _acrc_handler(items)
    source = {"acrc_from_year": 2024, "acrc_to_year": 2025}
    previous = tmp_path / "prev.csv"
    with _egress(handler) as eg:
        first = collect_proposals.download_acrc(source=source, destination=previous, egress=eg)
    rows = _rows(previous)
    # 예산 6 = 목록 1 + 건별 3(2025 완료) + 목록 1(2025 2쪽) → 2024는 예산 소진
    assert first["calls"] == 6 and first["fetched"] == 3 and first["stopped"] == "call budget exhausted"
    assert {r["year"] for r in rows} == {"2025"} and 2024 in first["incomplete_years"]
    body = rows[0]["body"]
    assert body == "[제안내용] 현황\n[개선방안] 개선\n[기대효과] 효과" and rows[0]["category"] == "보건복지부"
    assert "박영희" not in previous.read_text(encoding="utf-8")

    monkeypatch.setenv("BB_ACRC_CALL_BUDGET", "50")
    destination = tmp_path / "next.csv"
    with _egress(handler) as eg:
        second = collect_proposals.download_acrc(source=source, destination=destination, egress=eg,
                                                 previous=previous)
    assert second["previous_rows"] == 3 and second["fetched"] == 2 and second["stopped"] is None
    assert second["rows"] == 5 and sorted(r["year"] for r in _rows(destination)) == ["2024", "2024", "2025", "2025", "2025"]
    # 2025 완료 연도 = 목록 1회(건수 비교)만, 건별 재조회 없음
    assert second["calls"] == 1 + 1 + 2


def test_acrc_quota_error_keeps_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "DGK")
    monkeypatch.setenv("BB_ACRC_CALL_BUDGET", "100")
    handler, _ = _acrc_handler(_acrc_items(2025, 4), fail_after=3)
    destination = tmp_path / "acrc.csv"
    with _egress(handler) as eg:
        result = collect_proposals.download_acrc(source={"acrc_from_year": 2025, "acrc_to_year": 2025},
                                                 destination=destination, egress=eg)
    assert result["fetched"] == 2 and result["stopped"].endswith("failed") and len(_rows(destination)) == 2


def test_acrc_unavailable_item_becomes_placeholder_not_refetched(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "DGK")
    monkeypatch.setenv("BB_ACRC_CALL_BUDGET", "100")
    items = _acrc_items(2025, 3)
    handler, state = _acrc_handler(items, unavailable={"1AB-2501-0000002"})
    source = {"acrc_from_year": 2025, "acrc_to_year": 2025}
    destination = tmp_path / "acrc.csv"
    with _egress(handler) as eg:
        first = collect_proposals.download_acrc(source=source, destination=destination, egress=eg)
    assert first["rows"] == 2 and first["placeholders"] == 1 and first["unavailable"] == 1 and first["stopped"] is None
    rows = _rows(destination)
    assert [r["title"] for r in rows if r["key"] == "1AB-2501-0000002"] == [""]
    from bluebird.sources import SourceSpec, mapped_contest_csv
    spec = SourceSpec("acrc", "mapped_contest_csv", destination, "n", "l", "https://x.kr", 2, False,
                      record_kind="public_proposal",
                      columns={"key": "key", "title": "title", "year": "year", "body": ["body"]})
    assert len(list(mapped_contest_csv(spec, b"s" * 32))) == 2
    calls_before = state["calls"]
    with _egress(handler) as eg:
        second = collect_proposals.download_acrc(source=source, destination=tmp_path / "b.csv", egress=eg,
                                                 previous=destination)
    assert state["calls"] - calls_before == 1 and second["fetched"] == 0  # 목록 1회(건수 비교)만


def test_acrc_first_call_failure_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "DGK")
    with _egress(lambda r: httpx.Response(500)) as eg, pytest.raises(ValueError, match="first call"):
        collect_proposals.download_acrc(source={"acrc_from_year": 2025, "acrc_to_year": 2025},
                                        destination=tmp_path / "acrc.csv", egress=eg)


# ------------------------------------------------------------------ 경기
def test_gg_uses_browser_agent_and_records_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("GG_OPENAPI_KEY", "GGK")
    rows = [
        {"NO": 0, "RCPT_YR": "2020", "BIZ_NM": "작은 미술관", "PRP_DIV_NM": "도정참여형", "BIZ_LOC": "경기도",
         "SLCTN_YN_DIV": "선정", "FORMTN_BIZ_NM": "청소년수련시설 미술", "BUDGET_FORMTN_YR": "2021"},
        {"NO": 1, "RCPT_YR": "2020", "BIZ_NM": "생태 학습관", "PRP_DIV_NM": "지역지원형", "BIZ_LOC": "안양시",
         "SLCTN_YN_DIV": "", "FORMTN_BIZ_NM": "", "BUDGET_FORMTN_YR": "    "},
    ]

    def handler(request):
        assert request.headers["user-agent"].startswith("Mozilla/5.0") and request.url.params["KEY"] == "GGK"
        return httpx.Response(200, json={"tbggrpbudgresdntprpbizl": [
            {"head": [{"list_total_count": 2}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "ok"}}]},
            {"row": rows}]})

    destination = tmp_path / "gg.csv"
    calls = []
    with _egress(handler, calls) as eg:
        result = collect_proposals.download_gg(source={}, destination=destination, egress=eg)
    out = _rows(destination)
    assert result["rows"] == 2 and result["awarded"] == 1
    assert out[0]["award"] == "선정" and out[0]["body"] == "[편성사업명] 청소년수련시설 미술\n[예산편성연도] 2021"
    assert out[1]["category"] == "지역지원형 / 안양시" and out[1]["body"] == ""
    assert calls and calls[0].path_template == "/tbggrpbudgresdntprpbizl"


def test_gg_waf_html_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("GG_OPENAPI_KEY", "GGK")
    with _egress(lambda r: httpx.Response(200, text="<html>차단</html>")) as eg, pytest.raises(ValueError, match="non-JSON"):
        collect_proposals.download_gg(source={}, destination=tmp_path / "gg.csv", egress=eg)


def test_registry_loads_and_adapts_collector_output(tmp_path):
    from pathlib import Path

    from bluebird.sources import ADAPTERS, load_sources

    config = Path(__file__).resolve().parents[2] / "deploy" / "local" / "api-sources.toml"
    specs = {s.id: s for s in load_sources(config, tmp_path)}
    assert set(specs) == {"seoul_budget_proposals", "acrc_open_proposals", "gyeonggi_budget_proposals",
                          "seoul_law_proposals", "seoul_free_suggestions", "kipris_idea_api"}
    for sid, spec in specs.items():
        if spec.adapter != "mapped_contest_csv" or "source_url" in spec.columns:
            continue
        spec.path.write_text("key,title,year,award,category,body\n"
                             "k1,제안 하나,2024,선정,교통,\"[제안취지] 내용\"\n"
                             "k1,제안 하나,2024,선정,교통,\"[제안취지] 내용\"\n", encoding="utf-8")
        rows = list(ADAPTERS[spec.adapter](spec, b"s" * 32))
        assert len(rows) == 1 and rows[0]["body"] == "[제안취지] 내용" and rows[0]["year"] == 2024, sid
        assert rows[0]["source_url"] == spec.url and rows[0]["team_kind"] == "empty"


# ------------------------------------------------------------------ 서울 자유제안·법령제안
def test_seoul_law_and_free_suggestions(tmp_path, monkeypatch):
    monkeypatch.setenv("SEOUL_OPENAPI_KEY", "SECRETKEY")
    law = [{"SEQ": "B00294", "TITLE": "황사 국제법 제정", "RDATE": "2016-02-14 02:07:38", "INSTITUTION": "환경 정화",
            "GOVERNMENT1": "환경부", "CONTROVERSIAL": "황사 피해\r\n제안자: 김민수", "IMPROVEMENT": "국제법 요청",
            "FILEORINM": "김민수_제안서.hwp"},
           {"SEQ": "B00001", "TITLE": "", "RDATE": "2016-01-01", "CONTROVERSIAL": "x", "IMPROVEMENT": "y"}]
    free = [{"SN": 202964.0, "TITLE": "SNS 인증 &amp; 기프트\x08", "CONTENT": "https://idea.seoul.go.kr/front/freeSuggest/view.do?sn=202964",
             "REG_DATE": "2026-10-12 01:56:36.0", "VISIOIN_TXT": "교통", "VOTE_CNT": "3"},
            {"SN": 7, "TITLE": "링크 어긋남", "CONTENT": "https://evil.example/x", "REG_DATE": "2020-01-01", "VISIOIN_TXT": ""}]

    def handler(request):
        _, _, _, service, start, end, _ = request.url.path.split("/")
        rows = law if service == "LawsystemIdeaImporvement" else free
        return httpx.Response(200, json=_seoul_page(service, rows, int(start), int(end), len(rows)))

    law_csv, free_csv = tmp_path / "law.csv", tmp_path / "free.csv"
    with _egress(handler) as eg:
        r1 = collect_proposals.download_seoul_law(source={}, destination=law_csv, egress=eg)
        r2 = collect_proposals.download_seoul_free(source={}, destination=free_csv, egress=eg)
    row, = _rows(law_csv)
    assert r1["rows"] == 1 and row["key"] == "B00294" and row["category"] == "환경 정화"
    assert row["body"] == "[현황및문제점] 황사 피해\n제안자 ○○\n[개선방안] 국제법 요청"
    assert "김민수" not in law_csv.read_text(encoding="utf-8")
    rows = _rows(free_csv)
    assert r2["rows"] == 2 and rows[0]["key"] == "7" and rows[0]["source_url"].endswith("view.do?sn=7")
    assert rows[1]["title"] == "SNS 인증 & 기프트\x08" and rows[1]["body"] == "" and rows[1]["category"] == "교통"
    config = Path(__file__).resolve().parents[2] / "deploy" / "local" / "api-sources.toml"
    spec = replace(next(s for s in load_sources(config, tmp_path) if s.id == "seoul_free_suggestions"), path=free_csv)
    rec, = (r for r in mapped_contest_csv(spec, b"s" * 32) if r["title"].startswith("SNS"))
    assert rec["title"] == "SNS 인증 & 기프트"   # 제어문자 제거
    assert "evil.example" not in free_csv.read_text(encoding="utf-8")


# ------------------------------------------------------------------ KIPRIS 아이디어DB
def _kipris_xml(items, total):
    body = "".join(
        "<ideaDBInfo>" + "".join(f"<{k}>{v}</{k}>" for k, v in it.items()) + "</ideaDBInfo>" for it in items)
    return f'<?xml version="1.0" encoding="UTF-8"?><response><header/><body><items><totalCount>{total}</totalCount>{body}</items></body></response>'


def test_kipris_idea_db_pages_keys_and_adapter(tmp_path, monkeypatch):
    from bluebird import collect_kipris
    from bluebird.sources import SourceSpec, kipris_idea_api

    monkeypatch.setenv("KIPRIS_PLUS_KEY", "KPK")
    monkeypatch.setenv("BB_KIPRIS_INTERVAL", "0")
    base = {"awardInformation": "장려상", "contestName": "전국과학전람회", "contestYear": "1965",
            "hostInstitution": "미래창조과학부|국립중앙과학관", "ideaContent": "본문 &amp; 내용", "ipcCode": "B01J19/08;F02K",
            "interfaceApplicationNumber": " ", "openingDate": " ", "technologyClassification": "기타"}
    items = [
        {**base, "ideaName": "Plasma의 응용", "drawingPath": "http://x/getIdeaImage.jsp?CN=19650000010150&amp;seq=1",
         "originalLink": "http://www.science.go.kr/nalcoding/exhibit/boardview.jsp?view=2081"},
        {**base, "ideaName": "링크만 있는 건", "drawingPath": " ", "originalLink": "http://unknown.example/a",
         "interfaceApplicationNumber": "1020150012345"},
        {**base, "ideaName": "", "drawingPath": "http://x/?CN=3", "originalLink": "http://www.science.go.kr/x"},
        {**base, "ideaName": "링크만 있는 건", "drawingPath": " ", "originalLink": "http://unknown.example/a",
         "interfaceApplicationNumber": "1020150012345", "ideaContent": "같은 링크 다른 본문"},
        {**base, "ideaName": "링크만 있는 건", "drawingPath": " ", "originalLink": "http://unknown.example/a",
         "interfaceApplicationNumber": "1020150012345"},
    ]
    monkeypatch.setattr(collect_kipris, "_PAGE", 2)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.params["accessKey"] == "KPK" and request.url.params["ideaName"] == "%"
        start = int(request.url.params["docsStart"])
        return httpx.Response(200, text=_kipris_xml(items[start - 1:start + 1], len(items)))

    destination = tmp_path / "kipris.csv"
    with _egress(handler) as eg:
        result = collect_kipris.download(source={}, destination=destination, egress=eg)
    assert result == {"rows": 3, "listed": 5, "untitled": 1, "duplicate_keys": 1, "calls": 3, "with_link": 1,
                      "scope": "idea title/body/award/contest/classification/original link; no people"}
    rows = {r["key"]: r for r in _rows(destination)}
    hashed = sorted(k for k in rows if k.startswith("h:"))
    assert len(hashed) == 2 and hashed[1].startswith(hashed[0] + ":") and rows[hashed[1]]["body"] == "같은 링크 다른 본문"
    first = rows["19650000010150"]
    assert first["body"] == "본문 & 내용" and first["host"] == "미래창조과학부, 국립중앙과학관" and first["ipc"] == "B01J19/08;F02K"
    assert first["source_url"].startswith("http://www.science.go.kr/") and rows[hashed[0]]["source_url"] == ""

    spec = SourceSpec("kipris_idea_api", "kipris_idea_api", destination, "n", "l", "https://plus.kipris.or.kr", 1, False,
                      record_kind="contest_award", contest_name="KIPRIS", host_org="한국특허정보원")
    recs = {r["title"]: r for r in kipris_idea_api(spec, b"s" * 32) if r["body"] != "같은 링크 다른 본문"}
    assert recs["Plasma의 응용"]["extra"] == {"ipc": ["B01J19/08", "F02K"], "patent_applno": []}
    assert recs["링크만 있는 건"]["extra"]["patent_applno"] == ["1020150012345"]
    assert recs["링크만 있는 건"]["source_url"] == "https://plus.kipris.or.kr" and recs["Plasma의 응용"]["year"] == 1965


def test_kipris_retries_transport_and_5xx(tmp_path, monkeypatch):
    from bluebird import collect_kipris

    monkeypatch.setenv("KIPRIS_PLUS_KEY", "KPK")
    monkeypatch.setenv("BB_KIPRIS_INTERVAL", "0")
    monkeypatch.setattr(collect_kipris, "_RETRY_WAIT", (0, 0, 0))
    item = {"ideaName": "A", "drawingPath": "http://x/?CN=1234567", "contestYear": "2001", "contestName": "c",
            "hostInstitution": "h", "ideaContent": "b", "awardInformation": "", "technologyClassification": "",
            "ipcCode": "", "interfaceApplicationNumber": "", "originalLink": ""}
    seen = []

    def handler(request):
        seen.append(1)
        if len(seen) == 1:
            raise httpx.RemoteProtocolError("Server disconnected")
        if len(seen) == 2:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, text=_kipris_xml([item], 1))

    with _egress(handler) as eg:
        result = collect_kipris.download(source={}, destination=tmp_path / "k.csv", egress=eg)
    assert result["rows"] == 1 and result["calls"] == 3
    with _egress(lambda r: httpx.Response(403, text="denied")) as eg, pytest.raises(ValueError, match="HTTP 403"):
        collect_kipris.download(source={}, destination=tmp_path / "k.csv", egress=eg)
    assert len(seen) == 3


def test_kipris_total_change_or_short_page_raises(tmp_path, monkeypatch):
    from bluebird import collect_kipris

    monkeypatch.setenv("KIPRIS_PLUS_KEY", "KPK")
    monkeypatch.setenv("BB_KIPRIS_INTERVAL", "0")
    with _egress(lambda r: httpx.Response(200, text=_kipris_xml([], 5))) as eg, pytest.raises(ValueError, match="incomplete"):
        collect_kipris.download(source={}, destination=tmp_path / "k.csv", egress=eg)
    with _egress(lambda r: httpx.Response(200, text="<html>blocked</html>")) as eg, pytest.raises(ValueError, match="totalCount"):
        collect_kipris.download(source={}, destination=tmp_path / "k.csv", egress=eg)
