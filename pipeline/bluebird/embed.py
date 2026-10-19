"""아이디어 임베딩(2026-10-13 사용자 결정). 외부 호출 = egress.embed(용도 analysis)만.

- 대상: 비퇴역 + 실제 본문 50자 이상(구조 태그·글머리표·정형 머리말·본문 속 제목 제외, 공백 제외) = target_rows. 제목만 있는 기록은 넣지 않는다
- 입력: prep(title, body). 같은 입력(input_sha256)이면 다시 호출하지 않는다(증분)
- 저장: core.idea_embedding(idea_id, model=키, halfvec, dims). 벡터는 L2 정규화해 넣는다
- 키: provider:model:dims[:variant]. variant = notitle(본문에서 제목을 지운 입력, 평가용) | title(제목만, 평가 질의)
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from . import db
from .egress import Egress, EgressHTTPStatus, EgressTransportError

PREP_VERSION = 2   # 2: 깨진 글머리표(？)·개인 영역 글자(HWP 글머리 아이콘) 제거
MAX_CHARS = 6000
BATCH_CHARS = 150_000   # 요청 하나의 입력 글자 합 상한(OpenAI 요청당 30만 토큰 한도 아래)
RETRIES = 6


@dataclass(frozen=True)
class Model:
    provider: str
    model: str
    dims: int
    batch: int


MODELS = {
    "openai:text-embedding-3-large:3072": Model("openai", "text-embedding-3-large", 3072, 128),
    "openai:text-embedding-3-large:1536": Model("openai", "text-embedding-3-large", 1536, 128),
    "gemini:gemini-embedding-001:3072": Model("gemini", "gemini-embedding-001", 3072, 100),
    "gemini:gemini-embedding-2:3072": Model("gemini", "gemini-embedding-2", 3072, 100),
}
VARIANTS = ("notitle", "title")
# ⛔1 결정(2026-10-14 사용자): OpenAI 3-large, 1536차원(API dimensions = 앞부분 자르기+재정규화, 평가 A R@1 0.638·C lift 2.36)
DEFAULT_MODEL = "openai:text-embedding-3-large:1536"

MIN_BODY = 50   # 대상 = 정제·제목 제거 뒤 본문이 공백 빼고 50자 이상(2026-10-13 사용자 결정)

# 후보 = 원문 기준 50자+. 정제는 글자를 줄이기만 하므로 대상의 필요조건이다. 최종 판정은 body_len(target_rows)
CANDIDATE_SQL = """
    SELECT i.id, i.source_id, i.title, i.body FROM core.idea i
     WHERE i.retired_at IS NULL AND length(core.body_key(i.body)) >= 50
     ORDER BY i.id
