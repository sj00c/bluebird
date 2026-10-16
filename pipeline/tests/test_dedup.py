from bluebird.dedup import DAEGU, plan


def row(api, key, title, body=None, *, contest=None, year=2020, award=None, date=None, lot=None):
    return {"api": api, "key": key, "title": title, "body": body, "contest": contest, "year": year,
            "award": award, "date": date, "lot": lot}


def test_same_text_keeps_earliest_and_title_alone_is_not_duplicate():
    out = plan([
        row("seoul", "b", "공원 의자", "벤치를  놓자", date="2021-03-01"),
        row("seoul", "a", "공원의자!", "벤치를 놓자", date="2020-05-01"),
        row("seoul", "c", "공원 의자", "다른 내용"),
        row("seoul", "d", "공원 의자", "벤치를 놓자"),                 # 날짜·연도 기준 2020-01-01 → 가장 이름
    ])
    assert out == {("seoul", "a"): (("seoul", "d"), "같은 글"), ("seoul", "b"): (("seoul", "d"), "같은 글")}


def test_daegu_uses_lot_not_body_and_keeps_latest():
    out = plan([
        row(DAEGU, "1", "CCTV 설치", "정형 문구", year=2023, lot="동 1"),
        row(DAEGU, "2", "CCTV 설치", "정형 문구", year=2024, lot="동1"),
        row(DAEGU, "3", "CCTV 설치", "정형 문구", year=2024, lot="동 2"),
    ])
    assert out == {(DAEGU, "1"): ((DAEGU, "2"), "같은 장소")}


def test_entry_across_sources_needs_same_award_and_chain_points_to_final_head():
    out = plan([
        row("museum", "m", "해파리 콜라겐 페이퍼", contest="제69회 전국과학전람회", year=2023, award="장려상"),
        row("archive", "x", "해파리 콜라겐 페이퍼", "본문 있음", contest="전국과학전람회", year=2022, award="장려상"),
        row("archive", "y", "해파리 콜라겐 페이퍼", "본문 있음", contest="전국과학전람회", year=2022, award="장려상"),
        row("kipris", "k", "해파리 콜라겐 페이퍼", contest="전국과학전람회", year=2023, award="우수상"),  # 등급 다름
        row("museum", "n", "해파리 콜라겐 페이퍼", contest="전국과학전람회", year=2020, award="장려상"),  # 연도 차 2 이상
    ])
    assert out == {("archive", "y"): (("archive", "x"), "같은 글"), ("museum", "m"): (("archive", "x"), "같은 출품작")}
