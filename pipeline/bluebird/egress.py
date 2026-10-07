"""업무망의 유일한 외부 출구(계획 §3.5, 원칙 3).

- HTTP 클라이언트는 이 모듈이 하나만 소유한다(trust_env=False, 프록시는 BLUEBIRD_EGRESS_PROXY만).
  다른 모듈은 httpx·requests·urllib·socket·LLM SDK를 import하지 않는다(tests/test_no_direct_http.py).
- 요청 본문은 이 모듈이 직접 만든다. 호출자는 "어느 소스의 어떤 필드"를 넘기고, 이 모듈이 반출 정책
  (source.export_grade + core.export_policy)을 검사한 뒤 본문을 직렬화한다. LLM도 SDK 없이 REST로 부른다.
- 보낸 본문의 sha256을 요청 훅에서 다시 계산해 미리 계산한 값과 다르면 막는다.
- 허용·차단 모두 core.egress_call에 1행씩 남긴다.

fields = 아이디어·원천 내용(반출 검사 대상). params = 페이지·날짜·키 같은 비내용 파라미터(검사 없이 기록만).
params에 아이디어 내용을 넣지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from . import db

PURPOSES = ("collect", "signal", "trace", "llm", "source_check")

# DMZ 프록시 화이트리스트와 같은 목록(deploy/test/proxy/squid.conf). 둘 다 바꾼다.
ALLOWED_HOSTS = (
    "data.go.kr", "law.go.kr", "kipris.or.kr", "k-startup.go.kr", "bizinfo.go.kr",
    "openapi.naver.com", "api.openai.com", "api.anthropic.com",
)

# export_grade='O' 소스에서 정책 행 없이도 나갈 수 있는 내용 필드. 그 밖은 core.export_policy에 명시해야 한다.
DEFAULT_EXPORTABLE = frozenset({
    "title", "body", "problem", "solution", "used_data", "missing_data", "category", "year", "domain",
    "dataset_title", "dataset_description", "announcement_title", "announcement_summary", "law_title",
})
# 어떤 정책으로도 나갈 수 없는 필드.
NEVER_EXPORT = frozenset({"team", "person_name", "objection_body", "contact", "review_note"})

LLM_ENDPOINTS = {
    "openai": ("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1/messages", "ANTHROPIC_API_KEY"),
}


class EgressError(Exception):
    """egress 호출 실패의 공통 부모. 호출자는 httpx를 import하지 않고 이것만 잡는다."""


class EgressBlocked(EgressError):
    pass


class EgressTransportError(EgressError):
    """네트워크·타임아웃 등 전송 실패(감사 행은 남는다)."""


class KeyMissing(EgressBlocked):
    pass


@dataclass
class Policy:
    """source_id → export_grade, (source_id|'*', field, purpose) → allowed."""
    grades: dict[str, str]
    rules: dict[tuple[str, str, str], bool] = field(default_factory=dict)

    @classmethod
    def load(cls, conn) -> Policy:
        grades = dict(conn.execute("SELECT id, export_grade FROM core.source"))
        rules = {(s, f, p): a for s, f, p, a in conn.execute(
            "SELECT source_id, field, purpose, allowed FROM core.export_policy")}
        return cls(grades, rules)

    def check(self, source_id: str, fname: str, purpose: str) -> str | None:
        """None이면 허용, 아니면 차단 사유."""
        if fname in NEVER_EXPORT:
            return f"{fname} is never exported"
        grade = self.grades.get(source_id)
        if grade is None:
            return f"unknown source {source_id}"
        if grade == "deny":
            return f"source {source_id} export_grade=deny"
        for key in ((source_id, fname, purpose), ("*", fname, purpose)):
            if key in self.rules:
                return None if self.rules[key] else f"export_policy denies {source_id}.{fname} for {purpose}"
        if grade == "O" and fname in DEFAULT_EXPORTABLE:
            return None
        return f"{source_id}.{fname} not allowed for {purpose} (export_grade={grade})"


Field = tuple[str, object]  # (source_id, value)


@dataclass
class Call:
    purpose: str
    dest_host: str
    path_template: str
    source_ids: list[str]
    fields_sent: list[str]
    payload_sha256: str | None = None
    bytes_out: int | None = None
    bytes_in: int | None = None
    http_status: int | None = None
    decision: str = "allowed"
    reason: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


def db_recorder(dsn: str) -> Callable[[Call], int]:
    def record(c: Call) -> int:
        with db.connect(dsn) as conn:
            rid = conn.execute(
                """INSERT INTO core.egress_call (purpose, dest_host, path_template, source_ids, fields_sent,
                     payload_sha256, bytes_out, bytes_in, http_status, decision, reason, tokens_in, tokens_out)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (c.purpose, c.dest_host, c.path_template, c.source_ids, c.fields_sent, c.payload_sha256,
                 c.bytes_out, c.bytes_in, c.http_status, c.decision, c.reason, c.tokens_in, c.tokens_out),
            ).fetchone()[0]
            conn.commit()
        return rid

    return record


