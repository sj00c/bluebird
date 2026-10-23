"""문제 문장 → 비슷한 과거 아이디어(master 사용 대상). 방식·값 근거 = docs/SEARCH_PLAN.md

- 단어 검색 = BM25(search_tokens, 메모리 색인) / 벡터 검색 = embedding 코사인(pgvector)
- 둘을 가중 RRF로 섞은 순서대로 후보 CANDIDATES개씩 LLM이 재정렬(관련 있는 것만). 결과 목록 = 재정렬된 것을 이어 붙인 것
- 쪽(page) 단위로 보여 줌. 필요한 만큼만 다음 후보 묶음을 재정렬(Ranking.page)
- 질문 글은 egress로만 나감(벡터·재정렬). 사람이 친 글의 소스 = QUERY_SOURCE
"""

from __future__ import annotations

import math
import threading
from collections import Counter
from dataclasses import dataclass

from . import embed, llm
from .egress import Egress

# Kiwi 품사: 일반·고유 명사, 어근, 영문, 숫자. 동사·형용사·의존명사 넣으면 nDCG 0.719 → 0.701(2026-10-22 시험)
POS = frozenset({"NNG", "NNP", "XR", "SL", "SN"})
K1, B = 2.0, 0.5            # BM25. 품사 3 × k1 5 × b 4 중 최고(시험 A), B 세트에서 확인
DEPTH = 200                 # 단어·벡터 검색 각각 가져오는 수
RRF_K, W_BM25 = 60, 0.6     # 가중 RRF. 우리 글은 LLM이 정리해 낱말이 통일됨 → BM25 쪽이 조금 더 무거움
CANDIDATES = 50             # 재정렬 한 번에 보는 후보 수. 30·50·80 중 1등 정확도 최고
SIZE = 10                   # 한 쪽에 보여 줄 개수 기본값
RERANK = llm.Provider("openai", "gpt-4.1-mini")
QUERY_SOURCE = {"id": "query", "export_grade": "pending"}   # 사람이 친 검색 문장

_RERANK_SYSTEM = "JSON 객체 하나만 출력한다."
_RERANK_INSTRUCTION = (
    "<problem>은 최근 제기된 문제, <embedding_input>은 과거 아이디어 후보 목록(id, text)이다. "
    "관련 있는 후보만 모두 골라, 문제를 직접 다루는 아이디어가 앞에 오도록 순서대로 id를 낸다. "
    "관련 없으면 넣지 않는다.\n출력: {\"ids\": [..]}")

_kiwi = None
_kiwi_lock = threading.Lock()


def tokens(text: str | None) -> str | None:
    """BM25 토큰(공백으로 이음). 글이 비거나 남는 토큰이 없으면 None."""
    global _kiwi
    if not text or not text.strip():
        return None
    with _kiwi_lock:   # Kiwi 객체 = 스레드 간 공유 안 함
        if _kiwi is None:
            from kiwipiepy import Kiwi

            _kiwi = Kiwi()
        out = [t.form for t in _kiwi.tokenize(text) if t.tag in POS]
    return " ".join(out) or None


@dataclass(frozen=True)
class Filter:
    """사용자가 정한 범위. 비우면 전체."""
    year_min: int | None = None
    year_max: int | None = None
    kinds: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    item_types: tuple[str, ...] = ()
    awarded: bool = False   # 수상 내역 있는 행만

    def sql(self) -> tuple[str, dict]:
        where, args = [], {}
        if self.year_min is not None:
            where.append("year >= %(year_min)s")
            args["year_min"] = self.year_min
        if self.year_max is not None:
            where.append("year <= %(year_max)s")
            args["year_max"] = self.year_max
        for col, name in (("kind", "kinds"), ("item_type", "item_types")):
            if getattr(self, name):
                where.append(f"{col} = ANY(%({name})s)")
                args[name] = list(getattr(self, name))
        if self.domains:
            where.append("domain && %(domains)s::text[]")
            args["domains"] = list(self.domains)
        if self.awarded:
            where.append("NULLIF(BTRIM(award), '') IS NOT NULL")
        return "".join(" AND " + w for w in where), args


ALL = Filter()


class Index:
    """사용 대상 BM25 색인(메모리). 범위가 같으면 다시 만들 필요 없음."""

    def __init__(self, keys: list[tuple[str, str]], docs: list[list[str]]):
        self.keys = keys
        self.lens = [len(d) for d in docs]
        self.avg = sum(self.lens) / len(docs) if docs else 0.0
        df: Counter[str] = Counter()
        self.post: dict[str, list[tuple[int, int]]] = {}
        for i, doc in enumerate(docs):
            for word, count in Counter(doc).items():
                self.post.setdefault(word, []).append((i, count))
                df[word] += 1
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    @classmethod
    def load(cls, conn, flt: Filter = ALL) -> Index:
        where, args = flt.sql()
        rows = conn.execute("SELECT api, key, search_tokens FROM master"
                            " WHERE exclude_reasons = '{}' AND search_tokens IS NOT NULL" + where +
                            " ORDER BY api, key", args).fetchall()
        return cls([(a, k) for a, k, _ in rows], [t.split() for _, _, t in rows])

    def search(self, query_tokens: str | None, n: int = DEPTH) -> list[tuple[str, str]]:
        score: dict[int, float] = {}
        for word in set((query_tokens or "").split()):
            idf = self.idf.get(word)
            if idf is None:
                continue
            for i, tf in self.post[word]:
                norm = K1 * (1 - B + B * self.lens[i] / self.avg)
                score[i] = score.get(i, 0.0) + idf * tf * (K1 + 1) / (tf + norm)
        best = sorted(score.items(), key=lambda x: (-x[1], x[0]))[:n]
        return [self.keys[i] for i, _ in best]


