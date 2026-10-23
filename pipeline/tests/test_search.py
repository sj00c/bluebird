from bluebird import search
from bluebird.search import Index, Ranking, fuse, tokens


def test_tokens_keep_nouns_and_drop_verbs_and_particles():
    out = tokens("버스 정류장에서 기다리는 시간을 줄이는 앱").split()
    assert {"버스", "정류장", "시간"} <= set(out)
    assert not {"에서", "기다리", "줄이", "을", "는"} & set(out)
    assert tokens("  ") is None and tokens(None) is None


def _index(docs: dict[str, str]) -> Index:
    return Index([("s", k) for k in docs], [d.split() for d in docs.values()])


def test_bm25_rare_word_outranks_common_word_and_unmatched_docs_are_absent():
    ix = _index({"common": "버스 안전", "rare": "버스 드론", "other1": "버스 공원", "other2": "버스 조명",
                 "none": "급식 학교"})
    hits = ix.search("드론 버스")
    assert hits[0] == ("s", "rare")             # 드론 = 한 문서에만 → idf 높음
    assert ("s", "none") not in hits            # 겹치는 낱말 없음 = 결과 없음
    assert ix.search("우주") == []


def test_bm25_shorter_doc_wins_for_same_match():
    ix = _index({"long": "드론 배송 물류 창고 자동화 시스템 구축", "short": "드론 배송", "x": "학교 급식"})
    assert ix.search("드론")[:2] == [("s", "short"), ("s", "long")]


def test_fuse_prefers_items_found_by_both_and_weights_bm25_more():
    both, bm_only, vec_only = ("s", "both"), ("s", "bm"), ("s", "vec")
    assert fuse([both, bm_only], [vec_only, both])[0] == both
    # 같은 순위로 한쪽에만 있으면 BM25 쪽이 앞(가중치 0.6 > 0.4)
    assert fuse([bm_only], [vec_only]) == [bm_only, vec_only]


class _Conn:
    """master 행 조회만 흉내: (api, key) 목록 → 15칸 행."""

    def execute(self, sql, params):
        _vec, apis, keys = params
        rows = [(a, k, 2000, "공모전", "p", "상", k, "g", "s", [], k, [], "product", None, 0.5) for a, k in zip(apis, keys)]
        return type("R", (), {"fetchall": lambda _self: rows})()


class _Eg:
    def embed(self, *, model, source, texts):
        return [[0.0, 1.0]]


def _ranking(monkeypatch, n: int, picks):
    """후보 n개(점수 같음 → 순서 = d0, d1, …). picks(묶음 번호, 후보 key 목록) → 고를 번호."""
    calls = []
    monkeypatch.setattr(search, "vector_search", lambda conn, vec, flt: [])

    def rerank(eg, query, cands):
        calls.append([c["key"] for c in cands])
        return picks(len(calls) - 1, [c["key"] for c in cands])

    monkeypatch.setattr(search, "rerank", rerank)
    index = Index([("s", f"d{i}") for i in range(n)], [["w"] for _ in range(n)])
    return Ranking(_Conn(), _Eg(), index, "w"), calls


def test_pages_judge_lazily_and_keep_order_across_pages(monkeypatch):
    # 묶음마다 거꾸로 절반만 관련
    rk, calls = _ranking(monkeypatch, 120, lambda _n, keys: list(range(len(keys) - 1, -1, -2)))
    first, more = rk.page(_Conn(), 1, 10)
    assert len(calls) == 1 and more                          # 첫 묶음(50개)에서 25개 → 첫 쪽 + 다음 있음
    assert [x["rank"] for x in first] == list(range(1, 11)) and first[0]["key"] == "d49"
    third, _ = rk.page(_Conn(), 3, 10)                       # 21~30번째 → 둘째 묶음 판정 필요
    assert len(calls) == 2 and third[0]["rank"] == 21
    assert rk.page(_Conn(), 1, 10)[0] == first and len(calls) == 2   # 앞 쪽 다시 봐도 재판정·순서 변화 없음


def test_list_ends_when_a_batch_has_nothing_relevant(monkeypatch):
    rk, calls = _ranking(monkeypatch, 120, lambda n, keys: [0, 1, 2] if n == 0 else [])
    items, more = rk.page(_Conn(), 1, 10)
    assert [x["key"] for x in items] == ["d0", "d1", "d2"] and not more
    assert len(calls) == 2                                   # 빈 묶음 뒤 셋째 묶음은 안 봄
    assert rk.page(_Conn(), 2, 10) == ([], False)
