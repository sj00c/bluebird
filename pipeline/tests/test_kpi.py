"""G006: KPI 도구(κ·골드셋·Top 20·G1–G13 현황표)."""

from datetime import date

import psycopg
import pytest

from bluebird import kpi
from tests.test_db_integration import DSN, _pub_db, _seed_idea

IID = "ID-2019-aaaaaaaaaa"
db_only = pytest.mark.skipif(not DSN, reason="BB_TEST_DSN not set")


def test_cohen_kappa_known_values():
    assert kpi.cohen_kappa([]) is None
    assert kpi.cohen_kappa([("R", "R"), ("D", "D")]) == 1.0
    # 2×2 교과서 예: po=0.7, pe=0.5 → κ=0.4
    pairs = [("R", "R")] * 20 + [("R", "D")] * 5 + [("D", "R")] * 10 + [("D", "D")] * 15
    assert kpi.cohen_kappa(pairs) == pytest.approx(0.4)
    assert kpi.cohen_kappa([("R", "R")] * 3) == 1.0  # 모두 같은 코드(pe=1)


@pytest.fixture()
def fresh():
    name = "bbtest"
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {name}")
    dsn = DSN.rsplit("/", 1)[0] + f"/{name}"
    from bluebird import db
    db.migrate(dsn, "core")
    return dsn


def _code(c, iid, a, b):
    for rnd, who, code in (("coder_a", "lee", a), ("coder_b", "park", b)):
        if code:
            c.execute("INSERT INTO core.review (target_type, target_id, reviewer, round, decision, code)"
                      " VALUES ('idea',%s,%s,%s,'code',%s)", (iid, who, rnd, code))


@db_only
def test_kappa_status_follows_human_coding(fresh):
    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        ids = [IID] + [f"ID-2019-{n:010x}" for n in range(1, 4)]
        for iid in ids[1:]:
            c.execute("INSERT INTO core.idea (id, source_id, contest_id, year, title, team_kind, first_ingest_id,"
                      " last_ingest_id) VALUES (%s,'s','C-1',2019,'t','empty',1,1)", (iid,))
        for iid in ids:
            c.execute("INSERT INTO core.coding_sample VALUES ('k4',%s,'s:-',1)", (iid,))
        c.commit()
    assert kpi.kappa(dsn=fresh, sample_id="k4")["status"] == kpi.HUMAN  # 코딩 0
    with psycopg.connect(fresh) as c:
        _code(c, ids[0], "R", "R")
        _code(c, ids[1], "D", None)
        c.commit()
    r = kpi.kappa(dsn=fresh, sample_id="k4")
    assert (r["status"], r["coded_pairs"], r["coded_a"], r["coded_b"]) == (kpi.PROGRESS, 1, 2, 1)
    with psycopg.connect(fresh) as c:
        c.execute("INSERT INTO core.review (target_type, target_id, reviewer, round, decision, code)"
                  " VALUES ('idea',%s,'park','coder_b','code','D')", (ids[1],))
        _code(c, ids[2], "M", "M")
        _code(c, ids[3], "T", "R")
        c.commit()
    r = kpi.kappa(dsn=fresh, sample_id="k4")
    # po=3/4, pe=(R:1·2 + D:1·1 + M:1·1 + T:1·0)/16=4/16 → κ=(0.75-0.25)/0.75
    assert r["kappa"] == pytest.approx(0.667, abs=1e-3) and r["status"] == kpi.FAIL
    assert r["per_code_agreement"]["R"] == 0.5 and r["per_code_agreement"]["T"] == 0.0 and r["u_share"] == 0.0
    with pytest.raises(KeyError):
        kpi.kappa(dsn=fresh, sample_id="nope")


@db_only
def test_goldset_matches_by_year_title_and_reports_pending(fresh):
    from bluebird import funnel
    gold = ("pid,year,team,item,final\n"
            "1,2019,팀가나다,  제목 ,none\n"
            "2,2019,팀라마,없는 제목,realized\n")
    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.commit()
    r = kpi.goldset(dsn=fresh, gold_csv=gold)
    assert (r["matched_ideas"], r["unmatched"], r["pending"], r["decided"], r["status"]) == (1, 1, 1, 0, kpi.KEY)
    funnel.trace_manual(dsn=fresh, idea_id=IID, result="none", status=None, url=None, note="없음", by="t")
    r = kpi.goldset(dsn=fresh, gold_csv=gold, baseline=True)
    assert (r["decided"], r["confusion"]["none"]["none"], r["macro_f1"], r["status"]) == (1, 1, 100.0, kpi.PASS)
    with psycopg.connect(fresh) as c:  # 팀명은 어디에도 남지 않는다
        assert c.execute("SELECT count(*) FROM core.pipeline_run WHERE stats::text LIKE '%팀가나다%'").fetchone()[0] == 0
    with pytest.raises(ValueError, match="not in"):
        kpi.goldset(dsn=fresh, gold_csv="year,item,final\n2019,제목,maybe\n")


@db_only
def test_top20_and_report(fresh):
    from bluebird import funnel, publish
    from tests.test_console_objection import _to_stage4

    _to_stage4(fresh)
    funnel.approve(dsn=fresh, idea_id=IID, by="t")
    week = date(2026, 10, 12)
    funnel.compute_top(dsn=fresh, week=week)
    pub = _pub_db()
    publish.push(core_dsn=fresh, publish_dsn=pub)
    t = kpi.verify_top20(dsn=fresh, publish_dsn=pub, week=week)
    assert (t["core_top"], t["published"], t["expert_approved"], t["status"]) == (1, 1, 0, kpi.HUMAN)
    with psycopg.connect(fresh) as c:
        c.execute("INSERT INTO core.review (target_type, target_id, reviewer, round, decision)"
                  " VALUES ('idea',%s,'jung','expert','approve')", (IID,))
        c.commit()
    assert kpi.verify_top20(dsn=fresh, publish_dsn=pub, week=week)["status"] == kpi.PASS

    rows = {r["goal"]: r for r in kpi.report(dsn=fresh, publish_dsn=pub, inbox_dsn=pub, p95_ms=50.0, week=week)}
    assert list(rows) == [f"G{n}" for n in range(1, 14)]
    assert rows["G1"]["status"] == kpi.FAIL  # 테스트 DB는 카드 1건(<10,000)
    assert rows["G2"]["status"] == kpi.PASS and rows["G5"]["status"] == kpi.PASS
    assert rows["G3"]["status"] == kpi.HUMAN and rows["G12"]["status"] == kpi.HUMAN
    assert rows["G8"]["status"] == kpi.PASS and rows["G9"]["status"] == kpi.PASS
    assert rows["G10"]["status"] == kpi.PASS, rows["G10"]
    assert rows["G11"]["status"] == kpi.PROGRESS  # 처리된 이의 0
    # 공개된 진단에서 근거를 떼면(트리거 우회) G9가 잡는다
    with psycopg.connect(fresh) as c:
        c.execute("ALTER TABLE core.x_evidence DISABLE TRIGGER x_evidence_revoke")
        c.execute("DELETE FROM core.x_evidence WHERE target_type='diagnosis'")
        c.execute("ALTER TABLE core.x_evidence ENABLE TRIGGER x_evidence_revoke")
        c.commit()
    with psycopg.connect(fresh) as c:
        assert kpi.audit_g9(c)["diagnosis"] == 1
