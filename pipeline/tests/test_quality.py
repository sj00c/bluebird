import pytest

from bluebird.quality import reasons


@pytest.mark.parametrize("title, body, codes", [
    ("방범 CCTV", None, ["no_body"]),
    ("방범 CCTV", "[사업내용] . .", ["no_body"]),                                       # 라벨·기호뿐
    ("K-테이블 마스크", "[사업목적] 별첨 [사업내용] 첨부파일참조 [사업효과] 붙임 참조", ["attachment_only"]),
    ("반찬지원사업", "[불편한점] 반찬지원사업 [개선방안] 반찬 지원사업", ["title_repeat"]),
    ("30일", "모바일", ["short_title_body"]),                                            # 제목 3자 + 본문 3자
    ("보온병", "보온병이 불편해서 손잡이를 단다", []),                                       # 본문 11자 초과
    ("전기차 충전 터널 설계", "모바일", []),                                              # 제목 6자 이상 = 본문 짧아도 유지
    ("첨부 양식 개선", "첨부파일 이름을 자동으로 붙여 주는 기능", []),                        # 첨부 낱말이 있어도 내용 있음
    ("1 2 3", "[사업내용] 가나 다! [기타] ab", ["short_title_body"]),                     # 글자 수 = 라벨·공백·기호 빼고 3·5
])
def test_rule_reasons(title, body, codes):
    assert reasons(title, body) == codes


def test_ai_label_is_reason_unless_idea_or_no_body():
    body = "세금 너무 많다 국민연금 개편이 필요하다"
    assert reasons("세금", body, "complaint") == ["complaint"] and reasons("세금", body, "idea") == []
    assert reasons("세금", None, "complaint") == ["no_body"]
