from bluebird.cards import card_kind, extract_missing_data, rule_card


def test_card_kind_by_body_and_grade():
    assert card_kind(False, "O") == "title_only"
    assert card_kind(True, "O") == "full"
    assert card_kind(True, "pending") == "local_extract"
    assert card_kind(False, "pending") == "title_only"


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