def host_allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


@dataclass
class Response:
    status: int
    content: bytes
    headers: Mapping[str, str]
    url: str
    egress_call_id: int | None

    def json(self):
        return json.loads(self.content)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class Egress:
    def __init__(self, *, policy: Policy, recorder: Callable[[Call], int | None],
                 proxy: str | None = None, transport: httpx.BaseTransport | None = None,
                 timeout: float = 60.0, max_bytes: int = 300 * 1024 * 1024):
        proxy = (proxy if proxy is not None else os.environ.get("BLUEBIRD_EGRESS_PROXY")) or None
        self._policy = policy
        self._record = recorder
        self._max_bytes = max_bytes
        self._expected_sha: str | None = None
        self._client = httpx.Client(
            trust_env=False, proxy=proxy, transport=transport, timeout=timeout, follow_redirects=False,
            event_hooks={"request": [self._verify_body]},
            headers={"User-Agent": "bluebird-egress/1"},
        )

    @classmethod
    def from_dsn(cls, dsn: str, **kw) -> Egress:
        with db.connect(dsn) as conn:
            policy = Policy.load(conn)
        return cls(policy=policy, recorder=db_recorder(dsn), **kw)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ 내부
    def _verify_body(self, request: httpx.Request) -> None:
        sent = hashlib.sha256(request.read()).hexdigest()
        if self._expected_sha is not None and sent != self._expected_sha:
            raise EgressBlocked("request body differs from the body egress built")

    def _gate(self, purpose: str, fields: Mapping[str, Field]) -> tuple[list[str], list[str], str | None]:
        if purpose not in PURPOSES:
            raise ValueError(f"unknown purpose {purpose}")
        sources = sorted({s for s, _ in fields.values()})
        sent = sorted(f"{s}.{name}" for name, (s, _) in fields.items())
        for name, (s, _) in fields.items():
            reason = self._policy.check(s, name, purpose)
            if reason:
                return sources, sent, reason
        return sources, sent, None

    def _send(self, purpose: str, method: str, url: str, *, path_template: str | None,
              fields: Mapping[str, Field], params: Mapping[str, object] | None,
              body: bytes | None, headers: Mapping[str, str] | None,
              secret_params: Mapping[str, str] | None = None) -> Response:
        parts = urlsplit(url)
        sources, sent, reason = self._gate(purpose, fields)
        call = Call(purpose, parts.hostname or "", path_template or parts.path, sources, sent)
        if reason is None and not host_allowed(call.dest_host):
            reason = f"host {call.dest_host} not in allowlist"
        if reason is not None:
            call.decision, call.reason = "blocked", reason
            self._record(call)
            raise EgressBlocked(reason)
        call.payload_sha256 = hashlib.sha256(body).hexdigest() if body is not None else None
        call.bytes_out = len(body) if body is not None else 0
        q = {**(params or {}), **(secret_params or {})}
        self._expected_sha = hashlib.sha256(body or b"").hexdigest()
        try:
            resp = self._client.request(method, url, params=q or None, content=body, headers=headers)
            hops = 0
            while resp.is_redirect and hops < 5:
                nxt = resp.next_request
                if nxt is None or not host_allowed(nxt.url.host):
                    raise EgressBlocked(f"redirect to {nxt.url.host if nxt else '?'} not in allowlist")
                self._expected_sha = hashlib.sha256(nxt.read()).hexdigest()
                resp = self._client.send(nxt)
                hops += 1
            content = resp.read()
            if len(content) > self._max_bytes:
                raise EgressBlocked(f"response larger than {self._max_bytes} bytes")
        except EgressBlocked as e:
            call.decision, call.reason = "blocked", str(e)
            self._record(call)
            raise
        except httpx.HTTPError as e:
            call.reason = f"{type(e).__name__}: {e}"
            self._record(call)
            raise EgressTransportError(call.reason) from e
        finally:
            self._expected_sha = None
        call.http_status, call.bytes_in = resp.status_code, len(content)
        if purpose == "llm" and resp.status_code < 400:
            # 응답 형식이 이상해도 감사 행은 반드시 남긴다(본문은 이미 나갔다).
            try:
                usage = json.loads(content).get("usage") or {}
                call.tokens_in = usage.get("prompt_tokens", usage.get("input_tokens"))
                call.tokens_out = usage.get("completion_tokens", usage.get("output_tokens"))
            except (ValueError, AttributeError):
                call.reason = "unparseable LLM response"
        rid = self._record(call)
        return Response(resp.status_code, content, resp.headers, str(resp.url), rid)

    # ------------------------------------------------------------ 공개 API
    def get(self, purpose: str, url: str, *, params: Mapping[str, object] | None = None,
            fields: Mapping[str, Field] | None = None, path_template: str | None = None,
            secret_params: Mapping[str, str] | None = None,
            secret_headers: Mapping[str, str] | None = None) -> Response:
        """GET. fields 값은 쿼리 파라미터로 붙는다(반출 검사 후). secret_* 는 감사 행에 남지 않는 인증값."""
        fields = fields or {}
        q = {**(params or {}), **{k: v for k, (_, v) in fields.items()}}
        return self._send(purpose, "GET", url, path_template=path_template, fields=fields, params=q,
                          body=None, headers=secret_headers, secret_params=secret_params)

    def post_form(self, purpose: str, url: str, form: Mapping[str, str], *,
                  path_template: str | None = None) -> Response:
        """비내용 폼 POST(예: 파일 다운로드 토큰 요청). 아이디어 내용을 넣지 않는다."""
        body = "&".join(f"{httpx.QueryParams({k: v})}" for k, v in form.items()).encode()
        return self._send(purpose, "POST", url, path_template=path_template, fields={}, params=None,
                          body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})

    @staticmethod
    def build_llm_body(provider: str, model: str, system: str, instruction: str,
                       fields: Mapping[str, Field], max_tokens: int) -> bytes:
        user = instruction + "\n\n" + "\n".join(
            f"<{name}>\n{json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}\n</{name}>"
            for name, (_, v) in sorted(fields.items())
        )
        if provider == "openai":
            payload = {"model": model, "max_completion_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        elif provider == "anthropic":
            payload = {"model": model, "max_tokens": max_tokens, "system": system,
                       "messages": [{"role": "user", "content": user}]}
        else:
            raise ValueError(f"unknown provider {provider}")
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    def llm(self, *, provider: str, model: str, system: str, instruction: str,
            fields: Mapping[str, Field], max_tokens: int = 1500, purpose: str = "llm") -> tuple[str, Response]:
        """상용 LLM 호출. system·instruction은 코드에 고정된 지시문만(아이디어 내용 금지), 내용은 fields로만."""
        url, key_env = LLM_ENDPOINTS[provider]
        key = os.environ.get(key_env)
        if not key:
            raise KeyMissing(f"{key_env} not set")
        body = self.build_llm_body(provider, model, system, instruction, fields, max_tokens)
        headers = ({"Authorization": f"Bearer {key}", "Content-Type": "application/json"} if provider == "openai"
                   else {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
        resp = self._send(purpose, "POST", url, path_template=urlsplit(url).path, fields=fields, params=None,
                          body=body, headers=headers)
        if resp.status >= 400:
            raise EgressBlocked(f"{provider} HTTP {resp.status}: {resp.text[:300]}")
        data = resp.json()
        text = (data["choices"][0]["message"]["content"] if provider == "openai"
                else "".join(b.get("text", "") for b in data["content"]))
        return text, resp
