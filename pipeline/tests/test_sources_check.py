import httpx
import pytest

from bluebird.egress import Egress, Policy
from bluebird.sources_check import REMOTES, check_remote

REM = {r.id: r for r in REMOTES}


class Rec:
    def __init__(self):
        self.calls = []

    def __call__(self, c):
        self.calls.append(c)
        return len(self.calls)


def _eg(handler, rec):
    return Egress(policy=Policy(grades={}), recorder=rec, proxy="", transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    for r in REMOTES:
        for k in r.key_env:
            monkeypatch.delenv(k, raising=False)


def test_keyless_401_is_key_required_and_audited():
    seen, rec = [], Rec()

    def h(req):
        seen.append(req)
        return httpx.Response(401, json={"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg": "SERVICE_KEY_IS_NULL"}}})

    r = check_remote(_eg(h, rec), REM["kstartup_announcement_15125364"])
    assert r["status"] == "key_required" and r["http_status"] == 401 and not r["keyed"]
    assert "serviceKey" not in str(seen[0].url)  # 키 없으면 키 파라미터도 없다
    assert rec.calls[0].purpose == "source_check" and rec.calls[0].fields_sent == []


def test_key_sent_but_not_recorded(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "SECRET123")
    seen, rec = [], Rec()

    def h(req):
        seen.append(req)
        return httpx.Response(200, json={"totalCount": 4321, "data": [{"biz_pbanc_nm": "공고"}]})

    r = check_remote(_eg(h, rec), REM["kstartup_announcement_15125364"])
    assert (r["status"], r["rows"], r["keyed"]) == ("ok", 4321, True)
    assert "SECRET123" in str(seen[0].url)
    assert "SECRET123" not in repr(rec.calls[0])


def test_header_key_wrong_is_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "bad")
    rec = Rec()
    seen = []

    def h(req):
        seen.append(req)
        return httpx.Response(401, json={"error": {"message": "Incorrect API key"}})

    r = check_remote(_eg(h, rec), REM["openai_api"])
    assert r["status"] == "error" and seen[0].headers["authorization"] == "Bearer bad"
    assert "bad" not in repr(rec.calls[0])


def test_network_failure_is_error_not_ok():
    def h(req):
        raise httpx.ConnectError("dns")

    r = check_remote(_eg(h, Rec()), REM["law_drf_eflaw"])
    assert r["status"] == "error" and "ConnectError" in r["sample"]


def test_law_drf_test_oc_counts():
    def h(req):
        assert req.url.params["OC"] == "test"
        return httpx.Response(200, json={"LawSearch": {"totalCnt": "5100", "law": [{"법령명한글": "x"}]}})

    r = check_remote(_eg(h, Rec()), REM["law_drf_eflaw"])
    assert (r["status"], r["rows"]) == ("ok", 5100) and "OC=test" in r["note"]
