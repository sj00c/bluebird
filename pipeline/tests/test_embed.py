import math

import numpy as np
import pytest

from bluebird import embed, embed_eval
from bluebird.egress import EgressHTTPStatus

KEY = "openai:text-embedding-3-large:3072"


def test_clean_strips_html_section_tags_bullets_and_short_headers():
    body = "발명내용<br />수도꼭지를&nbsp;접는다.<br /><b>레버</b>로 물을 채운다."
    assert embed.clean(body) == "수도꼭지를 접는다. 레버 로 물을 채운다."
    budget = "[제안취지] ○ 골목길이 좁아\n위험함.\n[사업내용] □ 제안취지\n○ 포장 정비"
    assert embed.clean(budget) == "골목길이 좁아 위험함. 포장 정비"


def test_prep_joins_title_and_body_and_caps_length():
    assert embed.prep("제목", "본문 내용") == "제목\n\n본문 내용"
    assert len(embed.prep("t", "가" * 10_000)) == embed.MAX_CHARS


def test_strip_title_removes_title_even_with_spacing_differences():
    assert embed.strip_title("스마트 버스정류장", "이 스마트버스 정류장은 따뜻하다. 스마트 버스 정류장") == "이 은 따뜻하다."
    assert embed.strip_title("", "본문") == "본문"


def test_input_text_by_variant_and_sha_is_stable():
    assert embed.input_text(KEY + ":title", " 제목 ", "본문") == "제목"
    assert embed.input_text(KEY + ":notitle", "온열의자", "온열의자 설치 요청") == "설치 요청"
    assert embed.sha(embed.input_text(KEY, "a", "b")) == embed.sha("a\n\nb")


def test_parse_key_and_task_type():
    assert embed.parse_key(KEY) == (KEY, None)
    assert embed.parse_key("gemini:gemini-embedding-2:3072:title") == ("gemini:gemini-embedding-2:3072", "title")
    with pytest.raises(ValueError):
        embed.parse_key("openai:text-embedding-3-small:1536")
    g = embed.MODELS["gemini:gemini-embedding-001:3072"]
    assert embed.task_type(g, "title") == "RETRIEVAL_QUERY" and embed.task_type(g, None) == "RETRIEVAL_DOCUMENT"
    assert embed.task_type(embed.MODELS[KEY], "title") is None
    gk = "gemini:gemini-embedding-001:3072"
    assert embed.config_sha(gk) != embed.config_sha(gk + ":title")   # Gemini는 질의·문서 taskType이 다름


def test_batches_respect_count_and_char_budget(monkeypatch):
    monkeypatch.setattr(embed, "BATCH_CHARS", 10)
    rows = [(str(i), "s", "x" * 4) for i in range(5)]
    assert [len(b) for b in embed._batches(rows, 100)] == [2, 2, 1]
    assert [len(b) for b in embed._batches(rows, 1)] == [1] * 5


class FakeEg:
    def __init__(self, fails):
        self.fails, self.calls = list(fails), 0

    def embed(self, **kw):
        self.calls += 1
        if self.fails:
            raise EgressHTTPStatus(self.fails.pop(0), "x")
        return [[1.0]] * len(kw["items"]), None


def test_call_retries_rate_limit_and_server_errors_but_not_client_errors():
    m = embed.MODELS[KEY]
    eg, waits = FakeEg([429, 503]), []
    assert embed._call(eg, m, None, [("i", "s", "t")], sleep=waits.append)[0] == [[1.0]]
    assert eg.calls == 3 and waits == [1, 2]
    with pytest.raises(EgressHTTPStatus):
        embed._call(FakeEg([400]), m, None, [("i", "s", "t")], sleep=waits.append)
    with pytest.raises(EgressHTTPStatus):
        embed._call(FakeEg([429] * embed.RETRIES), m, None, [("i", "s", "t")], sleep=lambda s: None)


def test_normalize_and_truncate_renormalize():
    assert np.allclose(embed.normalize([3.0, 4.0]), [0.6, 0.8])
    m = embed_eval.truncate(np.array([[3.0, 4.0, 12.0]], dtype=np.float32), 2)
    assert np.allclose(m, [[0.6, 0.8]])


def test_rank_metrics_and_first_hit_ranks():
    scores = np.array([[0.9, 0.5, 0.1], [0.2, 0.3, 0.8], [0.5, 0.4, 0.6]])
    ranks = embed_eval.first_hit_ranks(scores, [{0}, {0}, {1}, set()], [set(), {2}, {2}, set()])
    assert ranks == [1, 2, 2]   # q1: 2를 빼면 0은 2위. q2: 2를 빼면 1은 2위. 정답 없는 질의는 뺀다
    r = embed_eval.rank_metrics(ranks)
    assert r["n"] == 3 and math.isclose(r["r1"], 1 / 3) and r["r10"] == 1 and math.isclose(r["mrr"], (1 + .5 + .5) / 3)
    assert embed_eval.rank_metrics([])["n"] == 0


def test_purity_against_chance_baseline():
    a, b = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    mat = np.array([a, a, a, b, b, b])
    pur, base = embed_eval.purity(mat, ["x", "x", "x", "y", "y", "y"], k=2)
    assert pur == 1.0 and base == 0.5


def test_clean_keeps_korean_angle_brackets_and_title_brackets():
    assert embed.clean("<전국 휴게소 OnStop 정보제공 서비스>", body=False) == "<전국 휴게소 OnStop 정보제공 서비스>"
    assert embed.clean("[유니버설디자인] 경사로", body=False) == "[유니버설디자인] 경사로"
    assert embed.clean("<p>본문</p><br/>둘째 줄") == "본문 둘째 줄"


def test_clean_drops_lost_bullets_and_private_glyphs_but_keeps_question_marks():
    assert embed.clean("판로 확보 ？ 전체 컨셉 ？ 1호점 운영") == "판로 확보 전체 컨셉 1호점 운영"
    assert embed.clean("\U000f03da 건의사항\n• 첫째\n왜 안 되나요？ 개선") == "건의사항 첫째 왜 안 되나요？ 개선"


def test_body_len_counts_only_real_body():
    meta = "[편성사업명] 시외버스 실내 공기정화장치 보급사업(주민참여예산)(자체/지원)\n[예산편성연도] 2022"
    assert len(meta.replace(" ", "").replace("\n", "")) >= 50 and embed.body_len("t", meta) < embed.MIN_BODY
    title = "스마트 공항관제 플랫폼 개발"
    assert embed.body_len(title, f"({title}) 영상 분석 지원") == len("()영상분석지원")
    assert embed.body_len("t", "가" * 50) == 50
