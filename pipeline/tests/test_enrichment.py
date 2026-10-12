"""Evidence boundaries and actual Egress/LLM/DB integration; no external requests."""
import json
import os
import uuid
from datetime import date

import httpx
import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from bluebird import cli, db, enrichment, funnel
from bluebird.egress import Egress, EgressBlocked, Policy, Response
from tests.test_db_integration import _seed_idea

IID = "ID-2019-aaaaaaaaaa"
BODY = "정책 지원 조건이 제한되어 사업화가 어렵다."


def response(data, status=200):
    content = data.encode() if isinstance(data, str) else json.dumps(data).encode()
    return Response(status, content, {}, "https://example.org", 1)


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    for key in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "KIPRIS_PLUS_KEY", "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY", "BB_LLM_PROVIDER"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("fn", [enrichment.trace_auto, enrichment.diagnose_auto, enrichment.score_auto])
def test_absent_keys_never_connect_or_classify(fn):
    result = fn(dsn="not-a-database")
    assert result["key_required"]
    assert result.get("processed", result.get("proposed")) == 0


@pytest.mark.parametrize("args", [["trace", "auto"], ["diagnose", "auto"], ["score", "auto"]])
def test_real_cli_reports_keys_without_database(args, capsys):
    assert cli.main([*args, "--dsn", "not-a-database", "--limit", "1"]) == 1
    assert "key_required" in capsys.readouterr().out


@pytest.mark.parametrize("limit", [0, -1, 21, True])
def test_automatic_runs_are_bounded(limit):
    with pytest.raises(ValueError):
        enrichment.trace_auto(dsn="not-a-database", limit=limit)


def test_field_mapping_checks_original_policy_name_and_audits_it():
    calls, requests = [], []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"total": 0, "items": []})
    with Egress(policy=Policy({"open": "O", "restricted": "pending"}), recorder=calls.append,
                transport=httpx.MockTransport(handle), proxy="") as eg:
        eg.get("trace", enrichment.NEWS_URL, fields={"title": ("open", "검색어")},
               field_params={"title": "query"}, params={"display": 10})
        assert requests[0].url.params["query"] == "검색어"
        assert "title" not in requests[0].url.params
        assert calls[0].fields_sent == ["open.title"]
        with pytest.raises(EgressBlocked):
            eg.get("trace", enrichment.NEWS_URL, fields={"title": ("restricted", "비공개")},
                   field_params={"title": "query"})
        with pytest.raises(ValueError):
            eg.get("trace", enrichment.NEWS_URL, fields={"title": ("open", "검색어")},
                   field_params={"title": "query"}, params={"query": "bypass"})
    assert len(requests) == 1


@pytest.mark.parametrize("payload", [{}, {"total": 0, "items": [{"title": "x"}]},
                                     {"total": 4, "items": []}, {"total": False, "items": []}])
def test_malformed_news_never_means_none(payload):
    with pytest.raises((ValueError, KeyError)):
        enrichment.news_candidates(response(payload))


def test_news_uses_only_actual_returned_http_links():
    total, hits = enrichment.news_candidates(response({"total": 1, "items": [
        {"title": "<b>사업</b>", "description": "실제 보도", "originallink": "https://news.example/a"}]}))
    assert total == 1 and hits[0]["url"] == "https://news.example/a" and hits[0]["title"] == "사업"
    assert enrichment.news_candidates(response({"total": 0, "items": []})) == (0, [])


def test_patent_empty_success_requires_explicit_valid_count():
    valid = "<response><header><resultCode>00</resultCode><successYN/></header><body><items/></body><count><totalCount>0</totalCount></count></response>"
    assert enrichment.patent_candidates(response(valid)) == (0, [])
    for invalid in (valid.replace("<totalCount>0</totalCount>", ""), valid.replace("00", "99"),
                    valid.replace("<successYN/>", "<successYN>N</successYN>"), "<response/>"):
        with pytest.raises(ValueError):
            enrichment.patent_candidates(response(invalid))


def test_patent_hits_keep_real_identifiers_without_inventing_urls():
    xml = """<response><header><resultCode>00</resultCode><successYN>Y</successYN></header>
    <body><items><item><applicationNumber>1019850010013</applicationNumber>
    <inventionTitle>회전체의센서</inventionTitle><applicantName>전송하지 않는 이름</applicantName>
    <registerStatus>소멸</registerStatus></item></items></body>
    <count><totalCount>1</totalCount></count></response>"""
    total, candidates = enrichment.patent_candidates(response(xml))
    assert total == 1
    assert candidates == [{"application_number": "1019850010013", "title": "회전체의센서",
                           "register_status": "소멸"}]
    with pytest.raises(ValueError):
        enrichment.patent_candidates(response(xml.replace("1019850010013", "invented")))


