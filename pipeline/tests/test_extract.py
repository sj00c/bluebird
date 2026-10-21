from bluebird.extract import parse

ROWS = [("s", "1", "변신분무기", "낮은 곳 화초에 물을 줄 때 분무기 헤드를 변형시켜 분사가 잘 되게 함", "발명품경진대회"),
        ("s", "2", "세금", "세금 너무 많다", None),
        ("s", "3", "그네", "무게중심 위치를 바꿔 실험했다", "과학전람회"),
        ("s", "4", "x", "본문", None)]


def test_parse_keeps_label_and_verifies_evidence_against_text():
    items = [
        {"id": 0, "label": "idea", "type": "product", "goal": "낮은 곳 분무 불편", "solution": "헤드 변형 분무기",
         "features": ["헤드 각도 조절", "", "a", "b"], "domain": ["생활", "없는분야", "과학기술", "교육"],
         "evidence": "분무기 헤드를  변형시켜"},
        {"id": 1, "label": "complaint", "type": "policy", "goal": "무시됨"},
        {"id": 2, "label": "idea", "type": "research", "goal": "최적 자세", "solution": "실험",
         "domain": [], "evidence": "지어낸 구절"},
        {"id": 3, "label": "idea", "type": "모름"},            # 유형 형식 오류 = 저장 안 함(다음에 다시)
    ]
    assert parse(items, ROWS) == [
        ("idea", "product", "낮은 곳 분무 불편", "헤드 변형 분무기", ["헤드 각도 조절", "a", "b"], ["생활", "과학기술"],
         "분무기 헤드를 변형시켜", True, "s", "1"),
        ("complaint", None, None, None, None, None, None, None, "s", "2"),
        ("idea", "research", "최적 자세", "실험", [], ["기타"], "지어낸 구절", False, "s", "3")]


def test_parse_normalizes_type_variants():
    """유형을 label 칸에 쓴 응답 = idea + 그 유형, product 하위 낱말(service 등) = product."""
    items = [{"id": 2, "label": "research", "goal": "최적 자세", "solution": "실험", "domain": ["과학기술"],
              "evidence": "무게중심 위치를 바꿔"},
             {"id": 0, "label": "idea", "type": "service", "domain": ["생활"], "evidence": "분무기 헤드를"}]
    assert [(r[9], r[0], r[1], r[7]) for r in parse(items, ROWS)] == [
        ("1", "idea", "product", True), ("3", "idea", "research", True)]
