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
