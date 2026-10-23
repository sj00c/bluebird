"""사용 대상 아이디어 → master.embedding_input(벡터에 넣는 글) + master.embedding(벡터) + master.search_tokens(BM25 토큰).

- 글 = 목표(끝 상투어 제거) + 해결책 + 핵심 기능, ". "로 이음. 분야·유형·근거·제목·본문 안 넣음
  (시험 2026-10-22: 목표만보다 상위 10개 중 같은 문제 34.4% → 38.0%, docs/DEMAND_PLAN.md)
- 상투어 제거 = 벡터용만(DB 목표 값은 그대로). 떼고 4자 미만이면 안 뗌
- 토큰 = 같은 글의 형태소(search.tokens, docs/SEARCH_PLAN.md). 외부 호출 없음
- 대상 = exclude_reasons = '{}'. 제외된 행 = 세 칸 비움. 글이 바뀐 행만 다시 벡터화(재실행 안전)
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import db, search
from .egress import Egress, EgressBlocked, EgressTransportError

MODEL = "text-embedding-3-small"
DIM = 1536
BATCH = 500

# 목표 끝 상투어(빈도 상위, 2026-10-22 사용 대상 목표 끝 표현 집계). 순서대로 최대 2번 적용
_ENDINGS = [re.compile(p) for p in (
    r"\s*문제(점)?(을|를)?\s*(해결|개선|해소)(한다|하는 것|하고자 함|하기 위함|하기|함)?$",
    r"\s*(을|를)\s*(해결|해소)(한다|하는 것|하고자 함|하기 위함|하기|함)$",
    r"(하고자 함|하기 위함|하고자 한다)$",
    r"\s*(알아내는|탐구하는|찾는|확인하는|밝히는)\s*것$",
    r"(하는|되는)\s*것$",
    r"\s*필요(성)?(이 있음|함)?$",
)]
MIN_LEFT = 4


def _tidy(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip().rstrip(".").strip()


def goal_core(goal: str | None) -> str:
    out = _tidy(goal)
    for _ in range(2):
        for pattern in _ENDINGS:
            cut = pattern.sub("", out).strip()
            if len(cut) >= MIN_LEFT:
                out = cut
    return out


def text_of(goal: str | None, solution: str | None, features: list[str] | None) -> str | None:
    parts = [goal_core(goal), _tidy(solution), ", ".join(f for f in (_tidy(x) for x in features or []) if f)]
    return ". ".join(p for p in parts if p) or None


def _vectors(eg: Egress, source: str, texts: list[str]) -> list[list[float]]:
    for wait in (5, 20, 60, None):
        try:
            return eg.embed(model=MODEL, source=source, texts=texts)
        except (EgressTransportError, KeyError, ValueError):
            pass
        except EgressBlocked as exc:
            if not any(code in str(exc) for code in ("HTTP 429", "HTTP 5")):
                raise
        if wait is None:
            raise RuntimeError(f"embedding failed: {source}")
        time.sleep(wait)
    return []


def embed(*, dsn: str, egress: Egress, only: str | None = None, workers: int = 8) -> list[dict]:
    with db.connect(dsn) as conn:
        cleared = conn.execute("UPDATE master SET embedding_input = NULL, embedding = NULL, search_tokens = NULL"
                               " WHERE exclude_reasons <> '{}' AND (embedding_input IS NOT NULL OR embedding IS NOT NULL"
                               " OR search_tokens IS NOT NULL)").rowcount
        rows = conn.execute("SELECT api, key, goal, solution, features, embedding_input, embedding IS NULL,"
                            " search_tokens IS NULL FROM master"
                            " WHERE exclude_reasons = '{}' AND (%(only)s::text IS NULL OR api = %(only)s)"
                            " ORDER BY api, key", {"only": only}).fetchall()
        conn.commit()
    todo, token_only = [], []
    for api, key, g, s, f, old, no_vec, no_tok in rows:
        if not (t := text_of(g, s, f)):
            continue
        if no_vec or t != old:
            todo.append((api, key, t))
        elif no_tok:
            token_only.append((search.tokens(t), api, key))
    jobs: list[list[tuple]] = []
    for row in todo:
        if jobs and jobs[-1][0][0] == row[0] and len(jobs[-1]) < BATCH:
            jobs[-1].append(row)
        else:
            jobs.append([row])

    def run(job: list[tuple]) -> list[tuple]:
        vecs = _vectors(egress, job[0][0], [t for _a, _k, t in job])
        return [(t, str(v), search.tokens(t), a, k) for (a, k, t), v in zip(job, vecs, strict=True)]

    done: dict[str, int] = {}
    with db.connect(dsn) as conn, ThreadPoolExecutor(workers) as pool:
        conn.cursor().executemany("UPDATE master SET search_tokens = %s WHERE api = %s AND key = %s", token_only)
        conn.commit()
        for n, out in enumerate(pool.map(run, jobs), 1):
            conn.cursor().executemany("UPDATE master SET embedding_input = %s, embedding = %s::halfvec,"
                                      " search_tokens = %s WHERE api = %s AND key = %s", out)
            done[out[0][3]] = done.get(out[0][3], 0) + len(out)
            if n % 20 == 0:
                conn.commit()
        conn.commit()
    out = [{"source": s, "status": "ok", "embedded": v} for s, v in sorted(done.items())]
    if token_only:
        out.append({"status": "ok", "tokens_only": len(token_only)})
    return out or [{"status": "ok", "embedded": 0, "cleared": cleared}]
