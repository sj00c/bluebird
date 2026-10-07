import re

from bluebird import publish
from bluebird.signals.catalog import title_norm


def test_title_norm_merges_reregistrations():
    a = title_norm("서울특별시_공공자전거 대여소 정보_20250115")
    assert a == title_norm("서울특별시 공공자전거 대여소 정보(2024년)")
    assert a == title_norm("서울특별시_공공자전거_대여소_정보")
    assert a != title_norm("서울특별시_공공자전거 이용현황")


def test_title_norm_nfkc():
    assert title_norm("ＡＢＣ 데이터") == title_norm("abc데이터")


def _template_columns() -> dict[str, list[str]]:
    text, _ = publish.template()
    out = {}
    for m in re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\);", text, re.DOTALL):
        cols = []
        for line in m.group(2).splitlines():
            line = line.strip()
            if line and not line.startswith(("PRIMARY KEY", "UNIQUE", "CHECK", "--")):
                cols.append(line.split()[0])
        out[m.group(1)] = cols
    return out


def test_publish_columns_match_template():
    """공개 DB로 나가는 열 = 템플릿 열(허용목록). 템플릿에 없는 열을 보내거나 빠뜨리지 않는다."""
    tpl = _template_columns()
    assert set(tpl) == set(publish.ORDER)
    for t in publish.ORDER:
        assert list(publish.columns(t)) == tpl[t], t


def test_publish_template_has_no_internal_columns():
    cols = {c for cs in _template_columns().values() for c in cs}
    assert not cols & {"team_kind", "extra", "first_ingest_id", "last_ingest_id", "export_grade", "reviewer",
                       "note", "body_present", "policy_approved_by", "model", "prompt_version"}


def test_template_checksum_stable():
    _, a = publish.template()
    _, b = publish.template()
    assert a == b and len(a) == 64
