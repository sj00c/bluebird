"""처리 작업 유일 외부 출구(계획 §3.5, 원칙 3).

- HTTP 클라이언트: 이 모듈 단일 소유(trust_env=False, 프록시 = BLUEBIRD_EGRESS_PROXY 지정 시만). 타 모듈 직접 네트워크 금지. urllib.parse 등 순수 URL 처리는 외부 호출 아님
- 요청 본문: 이 모듈이 생성. 호출자 = "소스·필드" 전달 → 반출 정책(source.export_grade + core.export_policy) 검사 → 직렬화. LLM도 SDK 없이 REST
- 전송 본문 sha256: 요청 훅에서 재계산, 사전값 불일치 시 차단
- 허용·차단 모두 기록 1건: 앱 = core.egress_call 1행, 정제 DB 명령 = 실행한 PC의 .runtime/egress-YYYY-MM.jsonl 1줄
- fields = 아이디어·원천 내용(반출 검사 대상) / params = 페이지·날짜·키 등 비내용(기록만). params에 아이디어 내용 금지
"""

from __future__ import annotations

import dataclasses
import hashlib
import http.cookiejar
import json
import os
import ssl
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import db

RUNTIME_DIR = Path(__file__).resolve().parents[2] / ".runtime"   # git 제외(실행 중 생성물)

PURPOSES = ("collect", "signal", "trace", "llm", "source_check")

# 외부 호출 허용 호스트. 목록 외 = 차단 + core.egress_call 기록
ALLOWED_HOSTS = (
    "data.go.kr", "law.go.kr", "kipris.or.kr", "k-startup.go.kr", "bizinfo.go.kr",
    "naverapihub.apigw.ntruss.com", "api.openai.com", "api.anthropic.com",
    "www.science.go.kr",
    "award.kidp.or.kr",
    "openapi.seoul.go.kr", "openapi.gg.go.kr",
    "idea.seoul.go.kr",
    # 참여예산 원본 사이트 상세 본문(master detail)
    "yesan.gwangju.go.kr", "www.gg.go.kr", "www.ulsan.go.kr", "www.yuseong.go.kr",
    # 최근 문제·바뀐 것 자료(docs/DEMAND_PLAN.md 6-1): 국회 의안·입법예고, 정부 입법예고·행정예고
    "open.assembly.go.kr", "www.lawmaking.go.kr", "opinion.lawmaking.go.kr",
)
# 과거 허용했다가 뺀 호스트. 새 호출 = 차단. 당시 허용 감사 행은 G10 반출 통제에서 위반으로 세지 않음
RETIRED_HOSTS = ("openapi.naver.com",)   # 2026-10-12 NAVER 검색 API → API HUB(naverapihub.apigw.ntruss.com)

# deny 아닌 소스에서 정책 행 없이 반출 가능한 내용 필드(pending = 차단 아님). 그 외 = core.export_policy 명시 필수
DEFAULT_EXPORTABLE = frozenset({
    "title", "body", "problem", "solution", "used_data", "missing_data", "category", "year", "domain",
    "dataset_title", "dataset_description", "announcement_title", "announcement_summary", "law_title", "change_title",
    "embedding_input",   # LLM이 만든 목표·해결책·기능을 이은 글(master.embedding_input)
})
# 어떤 정책으로도 나갈 수 없는 필드.
NEVER_EXPORT = frozenset({"team", "person_name", "contact", "review_note"})

LLM_ENDPOINTS = {
    "openai": ("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1/messages", "ANTHROPIC_API_KEY"),
}
EMBED_URL = "https://api.openai.com/v1/embeddings"


class EgressError(Exception):
    """egress 호출 실패의 공통 부모. 호출자는 httpx를 import하지 않고 이것만 잡는다."""


class EgressBlocked(EgressError):
    pass


class EgressTransportError(EgressError):
    """네트워크·타임아웃 등 전송 실패. 감사 행 유지."""


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
        if fname in DEFAULT_EXPORTABLE:
            return None
        return f"{source_id}.{fname} not allowed for {purpose} (export_grade={grade})"


Field = tuple[str | tuple[str, ...], object]  # (source_id 또는 여러 소스 내용을 한 칸에 모은 경우 source_id 묶음, value)


def _field_sources(source: str | tuple[str, ...]) -> tuple[str, ...]:
    return (source,) if isinstance(source, str) else tuple(source)


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


