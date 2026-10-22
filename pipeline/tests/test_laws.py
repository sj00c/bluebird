from datetime import date

from bluebird.laws import SOURCE, reason_text, rows_of


def test_rows_keep_public_link_and_source_never_api_link_with_key():
    item = {"법령일련번호": "291387", "법령명한글": "○○법 시행령", "법령구분명": "대통령령", "제개정구분명": "일부개정",
            "소관부처명": "행정안전부", "공포일자": "20261020", "시행일자": "20261022",
            "법령상세링크": "/DRF/lawService.do?OC=secret&target=law&MST=291387"}
    rows = rows_of("법령", [item, dict(item)])                   # 같은 번호가 이틀에 나와도 1행
    assert rows == [("법령", "291387", "○○법 시행령", "대통령령", "일부개정", "행정안전부", date(2026, 10, 20),
                     date(2026, 10, 22), "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=291387", SOURCE["법령"])]
    assert all("secret" not in str(v) for v in rows[0])


def test_reason_text_flattens_nested_lines():
    detail = {"법령": {"제개정이유": {"제개정이유내용": [["[일부개정]", "◇ 개정이유", "  외국교육기관 설립 허용 "]]}}}
    assert reason_text(detail) == "[일부개정]\n◇ 개정이유\n외국교육기관 설립 허용"
    assert reason_text({"법령": {}}) is None