def vector_search(conn, vector: list[float], flt: Filter = ALL, n: int = DEPTH) -> list[tuple[str, str]]:
    """코사인 가까운 순. 범위 필터가 있어도 n개를 채우도록 HNSW 반복 탐색."""
    where, args = flt.sql()
    with conn.transaction():
        conn.execute("SET LOCAL hnsw.ef_search = 400")
        conn.execute("SET LOCAL hnsw.iterative_scan = strict_order")
        rows = conn.execute("SELECT api, key FROM master WHERE exclude_reasons = '{}' AND embedding IS NOT NULL" + where +
                            " ORDER BY embedding <=> %(v)s::halfvec LIMIT %(n)s",
                            {**args, "v": str(vector), "n": n}).fetchall()
    return [(a, k) for a, k in rows]


def fuse(bm25: list, vector: list) -> list:
    """가중 RRF로 섞은 전체 순서. 같은 점수면 BM25 순위가 앞선 쪽."""
    score: dict = {}
    for hits, weight in ((bm25, W_BM25), (vector, 1 - W_BM25)):
        for rank, key in enumerate(hits, 1):
            score[key] = score.get(key, 0.0) + weight / (RRF_K + rank)
    return sorted(score, key=lambda k: -score[k])


def rerank(eg: Egress, query: tuple[str, str], cands: list[dict]) -> list[int]:
    """LLM이 고른 후보 번호(관련 있는 것만, 순서대로). query = (소스, 문장). cands = api·text 포함."""
    srcs = tuple(sorted({c["api"] for c in cands}))
    data, _ = llm.ask_json(eg, RERANK, system=_RERANK_SYSTEM, instruction=_RERANK_INSTRUCTION,
                           fields={"problem": query,
                                   "embedding_input": (srcs, [{"id": i, "text": c["text"]} for i, c in enumerate(cands)])},
                           max_tokens=400)
    picked = [int(x) for x in data.get("ids", []) if str(x).isdigit() and int(x) < len(cands)]
    return list(dict.fromkeys(picked))


_COLS = ("api", "key", "year", "kind", "program", "award", "title", "goal", "solution", "features", "text", "domain",
         "item_type", "url", "similarity")


class Ranking:
    """한 질문의 결과 목록. 재정렬은 앞에서부터 필요한 만큼만(후보 CANDIDATES개씩), 한 번 정한 순서는 유지.
    후보 묶음 하나에서 관련 있는 것이 0개면 그 뒤(섞은 순위가 더 낮은 후보)는 보지 않고 목록 끝.
    similarity = 질문과 아이디어 벡터의 코사인 유사도(순서 기준 아님, 참고 값)."""

    def __init__(self, conn, eg: Egress, index: Index, query: str, *, source: str = QUERY_SOURCE["id"],
                 flt: Filter = ALL, use_rerank: bool = True):
        self.eg, self.query, self.source = eg, query, source
        vector = eg.embed(model=embed.MODEL, source=source, texts=[query])[0]
        self.vector = str(vector)
        self.fused = fuse(index.search(tokens(query)), vector_search(conn, vector, flt))
        self.order: list[tuple[str, str]] = [] if use_rerank else list(self.fused)
        self.done = not use_rerank
        self.judged = 0
        self.rows: dict[tuple[str, str], dict] = {}
        self.lock = threading.Lock()

    def _load(self, conn, keys: list[tuple[str, str]]) -> None:
        need = [k for k in keys if k not in self.rows]
        if not need:
            return
        rows = conn.execute("SELECT api, key, year, kind, program, award, title, goal, solution, features, embedding_input,"
                            " domain, item_type, url, round((1 - (embedding <=> %s::halfvec))::numeric, 3)::float"
                            " FROM master WHERE (api, key) IN (SELECT * FROM unnest(%s::text[], %s::text[]))",
                            (self.vector, [a for a, _ in need], [k for _, k in need])).fetchall()
        self.rows.update({(r[0], r[1]): dict(zip(_COLS, r, strict=True)) for r in rows})

    def page(self, conn, page: int = 1, size: int = SIZE) -> tuple[list[dict], bool]:
        """page쪽 결과(1부터)와 다음 쪽이 있는지. 다음 쪽 확인을 위해 한 개 더 채워 둠."""
        end = page * size
        with self.lock:
            while len(self.order) <= end and not self.done:
                window = self.fused[self.judged:self.judged + CANDIDATES]
                self._load(conn, window)
                cands = [self.rows[k] for k in window if k in self.rows]
                picked = rerank(self.eg, (self.source, self.query), cands) if cands else []
                self.judged += len(window)
                self.order += [(cands[i]["api"], cands[i]["key"]) for i in picked]
                self.done = not picked or self.judged >= len(self.fused)
            keys = self.order[end - size:end]
            self._load(conn, keys)
        items = [{"rank": end - size + n, **self.rows[k]} for n, k in enumerate(keys, 1)]
        return items, len(self.order) > end


def search(conn, eg: Egress, index: Index, query: str, *, source: str = QUERY_SOURCE["id"], flt: Filter = ALL,
           top: int = SIZE, use_rerank: bool = True) -> list[dict]:
    """첫 쪽 top개(CLI용)."""
    return Ranking(conn, eg, index, query, source=source, flt=flt, use_rerank=use_rerank).page(conn, 1, top)[0]
