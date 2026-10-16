from bluebird.signals.catalog import title_norm


def test_title_norm_merges_reregistrations():
    a = title_norm("서울특별시_공공자전거 대여소 정보_20250115")
    assert a == title_norm("서울특별시 공공자전거 대여소 정보(2024년)")
    assert a == title_norm("서울특별시_공공자전거_대여소_정보")
    assert a != title_norm("서울특별시_공공자전거 이용현황")


def test_title_norm_nfkc():
    assert title_norm("ＡＢＣ 데이터") == title_norm("abc데이터")