"""

_TAG = re.compile(r"</?[A-Za-z][^>]*>")   # HTML 태그만(<전국 휴게소 …> 같은 한글 꺾쇠는 남김)
_BR = re.compile(r"<br\s*/?>|</p>", re.IGNORECASE)
_SECTION = re.compile(r"\[[^\]\n]{1,15}\]")        # [제안취지] [사업내용] 같은 구조 태그
_BULLET = re.compile(r"(?m)^\s*[○□■●◦▶·•❍․❖◆◇▷►\-]\s*")
_LOST_BULLET = re.compile(r"(?:^|(?<=\s))？(?=\s|$)")   # 인코딩에서 깨진 글머리표(예산 제안 " ？ … ？ ")
_PUA = re.compile(r"[\ue000-\uf8ff\U000f0000-\U000fffff]")   # 개인 영역 글자(HWP 글머리 아이콘 등)
_HEADER = re.compile(r"(?m)^\s*(발명\s*내용|발명\s*동기|발명의\s*효과|제안\s*취지|제안\s*내용|사업\s*내용|사업\s*효과"
                     r"|현황\s*및\s*문제점|개선\s*방안|기대\s*효과)\s*:?\s*$")   # 줄 전체가 정형 머리말
_SPACE = re.compile(r"\s+")


def clean(text: str | None, *, body: bool = True) -> str:
    """HTML 제거, 공백 정리. body=True면 구조 태그·글머리표·정형 머리말 줄도 지운다(제목에는 쓰지 않음)."""
    t = html.unescape(text or "")
    t = _BR.sub("\n", t)
    t = _TAG.sub(" ", t)
    if body:
        t = _SECTION.sub("\n", t)
        t = _PUA.sub(" ", t)
        t = _LOST_BULLET.sub("\n", t)
        t = _BULLET.sub("", t)
        t = _HEADER.sub("", t)
    return _SPACE.sub(" ", t).strip()


def prep(title: str, body: str | None) -> str:
    return (clean(title, body=False) + "\n\n" + clean(body))[:MAX_CHARS]


def strip_title(title: str, body: str) -> str:
    """본문 안의 제목 문자열(글자 사이 공백 무시)을 모두 지운다. 평가 A·B의 제목 누수 차단용."""
    chars = [re.escape(c) for c in re.sub(r"\s", "", clean(title, body=False))]
    if not chars:
        return body
    return _SPACE.sub(" ", re.sub(r"\s*".join(chars), " ", body)).strip()


def body_key_len(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def body_len(title: str, body: str | None) -> int:
    """대상 판정 길이: [제안취지] 같은 구조 태그·글머리표·정형 머리말과 본문 속 제목을 뺀 실제 본문 글자 수."""
    return body_key_len(strip_title(title, clean(body)))


def target_rows(conn) -> list[tuple[str, str, str, str]]:
    """(idea_id, source_id, title, body) — 임베딩·군집 대상 전부, id 순."""
    return [r for r in conn.execute(CANDIDATE_SQL) if body_len(r[2], r[3]) >= MIN_BODY]


def input_text(key: str, title: str, body: str | None) -> str:
    variant = parse_key(key)[1]
    if variant == "title":
        return clean(title, body=False)[:MAX_CHARS]
    if variant == "notitle":
        return strip_title(title, clean(body))[:MAX_CHARS]
    return prep(title, body)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def parse_key(key: str) -> tuple[str, str | None]:
    """키 → (기본 모델 키, variant)."""
    base, _, variant = key.rpartition(":")
    if variant in VARIANTS and base in MODELS:
        return base, variant
    if key in MODELS:
        return key, None
    raise ValueError(f"unknown model key {key!r} (known: {', '.join(MODELS)})")


def task_type(m: Model, variant: str | None) -> str | None:
    if m.provider != "gemini":
        return None
    return "RETRIEVAL_QUERY" if variant == "title" else "RETRIEVAL_DOCUMENT"


def config_sha(key: str) -> str:
    base, variant = parse_key(key)
    m = MODELS[base]
    return sha(json.dumps([m.provider, m.model, m.dims, task_type(m, variant), PREP_VERSION]))


def normalize(v: Sequence[float]):
    import numpy as np

    a = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(a))
    return a / n if n > 0 else a


def _batches(rows: Sequence[tuple[str, str, str]], size: int) -> Iterable[list[tuple[str, str, str]]]:
    batch: list[tuple[str, str, str]] = []
    chars = 0
    for r in rows:
        if batch and (len(batch) >= size or chars + len(r[2]) > BATCH_CHARS):
            yield batch
            batch, chars = [], 0
        batch.append(r)
        chars += len(r[2])
    if batch:
        yield batch


def _call(eg: Egress, m: Model, variant: str | None, batch: list[tuple[str, str, str]], sleep=time.sleep):
    field = "title" if variant == "title" else "body"
    for attempt in range(RETRIES):
        try:
            return eg.embed(provider=m.provider, model=m.model, dims=m.dims, task_type=task_type(m, variant),
                            items=[(field, sid, text) for _, sid, text in batch])
        except EgressHTTPStatus as e:
            if e.status != 429 and e.status < 500 or attempt == RETRIES - 1:
                raise
        except EgressTransportError:
            if attempt == RETRIES - 1:
                raise
        sleep(min(60, 2 ** attempt))
    raise AssertionError("unreachable")


def ensure(conn, eg: Egress, key: str, rows: Sequence[tuple[str, str, str, str | None]],
           sleep=time.sleep) -> dict[str, int]:
    """rows = (idea_id, source_id, title, body). 없거나 입력이 바뀐 것만 임베딩해 넣는다. 배치마다 commit."""
    from pgvector import HalfVector
    from pgvector.psycopg import register_vector

    register_vector(conn)
    base, variant = parse_key(key)
    m = MODELS[base]
    have = dict(conn.execute("SELECT idea_id, input_sha256 FROM core.idea_embedding WHERE model = %s", (key,)))
    todo = []
    for iid, sid, title, body in rows:
        text = input_text(key, title, body)
        if not text:
            raise ValueError(f"empty embedding input for {iid} ({key})")
        if have.get(iid) != sha(text):
            todo.append((iid, sid, text))
    csha = config_sha(key)
    out = {"embedded": 0, "unchanged": len(rows) - len(todo), "calls": 0, "chars": sum(len(t) for *_, t in todo)}
    for batch in _batches(todo, m.batch):
        vecs, resp = _call(eg, m, variant, batch, sleep)
        out["calls"] += 1
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO core.idea_embedding (idea_id, model, model_sha256, vec, dims, input_sha256,
                                                    egress_call_id, embedded_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                   ON CONFLICT (idea_id, model) DO UPDATE SET model_sha256 = EXCLUDED.model_sha256,
                     vec = EXCLUDED.vec, dims = EXCLUDED.dims, input_sha256 = EXCLUDED.input_sha256,
                     egress_call_id = EXCLUDED.egress_call_id, embedded_at = now()""",
                [(iid, key, csha, HalfVector(normalize(v)), m.dims, sha(text), resp.egress_call_id)
                 for (iid, _, text), v in zip(batch, vecs, strict=True)])
        conn.commit()
        out["embedded"] += len(batch)
    return out


