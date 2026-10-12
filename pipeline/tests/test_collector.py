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


def test_mask_team_masks_each_member_of_a_list():
    team = "꿈팀(김하나, 이두리, 박세찬)"
    assert mask_team("꿈팀 김하나와 이두리, 박세찬의 지도", team) == f"{MASK} {MASK}와 {MASK}, {MASK}의 지도"
    assert mask_team("김하나·이두리 제안", "김하나, 이두리") == f"{MASK}·{MASK} 제안"


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


def test_list_masking_keeps_generic_short_tokens_and_word_boundaries():
    team = "AI Lab(김하나, 2명)"
    out = mask_team("AI 기반 maintain 도구, Lab 안에서 김하나가 개발. Labor 통계 2명", team)
    # 이름(김하나)·3자 이상 팀 낱말(Lab)은 가리고, 2자 라틴 낱말(AI)·인원수(2명)·단어 속 부분(maintain, Labor)은 둔다
    assert out == f"AI 기반 maintain 도구, {MASK} 안에서 {MASK}가 개발. Labor 통계 2명"


def test_list_masking_keeps_generic_team_words():
    # 팀명 안의 흔한 낱말(데이터·연구소)은 본문에서 가리지 않고, 팀명 전체와 사람 이름만 가린다
    out = mask_team("데이터 연구소가 만든 주차면 데이터가 없어 홍길동이 제안", "데이터 연구소(홍길동)")
    assert out == f"{MASK}가 만든 주차면 데이터가 없어 {MASK}이 제안"


def test_names_out_collects_name_forms_in_memory_only(tmp_path):
    """G10 성명 일치 감사용: 어댑터는 요청할 때만 메모리 dict에 이름 형태를 담고, 레코드에는 이름이 없다."""
    from bluebird.anonymize import find_name
    from bluebird.sources import design_idea_csv, science_museum_csv
    s = _write_csv(tmp_path / "s.csv", ["대회명", "주제", "소속명", "제목", "지도교사", "수상자", "수상명"], [
        ["제69회 전국과학전람회", "물리", "", "줄다리기 줄의 비밀", "한홍수", "김하린, 송다원", "특상"]])
    d = _write_csv(tmp_path / "d.csv", ["등록번호", "연도", "포상", "수상자", "제목", "내용"], [
        ["1000000302", "2022", "대상", "이민수", "휠체어 충전 테이블", "내용"], ["1000000303", "2022", "상", "○○○", "t", ""]])
    names: dict = {}
    rows = list(science_museum_csv(SourceSpec("sm", "science_museum_csv", s, "n", "l", "", 2, True), b"x" * 32, names))
    rows += list(design_idea_csv(SourceSpec("d", "design_idea_csv", d, "n", "l", "", 2, True), b"x" * 32, names))
    assert set(names) == {rows[0]["idea_id"], rows[1]["idea_id"]}  # 마스킹된 수상자(○○○)는 대조할 이름이 없다
    assert set(names[rows[0]["idea_id"]]) == {"한홍수", "김하린", "송다원"}
    assert all(not find_name(r["title"], names.get(r["idea_id"], [])) for r in rows)
    assert find_name("이민수가 만든 테이블", names[rows[1]["idea_id"]])
    assert not find_name("maintAIn", ["AI"]) and find_name("AI 진단", ["AI"])


def test_mask_team_keeps_masking_latin_oo_and_partly_masked_teams():
    """'oo'가 든 영문 팀명, 일부만 가려진 팀('이**(브레싱스)')도 이름 부분은 가린다(G10 대조 형태도 같다)."""
    from bluebird.anonymize import audit_variants
    assert mask_team("Pill Good 앱", "Pill Good") == f"{MASK} 앱"
    assert mask_team("SCHOOL REBIRTH 플랫폼", "SCHOOL REBIRTH") == f"{MASK} 플랫폼"
    assert "Red" not in mask_team("Red Connect 플랫폼", "김** (Red Connect)")
    assert mask_team("브레싱스 호흡 코치", "이**(브레싱스)") == f"{MASK} 호흡 코치"
    assert audit_variants("이**(브레싱스)") == ["브레싱스"]
    assert "홍길동" in audit_variants("김*수, 홍길동") and not any("*" in v for v in audit_variants("김*수, 홍길동"))
    assert audit_variants("○○○") == [] and audit_variants("") == []


