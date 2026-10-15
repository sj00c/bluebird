from bluebird import fill

ROWS = [("a", "k1", "버스", None, None), ("a", "k2", "쉼터", "본문", "원래 대회")]


def test_parse_keeps_valid_items_and_fixed_domains():
    items = [
        {"id": 0, "keyword": ["버스", " 노선 ", "", "x", "y"], "problem": "  배차 간격이 길다 ", "feature": None,
         "target": "", "domain": ["교통", "우주", "교통"], "contest": "서울시 시민참여예산"},
        {"id": "1", "keyword": ["쉼터"], "domain": ["없는값"]},   # 목록 밖 domain → 기타
        {"id": 9, "keyword": ["x"], "domain": ["기타"]},          # 입력에 없는 id
    ]
    assert fill.parse(items, ROWS) == [
        (["버스", "노선", "x"], "배차 간격이 길다", None, None, ["교통"], "서울시 시민참여예산", "a", "k1"),
        (["쉼터"], None, None, None, ["기타"], None, "a", "k2")]
    assert fill.parse([{"id": 0, "keyword": [], "domain": ["교통"]}], ROWS) == []   # keyword 없음 → 버림


def test_context_uses_registry_fields():
    assert fill._context({"name": "서울 자유제안", "topic": "시민 제안", "contest_name": ""}) == (
        "소스명: 서울 자유제안\n주제: 시민 제안")
