import csv

from bluebird.anonymize import MASK, anon_id, clean_team, mask_team, team_kind
from bluebird.sources import AWARD_RECORD_COLUMNS, SourceSpec, awards_csv


def test_team_kind():
    assert team_kind("") == "empty"
    assert team_kind("-") == "empty"
    assert team_kind("○○○") == "masked"
    assert team_kind("김**") == "masked"
    assert team_kind("홍길동") == "person"
    assert team_kind("홍길동 외 2명") == "person"
    assert team_kind("집가고싶조") == "brand"
    assert team_kind("메디뷰(MediView)") == "brand"
    assert team_kind("(주)셀타스퀘어") == "brand"


def test_clean_team_keeps_korean_words_containing_suffix_chars():
    assert clean_team("외계인팀") == "외계인팀"
    assert clean_team("등대지기") == "등대지기"
    assert clean_team("홍길동 외 3명") == "홍길동"


def test_mask_team_replaces_raw_and_cleaned_forms():
    assert mask_team("메디뷰(MediView) 앱으로 MEDIVIEW 진료", "메디뷰(MediView)") == f"{MASK} 앱으로 {MASK} 진료"
    assert mask_team("메디뷰 MediView 서비스", "메디뷰(MediView)") == f"{MASK} 서비스"
    assert mask_team("A 서비스", "A") == "A 서비스"


def test_anon_id_is_stable_and_secret_dependent():
    a = anon_id(b"s" * 32, "src", "1", 2019)
    assert a == anon_id(b"s" * 32, "src", "1", 2019)
    assert a != anon_id(b"t" * 32, "src", "1", 2019)
    assert a.startswith("ID-2019-")


def test_awards_csv_drops_team_and_source_key(tmp_path):
    f = tmp_path / "a.csv"
    with f.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["no", "host", "year", "award", "team", "item", "data", "part"])
        w.writerow(["7", "서울시", "2021", "우수상 ", "꽃기사", "꽃기사 배송 플랫폼", "A데이터\nB데이터", "-"])
    spec = SourceSpec("t", "awards_csv", f, "n", "l", "", 2, True)
    rows = list(awards_csv(spec, b"x" * 32))
    assert len(rows) == 1
    r = rows[0]
    assert set(r) == set(AWARD_RECORD_COLUMNS)
    assert r["title"] == f"{MASK} 배송 플랫폼"
    assert "꽃기사" not in str(r)
    assert "7" not in r["idea_id"].split("-", 2)[1]
    assert r["award"] == "우수상"
    assert r["used_data"] == ["A데이터", "B데이터"]
    assert r["category"] is None
    assert r["team_kind"] == "person"  # 한글 3자 단독 → 실명 가능성으로 보수적 분류


def _write_csv(path, header, rows, enc="cp949"):
    with path.open("w", encoding=enc, newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def test_science_museum_drops_people_and_school(tmp_path):
    from bluebird.sources import science_museum_csv
    f = _write_csv(tmp_path / "s.csv", ["대회명", "주제", "소속명", "제목", "지도교사", "수상자", "수상명"], [
        ["제69회 전국과학전람회", "물리", "", "줄다리기 줄의 비밀", "한홍수", "김하린, 송다원", "특상"],
        ["제44회 전국학생과학발명품경진대회", "생활", "서울○○초등학교", "김하린의 접이식 우산", "", "김하린", "등급외"],
    ])
    rows = list(science_museum_csv(SourceSpec("sm", "science_museum_csv", f, "n", "l", "", 2, True), b"x" * 32))
    text = str(rows)
    for leaked in ("한홍수", "김하린", "송다원", "초등학교"):
        assert leaked not in text
    assert [r["year"] for r in rows] == [2023, 2022]
    assert rows[0]["award"] == "특상" and rows[1]["award"] is None  # 등급외 = 수상 아님
    assert rows[1]["title"] == f"{MASK}의 접이식 우산"
    assert all(set(r) == set(AWARD_RECORD_COLUMNS) for r in rows)


def test_design_idea_drops_winner_name(tmp_path):
    from bluebird.sources import design_idea_csv
    f = _write_csv(tmp_path / "d.csv", ["등록번호", "연도", "포상", "수상자", "제목", "내용"], [
        ["1000000301", "2023", "특별상", "최준영", "경계를 잇다", "경계를 잇다"],
        ["1000000302", "2022", "대상", "이민수", "휠체어 충전 테이블", "이민수가 만든 압전 충전 테이블"],
    ])
    rows = list(design_idea_csv(SourceSpec("d", "design_idea_csv", f, "n", "l", "", 2, True), b"x" * 32))
    assert "최준영" not in str(rows) and "이민수" not in str(rows)
    assert rows[0]["body"] is None  # 제목과 같은 내용은 본문으로 치지 않음
    assert rows[1]["body"] == f"{MASK}가 만든 압전 충전 테이블"


def test_mafra_splits_part_and_award(tmp_path):
    from bluebird.sources import mafra_contest_csv
    f = _write_csv(tmp_path / "m.csv", ["경진대회명", "분야_포상", "작품명", "활용 공공데이터명", "데이터 등록일"], [
        ["2015년 창업경진대회", "서비스 개발 / 우수상", "대한민국명산", "명산등산로 서비스, 산악기상정보", "2022-04-28"],
    ])
    (r,) = mafra_contest_csv(SourceSpec("m", "mafra_contest_csv", f, "n", "l", "", 2, True), b"x" * 32)
    assert (r["year"], r["category"], r["award"]) == (2015, "서비스 개발", "우수상")
    assert r["used_data"] == ["명산등산로 서비스", "산악기상정보"]
