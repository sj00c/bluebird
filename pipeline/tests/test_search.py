from bluebird.search import Index, fuse, tokens


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