def run(dsn: str, key: str, *, eg: Egress | None = None) -> dict[str, int]:
    """대상 전량을 키 하나로 적재. 대상 밖이 된 같은 키 행은 지운다(variant 키 행은 건드리지 않음)."""
    if parse_key(key)[1] is not None:
        raise ValueError("embed run takes a base model key without variant")
    own = eg is None
    eg = eg or Egress.from_dsn(dsn)
    try:
        with db.connect(dsn) as conn:
            conn.execute("SET statement_timeout = '10min'")
            rows = target_rows(conn)
            out = ensure(conn, eg, key, rows)
            removed = conn.execute("DELETE FROM core.idea_embedding WHERE model = %s AND NOT (idea_id = ANY(%s))",
                                   (key, [r[0] for r in rows])).rowcount
            conn.commit()
    finally:
        if own:
            eg.close()
    return {"target": len(rows), **out, "removed": removed}


def load(conn, key: str, ids: Sequence[str] | None = None):
    """(idea_id 목록, float32 행렬). ids가 있으면 그 순서로, 없는 id는 빠진다."""
    import numpy as np
    from pgvector.psycopg import register_vector

    register_vector(conn)
    sql = "SELECT idea_id, vec FROM core.idea_embedding WHERE model = %s"
    params: tuple = (key,)
    if ids is not None:
        sql += " AND idea_id = ANY(%s)"
        params = (key, list(ids))
    got = {iid: v.to_numpy() for iid, v in conn.execute(sql, params, binary=True)}
    order = [i for i in (ids if ids is not None else sorted(got)) if i in got]
    dims = MODELS[parse_key(key)[0]].dims
    mat = np.empty((len(order), dims), dtype=np.float32)
    for n, i in enumerate(order):
        mat[n] = got.pop(i)
    return order, mat
