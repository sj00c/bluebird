import ast
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from bluebird import egress
from bluebird.egress import Egress, EgressBlocked, KeyMissing, Policy

PKG = Path(egress.__file__).parent
NET_MODULES = {"httpx", "requests", "urllib", "urllib3", "http", "aiohttp", "socket", "openai", "anthropic",
               "huggingface_hub", "sentence_transformers", "transformers", "ssl", "ftplib", "smtplib"}


def _imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module.split(".")[0])
    return out


def test_no_direct_http():
    """egress.py 말고는 네트워크·LLM SDK 모듈을 import하지 않는다."""
    offenders = {}
    for f in PKG.rglob("*.py"):
        bad = _imports(f) & NET_MODULES
        if f.name == "egress.py":
            bad -= {"httpx", "urllib"}  # urllib.parse(문자열 처리)만 사용
        if bad:
            offenders[str(f.relative_to(PKG))] = sorted(bad)
    assert offenders == {}


class Rec:
    def __init__(self):
        self.calls = []

    def __call__(self, c):
        self.calls.append(c)
        return len(self.calls)


POLICY = Policy(
    grades={"open": "O", "kipris": "pending", "secret": "deny"},
    rules={("kipris", "title", "trace"): True},
)


def _eg(handler, rec=None):
    return Egress(policy=POLICY, recorder=rec or Rec(), proxy="", transport=httpx.MockTransport(handler))


def _ok(req):
    return httpx.Response(200, json={"ok": True, "url": str(req.url)})


def test_open_source_title_allowed_and_recorded():
    rec = Rec()
    with _eg(_ok, rec) as eg:
        r = eg.get("trace", "https://openapi.naver.com/v1/search/news.json", fields={"title": ("open", "꽃 배송")})
    assert r.status == 200
    assert "%EA%BD%83" in r.json()["url"]  # 값이 쿼리로 나갔다
    c = rec.calls[-1]
    assert (c.decision, c.fields_sent, c.source_ids, c.http_status) == ("allowed", ["open.title"], ["open"], 200)


@pytest.mark.parametrize("fields,purpose,why", [
    ({"body": ("kipris", "본문")}, "trace", "export_grade=pending"),
    ({"title": ("kipris", "제목")}, "llm", "export_grade=pending"),   # 규칙은 trace만 허용
    ({"title": ("secret", "x")}, "trace", "deny"),
    ({"objection_body": ("open", "x")}, "llm", "never exported"),
    ({"team": ("open", "x")}, "trace", "never exported"),
    ({"title": ("nope", "x")}, "trace", "unknown source"),
])
def test_blocked_fields_never_leave(fields, purpose, why):
    sent = []
    rec = Rec()
    with _eg(lambda req: sent.append(req) or _ok(req), rec) as eg, pytest.raises(EgressBlocked, match=why):
        eg.get(purpose, "https://openapi.naver.com/x", fields=fields)
    assert sent == []
    assert rec.calls[-1].decision == "blocked"


def test_explicit_policy_rule_allows_pending_title_for_trace_only():
    with _eg(_ok) as eg:
        assert eg.get("trace", "https://plus.kipris.or.kr/x", fields={"title": ("kipris", "제목")}).status == 200


def test_host_outside_allowlist_blocked():
    rec = Rec()
    with _eg(_ok, rec) as eg, pytest.raises(EgressBlocked, match="allowlist"):
        eg.get("collect", "https://example.com/")
    assert rec.calls[-1].dest_host == "example.com"


def test_redirect_outside_allowlist_blocked():
    def handler(req):
        if req.url.host == "www.data.go.kr":
            return httpx.Response(302, headers={"Location": "https://evil.example/x"})
        return _ok(req)

    with _eg(handler) as eg, pytest.raises(EgressBlocked, match="redirect"):
        eg.get("collect", "https://www.data.go.kr/a")


def test_redirect_inside_allowlist_followed():
    def handler(req):
        if req.url.path == "/a":
            return httpx.Response(302, headers={"Location": "https://file.data.go.kr/b"})
        return httpx.Response(200, content=b"file")

    with _eg(handler) as eg:
        assert eg.get("collect", "https://www.data.go.kr/a").content == b"file"


def test_body_hash_mismatch_blocked():
    """egress가 만든 본문과 실제로 나가는 본문이 다르면 막는다."""
    rec = Rec()
    eg = _eg(_ok, rec)
    eg._client.event_hooks["request"].insert(0, lambda req: setattr(req, "_content", b"tampered"))
    with pytest.raises(EgressBlocked, match="differs"):
        eg.post_form("collect", "https://www.data.go.kr/x", {"a": "1"})
    assert rec.calls[-1].decision == "blocked"


def test_llm_body_built_by_egress_and_hash_recorded(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    seen = {}

    def handler(req):
        seen["body"] = req.read()
        seen["key"] = req.headers["x-api-key"]
        return httpx.Response(200, json={"content": [{"type": "text", "text": "{\"a\":1}"}],
                                         "usage": {"input_tokens": 11, "output_tokens": 3}})

    rec = Rec()
    with _eg(handler, rec) as eg:
        text, _ = eg.llm(provider="anthropic", model="m", system="sys", instruction="do",
                         fields={"title": ("open", "제목"), "body": ("open", "본문")})
    assert text == "{\"a\":1}"
    body = json.loads(seen["body"])
    assert body["system"] == "sys" and "<title>\n제목\n</title>" in body["messages"][0]["content"]
    c = rec.calls[-1]
    assert c.payload_sha256 == hashlib.sha256(seen["body"]).hexdigest()
    assert (c.tokens_in, c.tokens_out, c.purpose) == (11, 3, "llm")
    assert seen["key"] == "k"


def test_llm_without_key_raises_before_sending(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with _eg(_ok) as eg, pytest.raises(KeyMissing):
        eg.llm(provider="openai", model="m", system="s", instruction="i", fields={"title": ("open", "x")})


def test_client_ignores_environment_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://should-not-be-used:1")
    monkeypatch.delenv("BLUEBIRD_EGRESS_PROXY", raising=False)
    eg = Egress(policy=POLICY, recorder=Rec())
    assert eg._client._trust_env is False
    assert eg._client._mounts == {}
