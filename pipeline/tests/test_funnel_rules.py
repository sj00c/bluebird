import pathlib
import re

import pytest

from bluebird import announce, funnel, score, wording


@pytest.mark.parametrize("scores,kinds,verdict,s", [
    ({"data": 5}, {"dataset_opened"}, "hold", 5.0),                                     # 항목 1개 → hold
    ({"data": 5, "policy": 4}, {"dataset_opened"}, "now", 4.5),                         # 계획 예시
    ({"data": 4, "regulation": 2}, {"dataset_opened"}, "conditional", 3.0),             # 계획 예시
    ({"tech": 5, "policy": 5}, {"dataset_opened"}, "hold", 5.0),                        # 바뀐 것 축(data) 미채점
    ({"regulation": 4, "tech": 3, "data": None}, {"law_effective"}, "conditional", 3.5),
    ({"regulation": 2, "tech": 2}, {"law_effective"}, "hold", 2.0),
    ({}, set(), "hold", None),
])
def test_s_rule(scores, kinds, verdict, s):
    r = score.compute(scores, kinds)
    assert (r.verdict, r.s) == (verdict, s)
    if verdict != "hold":
        assert r.n_scored >= 2


def test_s_threshold_not_rounded_up():
    # 3.995는 반올림하면 4.0이지만 now가 아니다
    r = score.compute({"data": 4, "policy": 4, "tech": 4, "regulation": 3.98}, {"dataset_opened"})
    assert r.verdict == "conditional"


def test_s_rejects_out_of_range():
    with pytest.raises(ValueError):
        score.compute({"data": 6}, {"dataset_opened"})


def test_trace_not_run_is_pending_never_none():
    req = funnel.required_items("full_v1", env={})
    assert req == ("manual",)
    assert funnel.decide_trace("full_v1", {}, req) == ("pending", "not_done")
    # 키가 없어 사람 확인만 했으면 외부 검색은 미실시(포털에 "외부 검색 미실시")
    assert funnel.decide_trace("full_v1", {"manual": {"result": "none"}}, req) == ("none", "not_done")
    req_keys = funnel.required_items("full_v1", env={"NAVER_CLIENT_ID": "a", "NAVER_CLIENT_SECRET": "b"})
    assert req_keys == ("news_web", "manual")
    checks = {"manual": {"result": "none"}, "news_web": {"result": "not_run"}}
    assert funnel.decide_trace("full_v1", checks, req_keys)[0] == "pending"
    checks["news_web"] = {"result": "none"}
    assert funnel.decide_trace("full_v1", checks, req_keys) == ("none", "done")


def test_trace_manual_status_wins_and_kipris_local():
    req = ("manual",)
    assert funnel.decide_trace("full_v1", {"manual": {"result": "found", "status": "realized"}}, req)[0] == "realized"
    lreq = funnel.required_items("kipris_local_v1")
    assert funnel.decide_trace("kipris_local_v1", {"ip_local": {"result": "none"}}, lreq)[0] == "pending"
    both_none = {"ip_local": {"result": "none"}, "similar_local": {"result": "none"}}
    assert funnel.decide_trace("kipris_local_v1", both_none, lreq) == ("none", "not_done")
    linked = {"ip_local": {"result": "found"}, "similar_local": {"result": "none"}}
    assert funnel.decide_trace("kipris_local_v1", linked, lreq)[0] == "pending"


@pytest.mark.parametrize("text", [
    "그때 없던 데이터", "당시 없었던 정보", "당시에는 미개방이던 자료", "그 당시 존재하지 않던",
    "그땐 없던 API", "그때까지 없던 데이터", "예전엔 없던 서비스", "과거에는 없었고", "당시에는 없었으나",
    "존재하지 않던 데이터", "공모 당시 공개되지 않았던 통계", "그때는 이런 데이터가 없었다",
])
def test_forbidden_phrase_rejected(text):
    with pytest.raises(wording.WordingError):
        wording.check("앞 문장. " + text)


def test_allowed_phrases():
    wording.check("포털 등록 2024-03-01", "파랑새 관측 2026-10-12 신규", "그때는 규제로 막혔다",
                  "사후통보가 전화·팩스로만 가능해 대체조제가 어려웠다", "주차면 데이터가 없어 추정한다",
                  "이제 시스템으로 통보할 수 있다")


def test_no_forbidden_phrase_in_screens_or_pipeline_text():
    root = pathlib.Path(__file__).resolve().parents[2]
    offenders = []
    for base, pat in ((root / "web/portal", "**/*.tsx"), (root / "web/portal", "**/*.ts"),
                      (root / "pipeline/bluebird", "**/*.py"), (root / "pipeline/bluebird", "**/*.sql")):
        for f in base.glob(pat):
            if "node_modules" in f.parts or f.name == "wording.py":
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if wording.FORBIDDEN.search(line):
                    offenders.append(f"{f.relative_to(root)}:{n}")
    assert offenders == []


def test_kstartup_parse_skips_rows_without_url_or_id():
    items, raw = announce.parse_kstartup({"data": [
        {"pbanc_sn": 176001, "biz_pbanc_nm": "2026 예비창업패키지", "pbanc_ntrp_nm": "창업진흥원",
         "pbanc_rcpt_bgng_dt": "20261001", "pbanc_rcpt_end_dt": "20261031",
         "detl_pg_url": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=176001"},
        {"pbanc_sn": 2, "biz_pbanc_nm": "URL 없음", "detl_pg_url": ""},
    ]})
    assert (len(items), raw) == (1, 2)
    a = items[0]
    assert a["id"] == "kstartup:176001" and str(a["apply_to"]) == "2026-10-31"
    assert re.match(r"https://www\.k-startup\.go\.kr/", a["url"])


def test_specific_tokens_drop_generic_words():
    assert funnel.specific_tokens("사진 정보") == ["사진"]          # 후보 생성 안 함(<2)
    assert funnel.specific_tokens("저상버스 배차 데이터") == ["저상버스", "배차"]


def test_kstartup_parse_fails_closed_on_unknown_format():
    with pytest.raises(announce.AnnounceFormatError, match="no data list"):
        announce.parse_kstartup({"response": {"header": {"resultCode": "30"}}})
    renamed = {"data": [{"pbancSn": 1, "bizPbancNm": "이름 바뀜", "detlPgUrl": "https://www.k-startup.go.kr/x",
                         "pbancRcptBgngDt": "20261001"}]}
    with pytest.raises(announce.AnnounceFormatError, match="none parsed"):
        announce.parse_kstartup(renamed)
    assert announce.parse_kstartup({"data": []}) == ([], 0)


@pytest.mark.parametrize("url", ["https://k-startup.go.kr.evil.com/x", "https://evil.com/k-startup.go.kr", "nota-url"])
def test_announce_add_rejects_non_kstartup_hosts(url):
    with pytest.raises(ValueError, match="K-Startup"):
        announce.add(dsn="unused", url=url, title="t", org=None, apply_from=None, apply_to=None, summary=None, by="t")


def test_announce_add_requires_apply_from():
    with pytest.raises(ValueError, match="apply-from"):
        announce.add(dsn="unused", url="https://www.k-startup.go.kr/x?pbancSn=1", title="t", org=None,
                     apply_from=None, apply_to=None, summary=None, by="t")