def diagnosis(**changes):
    return {"primary": "M", "secondary": None, "rationale": "정책 조건 제약", "evidence": [
        {"id": "body", "excerpt": BODY}], **changes}


@pytest.mark.parametrize("changes", [{"primary": "X"}, {"primary": "D"},
    {"evidence": [{"id": "body", "excerpt": "없는 문장"}]},
    {"evidence": [{"id": "https://invented.example", "excerpt": BODY}]},
    {"rationale": "https://invented.example"}, {"evidence": []}])
def test_diagnosis_rejects_unsupported_claims(changes):
    with pytest.raises(ValueError):
        enrichment.validate_diagnosis(diagnosis(**changes), BODY, [])


def test_diagnosis_uses_verbatim_source_evidence():
    assert enrichment.validate_diagnosis(diagnosis(), BODY, [])[0] == "M"
    assert enrichment.validate_diagnosis(diagnosis(primary="U", evidence=[]), BODY, [])[0] == "U"


def score_payload(value=4, ref="e1"):
    return {"scores": {"tech": None, "data": None, "regulation": None, "policy": value},
            "evidence": {"tech": None, "data": None, "regulation": None, "policy": ref}}


@pytest.mark.parametrize("value,ref", [(True, "e1"), (4.0, "e1"), (6, "e1"), (4, "https://invented.example"),
                                       (None, "e1"), (4, "e2")])
def test_scores_reject_bad_values_or_unknown_citations(value, ref):
    records = {"e1": {"axis": "policy", "url": "https://example.org/p"},
               "e2": {"axis": "tech", "url": "https://example.org/t"}}
    with pytest.raises(ValueError):
        enrichment.validate_scores(score_payload(value, ref), records)


def test_missing_axis_is_not_silently_filled():
    payload = score_payload()
    del payload["scores"]["tech"]
    with pytest.raises(ValueError):
        enrichment.validate_scores(payload, {})


def test_human_interpretation_is_authoritative():
    checks = {"manual": {"result": "none", "status": "award_only"}, "ip": {"result": "not_run"}}
    assert funnel.decide_trace("full_v1", checks, ("manual", "ip"))[0] == "award_only"
    checks.pop("manual")
    assert funnel.decide_trace("full_v1", checks, ("manual", "ip"))[0] == "pending"
    for result in ("found", "not_run"):
        checks = {"manual": {"result": "none"}, "ip": {"result": result}}
        assert funnel.decide_trace("full_v1", checks, ("manual",))[0] == "pending"


@pytest.fixture()
def isolated_db():
    base = os.environ.get("BB_TEST_DSN")
    if not base:
        pytest.skip("BB_TEST_DSN not set")
    name = "bb_enrichment_" + uuid.uuid4().hex[:12]
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute(psycopg.sql.SQL("CREATE DATABASE {} ").format(psycopg.sql.Identifier(name)))
    dsn = make_conninfo(base, dbname=name)
    try:
        db.migrate(dsn, "core")
        with psycopg.connect(dsn) as conn:
            _seed_idea(conn)
            conn.execute("UPDATE core.idea SET body=%s,source_url='https://example.org/idea' WHERE id=%s", (BODY, IID))
        yield dsn
    finally:
        with psycopg.connect(base, autocommit=True) as conn:
            conn.execute(psycopg.sql.SQL("DROP DATABASE {} WITH (FORCE)").format(psycopg.sql.Identifier(name)))


