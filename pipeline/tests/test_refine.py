import pytest

from bluebird import refine


@pytest.mark.parametrize("raw, expected", [
    ('[제안취지] ○ 양천구는 북한이탈주민이 많음\n○ 출산 지원', "[제안취지] 양천구는 북한이탈주민이 많음 출산 지원"),
    ('"- 경사로 핸드레일 재정비\n- 겨울철 사고예방"', "경사로 핸드레일 재정비 겨울철 사고예방"),
    ("[현황및문제점] \U000f03da 현황\n ○ 집합건물", "[현황및문제점] 현황 집합건물"),
    ("1. 정비계획 수립\n가. 교통·환경 개선 - 단계별", "1. 정비계획 수립 가. 교통·환경 개선 - 단계별"),
    ('그는 "안전"을 말했다', '그는 "안전"을 말했다'),
    ("[NULL]", ""),
    ("A &amp; B\r\n\r\n  C", "A & B C"),
])
def test_clean_body(raw, expected):
    assert refine.clean(raw) == expected


def test_clean_title_drops_receipt_number_only_at_start():
    assert refine.clean("(SPS-2607-3012689)전기자전거 배터리 안전 기준", title=True) == "전기자전거 배터리 안전 기준"
    assert refine.clean("\t군산시 공공 축구장 야간 운영 시간 연..", title=True) == "군산시 공공 축구장 야간 운영 시간 연.."
    assert refine.clean("KTX-2026 노선 개선", title=True) == "KTX-2026 노선 개선"
    assert refine.clean("(SPS-2601-1520253)*우회전 차량 사고 방지책*", title=True) == "우회전 차량 사고 방지책"
    assert refine.clean("&amp;lt;삼돌이마을&amp;gt;") == "<삼돌이마을>"


def test_masking_uses_name_token_after_cleaning():
    body = refine.clean("○ 우리의 보스가 만든 앱. 문의 010-1234-5678")
    f = refine._fields("우리의 보스 팀의 문해력 앱", body, people=["우리의 보스"])
    assert f["title"] == "[이름] 팀의 문해력 앱"
    assert f["body"] == "[이름]가 만든 앱. 문의 [전화]"


def test_mapped_skips_guidance_rows_and_keeps_contest_only_from_row():
    spec = {"id": "x", "url": "https://www.data.go.kr/data/1/fileData.do", "contest_name": "등록 기본값",
            "columns": {"title": "제목", "year": "연도", "body": ["내용"], "people": ["성명"]},
            "exclude": {"제목": ["제안공모"]}, "require_any": ["내용"]}
    extract = refine.mapped(spec)
    assert extract({"제목": "제목", "연도": "연도", "내용": "내용", "성명": "성명"}) is None
    assert extract({"제목": "제안공모", "연도": "2024", "내용": "본문", "성명": ""}) is None
    assert extract({"제목": "쉼터", "연도": "2024", "내용": "", "성명": ""}) is None
    assert extract({"제목": "홍길동 쉼터", "연도": "2024년", "내용": "○ 쉼터 설치", "성명": "홍길동"}) == {
        "title": "[이름] 쉼터", "body": "쉼터 설치", "contest": None,
        "url": "https://www.data.go.kr/data/1/fileData.do", "year": 2024}


def test_api_extractors():
    url = "https://example.go.kr/"
    acrc = refine.extractor({"id": "acrc_open_proposals", "url": url})
    assert acrc({"title": "제안", "regDate": "2026.04.17. 07:31:23", "peterName": "김철수",
                 "content": "김철수입니다. ○ 개선", "improveIdea": ""}) == {
        "title": "제안", "body": "[제안내용] [이름]입니다. 개선", "contest": None, "url": url, "year": 2026}
    kipris = refine.extractor({"id": "kipris_idea_api", "url": url})
    assert kipris({"ideaName": "Plasma의 응용", "contestYear": "1965", "contestName": "전국과학전람회",
                   "ideaContent": "본 발명품은", "originalLink": "http://evil.example/x"}) == {
        "title": "Plasma의 응용", "body": "본 발명품은", "contest": "전국과학전람회", "url": url, "year": 1965}
    free = refine.extractor({"id": "seoul_free_suggestions", "url": url})
    assert free({"TITLE": "벤치", "REG_DATE": "2026-10-14 10:45:15.0",
                 "CONTENT": "https://idea.seoul.go.kr/front/freeSuggest/view.do?sn=1"})["url"].endswith("sn=1")


def test_extractor_requires_mapping():
    with pytest.raises(ValueError, match="no extractor"):
        refine.extractor({"id": "unknown"})


def test_extra_body_columns_for_master_only():
    spec = {"id": "jeonnam_citizen_proposals", "url": "https://www.data.go.kr/",
            "columns": {"title": "제안명", "year": "등록일시"}}
    f = refine.mapped(spec)({"제안명": "버스 노선", "등록일시": "2023-01-02", "공개내용": "○ 노선 증설"})
    assert f["body"] == "노선 증설"
    assert "body" not in spec["columns"]