def file_recorder(directory: Path) -> Callable[[Call], None]:
    """호출 1건 = JSON 1줄, 월별 파일(egress-YYYY-MM.jsonl). 보낸 내용 원문 없음(칸 이름·sha256만)."""
    lock = threading.Lock()

    def record(c: Call) -> None:
        now = datetime.now(UTC)
        line = json.dumps({"at": now.isoformat(timespec="seconds"), **dataclasses.asdict(c)}, ensure_ascii=False)
        with lock:
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / f"egress-{now:%Y-%m}.jsonl").open("a", encoding="utf-8") as f:
                f.write(line + "\n")

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
                 timeout: float = 60.0, max_bytes: int = 300 * 1024 * 1024, cookies: bool = True):
        proxy = (proxy if proxy is not None else os.environ.get("BLUEBIRD_EGRESS_PROXY")) or None
        self._policy = policy
        self._record = recorder
        self._max_bytes = max_bytes
        # trust_env=False(프록시 환경변수 무시)여도 PC 지정 CA 묶음(SSL_CERT_FILE, 사내 TLS 검사 등)은 따름
        cafile = os.environ.get("SSL_CERT_FILE")
        self._client = httpx.Client(
            trust_env=False, proxy=proxy, transport=transport, timeout=timeout, follow_redirects=False,
            verify=ssl.create_default_context(cafile=cafile) if cafile else True,
            event_hooks={"request": [self._verify_body]},
            # cookies=False: 요청마다 새 세션(세션 단위로 호출 수를 제한하는 상세 페이지 대량 수집)
            cookies=None if cookies else http.cookiejar.CookieJar(http.cookiejar.DefaultCookiePolicy(allowed_domains=[])),
            headers={"User-Agent": "bluebird-egress/1"},
        )

    @classmethod
    def from_dsn(cls, dsn: str, **kw) -> Egress:
        with db.connect(dsn) as conn:
            policy = Policy.load(conn)
        return cls(policy=policy, recorder=db_recorder(dsn), **kw)

    @classmethod
    def for_master(cls, sources: list[dict] = (), log_dir: Path = RUNTIME_DIR, **kw) -> Egress:
        """정제 DB 명령 전용(core·DB 기록 없음): 정책 = 레지스트리 export_grade(칸 규칙 없음 →
        DEFAULT_EXPORTABLE·NEVER_EXPORT), 기록 = log_dir 파일."""
        grades = {s["id"]: s.get("export_grade", "pending") for s in sources}
        return cls(policy=Policy(grades), recorder=file_recorder(log_dir), **kw)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ 내부
    def _verify_body(self, request: httpx.Request) -> None:
        sent = hashlib.sha256(request.read()).hexdigest()
        expected = request.extensions.get("bb_body_sha")   # 요청별(스레드 공유 상태 없음)
        if expected is None or sent != expected:
            raise EgressBlocked("request body differs from the body egress built")

    def _gate(self, purpose: str, fields: Mapping[str, Field]) -> tuple[list[str], list[str], str | None]:
        if purpose not in PURPOSES:
            raise ValueError(f"unknown purpose {purpose}")
        pairs = [(s, name) for name, (src, _) in fields.items() for s in _field_sources(src)]
        sources = sorted({s for s, _ in pairs})
        sent = sorted({f"{s}.{name}" for s, name in pairs})
        for s, name in pairs:
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
        resp = None
        try:
            request = self._client.build_request(method, url, params=q or None, content=body, headers=headers)
            request.extensions["bb_body_sha"] = hashlib.sha256(body or b"").hexdigest()
            resp = self._client.send(request, stream=True)
            hops = 0
            while resp.is_redirect and hops < 5:
                nxt = resp.next_request
                if nxt is None or not host_allowed(nxt.url.host):
                    raise EgressBlocked(f"redirect to {nxt.url.host if nxt else '?'} not in allowlist")
                nxt.extensions["bb_body_sha"] = hashlib.sha256(nxt.read()).hexdigest()
                resp.close()
                resp = self._client.send(nxt, stream=True)
                hops += 1
            with BytesIO() as buffer:
                size = 0
                for chunk in resp.iter_bytes():
                    size += len(chunk)
                    if size > self._max_bytes:
                        raise EgressBlocked(f"response larger than {self._max_bytes} bytes")
                    buffer.write(chunk)
                content = buffer.getvalue()
        except EgressBlocked as e:
            call.decision, call.reason = "blocked", str(e)
            self._record(call)
            raise
        except httpx.HTTPError as e:
            call.reason = f"{type(e).__name__}: {e}"
            self._record(call)
            raise EgressTransportError(call.reason) from e
        finally:
            if resp is not None:
                resp.close()
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
            secret_headers: Mapping[str, str] | None = None,
            field_params: Mapping[str, str] | None = None) -> Response:
        """GET. field_params maps policy field names to API parameter names; values remain policy-gated."""
        fields = fields or {}
        mapping = field_params or {}
        if set(mapping) - fields.keys():
            raise ValueError("field_params contains unknown fields")
        names = [mapping.get(k, k) for k in fields]
        if any(not isinstance(k, str) or not k for k in names) or len(set(names)) != len(names):
            raise ValueError("field_params must have distinct nonempty parameter names")
        if set(names) & (set(params or {}) | set(secret_params or {})):
            raise ValueError("field parameters collide with static or secret parameters")
        q = {**(params or {}), **{mapping.get(k, k): v for k, (_, v) in fields.items()}}
        return self._send(purpose, "GET", url, path_template=path_template, fields=fields, params=q,
                          body=None, headers=secret_headers, secret_params=secret_params)

    def post_form(self, purpose: str, url: str, form: Mapping[str, str], *,
                  path_template: str | None = None) -> Response:
        """비내용 폼 POST(예: 파일 다운로드 토큰). 아이디어 내용 금지."""
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
            raise EgressBlocked(f"{provider} HTTP {resp.status}")  # 본문 미기록(키 일부 반환 가능)
        data = resp.json()
        text = (data["choices"][0]["message"]["content"] if provider == "openai"
                else "".join(b.get("text", "") for b in data["content"]))
        return text, resp

    def embed(self, *, model: str, source: str, texts: list[str], dimensions: int | None = None) -> list[list[float]]:
        """OpenAI 임베딩. 내용 = 칸 embedding_input(반출 검사·기록). 반환 순서 = 입력 순서."""
        key = os.environ.get(LLM_ENDPOINTS["openai"][1])
        if not key:
            raise KeyMissing(f"{LLM_ENDPOINTS['openai'][1]} not set")
        payload = {"model": model, "input": texts} | ({"dimensions": dimensions} if dimensions else {})
        resp = self._send("llm", "POST", EMBED_URL, path_template=urlsplit(EMBED_URL).path,
                          fields={"embedding_input": (source, texts)}, params=None,
                          body=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        if resp.status >= 400:
            raise EgressBlocked(f"openai embeddings HTTP {resp.status}")
        return [d["embedding"] for d in sorted(resp.json()["data"], key=lambda d: d["index"])]