def test_real_trace_candidates_failed_search_and_manual_override(isolated_db, monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("KIPRIS_PLUS_KEY", "test-key")
    def handle(request):
        if request.url.host == "openapi.naver.com":
            assert request.url.params["query"] == "제목"
            return httpx.Response(200, json={"total": 1, "items": [
                {"title": "유사 사업", "description": "검색 후보", "link": "https://example.org/news"}]})
        assert request.url.params["word"] == "제목"
        return httpx.Response(503)
    with Egress.from_dsn(isolated_db, transport=httpx.MockTransport(handle), proxy="") as eg:
        result = enrichment.trace_auto(dsn=isolated_db, idea_id=IID, egress=eg)
        assert result["found"] == 1 and result["failed"] == 1
        with psycopg.connect(isolated_db) as conn:
            assert conn.execute("SELECT status FROM core.trace_verdict").fetchone()[0] == "pending"
            assert conn.execute("SELECT result FROM core.trace_check WHERE item='ip'").fetchone()[0] == "not_run"
        funnel.trace_manual(dsn=isolated_db, idea_id=IID, item="ip", result="none", status=None,
                            url=None, note="직접 특허 검색", by="reviewer")
        funnel.trace_manual(dsn=isolated_db, idea_id=IID, result="none", status="award_only",
                            url=None, note="후보를 확인함", by="reviewer")
        result = enrichment.trace_auto(dsn=isolated_db, idea_id=IID, egress=eg)
        assert result["preserved"] == 2
        with psycopg.connect(isolated_db) as conn:
            assert conn.execute("SELECT status FROM core.trace_verdict").fetchone()[0] == "award_only"


def test_p2_p3_real_llm_transport_and_human_preservation(isolated_db, monkeypatch):
    funnel.trace_manual(dsn=isolated_db, idea_id=IID, result="none", status=None,
                        url=None, note="검색 확인", by="reviewer")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    seen = []
    def handle(request):
        payload = json.loads(request.content)
        seen.append(payload)
        text = payload["messages"][1]["content"]
        answer = diagnosis() if "Classify" in text else score_payload()
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}],
                                        "usage": {"prompt_tokens": 10, "completion_tokens": 10}})
    with Egress.from_dsn(isolated_db, transport=httpx.MockTransport(handle), proxy="") as eg:
        assert enrichment.diagnose_auto(dsn=isolated_db, idea_id=IID, egress=eg)["proposed"] == 1
        with psycopg.connect(isolated_db) as conn:
            assert conn.execute('SELECT "primary",extractor,prompt_version,decided_by FROM core.diagnosis').fetchone() == ("M", "llm", "p2-v1", None)
        cid = funnel.change_add(dsn=isolated_db, kind="policy_news", url="https://example.org/policy",
                                title="지원 정책", occurred_at=date(2026, 1, 1), by="reviewer")
        funnel.match_set(dsn=isolated_db, idea_id=IID, change_id=cid, verdict="human",
                         what_changed=["정책 지원"], how_now="신청 가능", by="reviewer")
        assert enrichment.score_auto(dsn=isolated_db, idea_id=IID, egress=eg)["proposed"] == 1
        with psycopg.connect(isolated_db) as conn:
            row = conn.execute("SELECT policy,tech,verdict,scored_by FROM core.timeliness").fetchone()
            assert row[:3] == (4, None, "hold") and row[3].startswith("llm:")
            assert conn.execute("SELECT count(*) FROM core.publication").fetchone()[0] == 0
        funnel.diagnose_set(dsn=isolated_db, idea_id=IID, cause="M", rationale="사람 검토",
                            evidence=[("https://example.org/manual", BODY)], by="reviewer")
        # The original flag CLI still writes a human score, replacing the unapproved proposal.
        assert cli.main(["score", "--dsn", isolated_db, "--idea", IID, "--policy", "3",
                         "--policy-url", "https://example.org/manual", "--by", "reviewer"]) == 0
        assert enrichment.diagnose_auto(dsn=isolated_db, idea_id=IID, egress=eg)["proposed"] == 0
        assert enrichment.score_auto(dsn=isolated_db, idea_id=IID, as_of=date(2027, 1, 1), egress=eg)["proposed"] == 0
        assert len(seen) == 2
        with psycopg.connect(isolated_db) as conn:
            assert conn.execute("SELECT policy,scored_by FROM core.timeliness").fetchone() == (3, "reviewer")


def test_nonexportable_idea_is_never_sent(isolated_db, monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with psycopg.connect(isolated_db) as conn:
        conn.execute("UPDATE core.source SET export_grade='pending'")
    def no_request(request):
        pytest.fail("non-exportable source was sent")
    with Egress.from_dsn(isolated_db, transport=httpx.MockTransport(no_request), proxy="") as eg:
        assert enrichment.trace_auto(dsn=isolated_db, idea_id=IID, egress=eg)["processed"] == 0
        assert enrichment.diagnose_auto(dsn=isolated_db, idea_id=IID, egress=eg)["proposed"] == 0
        assert enrichment.score_auto(dsn=isolated_db, idea_id=IID, egress=eg)["proposed"] == 0