def test_mapped_records_mask_people_exclude_contacts_and_keep_unknown_year(tmp_path):
    from bluebird.sources import mapped_contest_csv

    f = _write_csv(tmp_path / "mapped.csv",
                   ["제안명", "설명", "연도", "수상자", "학교", "전화", "이메일"], [
        ["김하나의 접이식 우산", "김하나가 제안한 빗물 회수 장치", "21년 상반기",
         "김하나", "새봄학교", "010-1234-5678", "private@example.com"],
        ["방수 장치", "빗물 유입 방지", "2021년", "", "", "", ""],
        ["", "제목 없는 행", "2022", "", "", "", ""],
    ])
    spec = SourceSpec("mapped", "mapped_contest_csv", f, "공식 목록 2025", "l", "", 2, False,
                      columns={"title": "제안명", "body": ["설명"], "year": "연도", "people": ["수상자"]},
                      contest_name="제69회 대회", record_kind="contest_award")
    records = list(mapped_contest_csv(spec, b"x" * 32))
    assert len(records) == 2
    assert records[0]["title"] == f"{MASK}의 접이식 우산"
    assert records[0]["body"] == f"{MASK}가 제안한 빗물 회수 장치"
    assert [r["year"] for r in records] == [None, 2021]
    assert records[0]["extra"] == {}  # record_kind는 행이 아니라 core.source에 둔다
    for private in ("김하나", "새봄학교", "010-1234-5678", "private@example.com"):
        assert private not in str(records)


def test_mapped_ids_survive_reorder_and_exact_duplicates(tmp_path):
    from bluebird.sources import mapped_contest_csv

    f = tmp_path / "mapped.csv"
    rows = [["1", "재사용 포장", "2020", "010-1111-2222"],
            ["2", "빗물 회수", "2021", "010-3333-4444"]]
    spec = SourceSpec("mapped", "mapped_contest_csv", f, "n", "l", "", 2, False,
                      columns={"title": "제안명", "year": "연도"})
    _write_csv(f, ["순번", "제안명", "연도", "전화"], rows + rows[:1], enc="utf-8-sig")
    first = list(mapped_contest_csv(spec, b"x" * 32))
    reordered = [[str(i), *row[1:3], "010-9999-8888"] for i, row in enumerate(rows[::-1], 1)]
    _write_csv(f, ["순번", "제안명", "연도", "전화"], reordered, enc="cp949")
    second = list(mapped_contest_csv(spec, b"x" * 32))
    assert len(first) == len(second) == 2
    assert {r["title"]: r["idea_id"] for r in first} == {r["title"]: r["idea_id"] for r in second}


def test_mapped_real_key_survives_title_update_and_rejects_conflicts(tmp_path):
    import pytest

    from bluebird.sources import mapped_contest_csv

    f = tmp_path / "mapped.csv"
    spec = SourceSpec("mapped", "mapped_contest_csv", f, "n", "l", "", 2, False,
                      columns={"title": "제안명", "key": "접수번호"})
    _write_csv(f, ["접수번호", "제안명"], [["K-42", "빗물 회수"]])
    first, = mapped_contest_csv(spec, b"x" * 32)
    _write_csv(f, ["접수번호", "제안명"], [["K-42", "빗물 회수 장치"]])
    updated, = mapped_contest_csv(spec, b"x" * 32)
    assert updated["idea_id"] == first["idea_id"]
    _write_csv(f, ["접수번호", "제안명"], [["K-42", "빗물 회수"], ["K-42", "다른 작품"]])
    with pytest.raises(ValueError, match="conflicting records"):
        list(mapped_contest_csv(spec, b"x" * 32))


def test_mapped_filters_require_real_content_and_expected_headers(tmp_path):
    import pytest

    from bluebird.sources import mapped_contest_csv

    f = _write_csv(tmp_path / "mapped.csv", ["제안명", "설명", "공개여부"], [
        ["마을 이름", "", "Y"], ["실제 프로젝트", "개선 방법", "Y"],
        ["비공개", "비공개 방법", "N"], ["테스트", "기능 확인", "Y"],
    ])
    spec = SourceSpec("mapped", "mapped_contest_csv", f, "n", "l", "", 2, False,
                      columns={"title": "제안명", "body": ["설명"]}, require_any=["설명"],
                      row_equals={"공개여부": "Y"}, exclude={"제안명": ["테스트"]})
    assert [r["title"] for r in mapped_contest_csv(spec, b"x" * 32)] == ["실제 프로젝트"]
    _write_csv(f, ["제안명", "설명"], [["작품", "방법"]])
    with pytest.raises(ValueError, match="missing required headers: 공개여부"):
        list(mapped_contest_csv(spec, b"x" * 32))


def test_mapped_record_preserves_verified_detail_url_and_full_long_title(tmp_path):
    import pytest

    from bluebird.sources import mapped_contest_csv

    title = "물의 흐름을 이용한 장치 " * 40
    url = "https://www.science.go.kr/mps/1079/bbs/423/moveBbsNttDetail.do?nttSn=21841"
    f = _write_csv(tmp_path / "mapped.csv", ["title", "source_url"], [[title, url]])
    spec = SourceSpec("mapped", "mapped_contest_csv", f, "n", "l",
                      "https://www.science.go.kr/mps/1079/bbs/423/list.do", 2, False,
                      columns={"title": "title", "source_url": "source_url"})
    record, = mapped_contest_csv(spec, b"x" * 32)
    assert record["source_url"] == url
    assert record["title"] == title.strip()[:300] and record["body"] == title.strip()
    assert record["year"] is None
    _write_csv(f, ["title", "source_url"], [["장치", "https://other.example/project"]])
    with pytest.raises(ValueError, match="official source host"):
        list(mapped_contest_csv(spec, b"x" * 32))
