from bluebird.budget_detail import gg_fields, match, match_position, ulsan_fields
from bluebird.html_text import th_sections, th_value


def cand(i, *fields, body="b"):
    return {"id": i, "url": f"u{i}", "body": body, "fields": tuple(fields)}


def test_match_exact_order_loose_and_none():
    rows = [("1", ("2024", "cctv", "안산", "50")),
            ("2", ("2024", "스쿨존", "광명", "0")), ("3", ("2024", "스쿨존", "광명", "0")),
            ("4", ("2024", "벤치", "파주", "10")),   # 예산 다름 → 지역까지 같은 후보 1건이면 loose
            ("5", ("2024", "없음", "수원", "1"))]
    cands = [cand("10", "2024", "cctv", "안산", "50"), cand("20", "2024", "cctv", "안산", "7"),
             cand("31", "2024", "스쿨존", "광명", "0"), cand("30", "2024", "스쿨존", "광명", "0"),
             cand("40", "2024", "벤치", "파주", "12")]
    got = {k: (c["id"] if c else None, how) for k, (c, how) in match(rows, cands).items()}
    assert got == {"1": ("10", "exact"), "2": ("30", "order"), "3": ("31", "order"), "4": ("40", "loose"),
                   "5": (None, "none")}


def test_loose_needs_unique_candidate():
    rows = [("1", ("2024", "벤치", "파주", "10"))]
    cands = [cand("1", "2024", "벤치", "파주", "11"), cand("2", "2024", "벤치", "파주", "12")]
    assert match(rows, cands)["1"] == (None, "none")


def test_position_pairs_same_or_contained_titles_and_title_matches_rest():
    rows = [("1", ("가",)), ("2", ("나",)), ("10", ("경제교육",))]
    same = [cand("9", "가"), cand("8", "나"), cand("7", "관평동경제교육")]   # 사이트가 제목 보완
    assert {k: (c["id"], how) for k, (c, how) in match_position(rows, same).items()} == {
        "1": ("9", "position"), "2": ("8", "position"), "10": ("7", "position")}
    shuffled = [cand("9", "나"), cand("8", "가"), cand("7", "다")]
    assert {k: (c["id"] if c else None, how) for k, (c, how) in match_position(rows, shuffled).items()} == {
        "1": ("8", "exact"), "2": ("9", "exact"), "10": (None, "none")}


def test_row_fields_normalize_like_site():
    assert gg_fields({"RCPT_YR": "2024", "BIZ_NM": "안전한 스쿨존", "BIZ_LOC": "안산시", "BIZ_EXPN": 50000000.0}) == (
        "2024", "안전한스쿨존", "안산시", "50000000")
    assert ulsan_fields({"년도": "2021년", "사업명": "벤치 설치", "사업위치": "남목2동 앞"}) == ("2021", "벤치설치", "남목2동앞")


def test_th_fields_strip_tags_and_hidden_label():
    page = ('<tr><th scope="row">사업내용</th><td colspan="3"><label style="display:none">사업내용</label>'
            '<textarea>첫 줄&amp;</textarea><br/>둘째</td></tr><tr><th>사업효과</th><td></td></tr>')
    assert th_value(page, "사업내용") == "첫 줄&\n둘째"
    assert th_sections(page, ("사업목적", "사업내용", "사업효과")) == "[사업내용] 첫 줄&\n둘째"
