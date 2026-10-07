import json

import httpx
import pytest

from bluebird import llm
from bluebird.cards import card_kind, extract_missing_data, llm_card, rule_card
from bluebird.egress import Egress, Policy


def test_card_kind_is_what_p1_received():
    assert card_kind(False, False) == "title_only"
    assert card_kind(True, True) == "full"
    assert card_kind(True, False) == "local_extract"  # 규칙만 → full 아님


def test_llm_card_keeps_only_excerpts_found_in_body(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    body = "버스 도착 정보는 있다. 저상버스 배차 데이터가 공개되지 않아 휠체어 이용자가 기다린다."
    answer = {"problem": "휠체어 이용자 대기", "solution": "저상버스 예측", "required_tech": ["예측"],
              "missing_data": [
                  {"name": "저상버스 배차 데이터", "excerpt": "저상버스 배차 데이터가 공개되지 않아 휠체어 이용자가 기다린다."},
                  {"name": "지어낸 데이터", "excerpt": "본문에 없는 문장"}]}
    sent = []

    def h(req):
        sent.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "```json\n" + json.dumps(answer, ensure_ascii=False) + "\n```"}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    calls = []
    eg = Egress(policy=Policy(grades={"s": "O"}), recorder=lambda c: calls.append(c) or len(calls), proxy="",
                transport=httpx.MockTransport(h))
    c, call_id = llm_card(eg, llm.Provider("openai", "m"), {"source_id": "s", "title": "저상버스", "body": body})
    (md,) = c["missing_data"]
    assert body[md["char_span"][0]:md["char_span"][1]] == md["excerpt"]
    assert c["required_tech"] == ["예측"] and call_id == 1
    assert calls[0].fields_sent == ["s.body", "s.title"] and calls[0].tokens_in == 10
    assert body in sent[0]["messages"][1]["content"]


def test_llm_card_refused_for_pending_source(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    from bluebird.egress import EgressBlocked
    eg = Egress(policy=Policy(grades={"kipris": "pending"}), recorder=lambda c: 1, proxy="",
                transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(EgressBlocked):
        llm_card(eg, llm.Provider("openai", "m"), {"source_id": "kipris", "title": "t", "body": "b"})


def test_provider_none_without_keys(monkeypatch):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "BB_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    assert llm.provider() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert llm.provider().name == "anthropic"


def test_missing_data_only_from_body_with_span():
    body = "주차장 위치는 공개돼 있다. 그러나 실시간 주차면 데이터가 없어 빈자리를 알 수 없다. 앱으로 안내한다."
    (md,) = extract_missing_data(body)
    assert md["name"].endswith("주차면 데이터") and md["origin"] == "body"
    s, e = md["char_span"]
    assert "데이터가 없" in body[s:e]
    assert md["excerpt"].startswith("그러나 실시간")


def test_no_missing_data_when_body_says_nothing_missing():
    assert extract_missing_data("공공 와이파이 데이터를 활용해 지도를 만든다.") == []


def test_rule_card_problem_and_solution():
    c = rule_card({"body": "노인은 병원 예약이 어렵다. 음성으로 예약하는 서비스를 제공한다."})
    assert c["problem"].startswith("노인은") and c["solution"].startswith("음성으로")


def _anchor(body, items):
    from bluebird.cards import _anchor_missing
    return _anchor_missing(body, items)


def test_anchor_rejects_weak_or_invented_missing_data():
    body = "버스 도착 정보는 있다. 저상버스 배차 데이터가 공개되지 않아 휠체어 이용자가 기다린다."
    good = "저상버스 배차 데이터가 공개되지 않아 휠체어 이용자가 기다린다."
    assert _anchor(body, [{"name": "저상버스 배차 데이터", "excerpt": good}])[0]["excerpt"] == good
    # 너무 짧은 조각(본문에 있어도), 부족 표현 없는 문장, 이름과 무관한 문장, 300자 초과는 버린다
    assert _anchor(body, [{"name": "저상버스 배차 데이터", "excerpt": "데이터"}]) == []
    assert _anchor(body, [{"name": "버스 도착 정보", "excerpt": "버스 도착 정보는 있다."}]) == []
    assert _anchor(body, [{"name": "지하철 혼잡도 데이터", "excerpt": good}]) == []
    assert _anchor(body, [{"name": "데이터", "excerpt": good}]) == []  # 일반어만 있는 이름
    long_body = "가" * 290 + " 배차 데이터가 없다."
    assert _anchor(long_body, [{"name": "배차 데이터", "excerpt": long_body}]) == []


def test_anchor_cue_needs_negative_ending():
    body = "별도 장비 없이 드론 영상 데이터를 활용한다. 안전 확보를 위해 사고 통계 데이터를 쓴다. 주차면 점유 데이터가 없어 추정한다."
    assert _anchor(body, [{"name": "드론 영상 데이터", "excerpt": "별도 장비 없이 드론 영상 데이터를 활용한다."}]) == []
    assert _anchor(body, [{"name": "사고 통계 데이터", "excerpt": "안전 확보를 위해 사고 통계 데이터를 쓴다."}]) == []
    assert len(_anchor(body, [{"name": "주차면 점유 데이터", "excerpt": "주차면 점유 데이터가 없어 추정한다."}])) == 1

