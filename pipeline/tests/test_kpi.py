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
def test_kappa_status_follows_human_coding(fresh, monkeypatch):
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
    assert r["status"] == kpi.PROGRESS  # 다 코딩했어도 100건 미만 표본(파일럿)은 통과로 치지 않는다
    monkeypatch.setattr(kpi, "KAPPA_MIN_SAMPLE", 4)
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
    assert (r["matched_ideas"], r["unmatched"], r["pending"], r["decided"], r["status"]) == (1, 1, 1, 0, kpi.PROGRESS)
    with psycopg.connect(fresh) as c:  # 흔적 검색 키가 없다는 점검 기록이 있으면 key_required
        c.execute("INSERT INTO core.source_check (source_id, status) VALUES ('naver_search_news','key_required')")
        c.commit()
    assert kpi.goldset(dsn=fresh, gold_csv=gold)["status"] == kpi.KEY
    funnel.trace_manual(dsn=fresh, idea_id=IID, result="none", status=None, url=None, note="없음", by="t")
    r = kpi.goldset(dsn=fresh, gold_csv=gold)
    assert (r["decided"], r["status"]) == (1, kpi.PROGRESS)  # 기준선이 없으면 회귀를 판정하지 않는다
    r = kpi.goldset(dsn=fresh, gold_csv=gold, baseline=True)
    assert (r["decided"], r["confusion"]["none"]["none"], r["macro_f1"], r["status"]) == (1, 1, 100.0, kpi.PASS)
    assert kpi.goldset(dsn=fresh, gold_csv=gold)["status"] == kpi.PASS  # 기준선 대비 하락 없음
    # 판정이 정답과 달라지면 macro-F1이 100 → 0, 5pt 넘게 떨어져 FAIL
    funnel.trace_manual(dsn=fresh, idea_id=IID, result="found", status="realized", url="https://a.kr/x",
                        note="사업화", by="t")
    assert kpi.goldset(dsn=fresh, gold_csv=gold)["status"] == kpi.FAIL
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
    assert (t["core_top"], t["published"], t["status"]) == (1, 1, kpi.PROGRESS)  # 1건 < 목표 20
    t = kpi.verify_top20(dsn=fresh, publish_dsn=pub, week=week, target=1)  # E3 조정 목표
    assert (t["expert_approved"], t["status"]) == (0, kpi.HUMAN)
    with psycopg.connect(fresh) as c:
        c.execute("INSERT INTO core.review (target_type, target_id, reviewer, round, decision)"
                  " VALUES ('idea',%s,'jung','expert','approve')", (IID,))
        c.commit()
    assert kpi.verify_top20(dsn=fresh, publish_dsn=pub, week=week, target=1)["status"] == kpi.PASS
    with psycopg.connect(pub) as c:  # 공개본이 core Top과 다르면 FAIL
        c.execute("DELETE FROM publish.weekly_top")
        c.commit()
    assert kpi.verify_top20(dsn=fresh, publish_dsn=pub, week=week, target=1)["status"] == kpi.FAIL
    publish.push(core_dsn=fresh, publish_dsn=pub)

    def rep(**kw):
        return {r["goal"]: r for r in kpi.report(dsn=fresh, publish_dsn=pub, inbox_dsn=pub, p95_ms=50.0, week=week,
                                                 top_target=1, **kw)}

    clean = {"name_matches": 0, "compared": 1, "ideas_with_names": 1, "source_files": 1, "missing_files": 0}
    rows = rep(names=clean)
    assert list(rows) == [f"G{n}" for n in range(1, 14)]
    assert rows["G1"]["status"] == kpi.FAIL  # 테스트 DB는 카드 1건(<10,000)
    assert rows["G2"]["status"] == kpi.PASS and rows["G5"]["status"] == kpi.PASS
    assert rows["G3"]["status"] == kpi.HUMAN and rows["G12"]["status"] == kpi.HUMAN
    assert rows["G8"]["status"] == kpi.PASS and rows["G9"]["status"] == kpi.PASS
    assert rows["G10"]["status"] == kpi.PASS, rows["G10"]
    assert rows["G11"]["status"] == kpi.PROGRESS  # 처리된 이의 0
    assert rows["G13"]["status"] == kpi.PROGRESS  # must 원격 소스 점검 기록 없음
    # G10: 이름 대조를 안 했으면 진행 중, 이름이 남아 있으면 FAIL
    assert rep()["G10"]["status"] == kpi.PROGRESS
    assert rep(names={**clean, "name_matches": 1})["G10"]["status"] == kpi.FAIL
    # G13: must 소스가 egress에서 막히면(blocked) FAIL, 범위 밖(BLOCKED 목록)은 무시, 키 대기는 통과
    from bluebird.sources_check import REMOTES
    with psycopg.connect(fresh) as c:
        for r in REMOTES:
            c.execute("INSERT INTO core.source_check (source_id, status) VALUES (%s,%s)",
                      (r.id, "key_required" if r.key_env else "ok"))
        c.execute("INSERT INTO core.source_check (source_id, status) VALUES ('modu_idea','blocked')")
        c.commit()
    assert rep(names=clean)["G13"]["status"] == kpi.PASS
    with psycopg.connect(fresh) as c:
        must_id = next(r.id for r in REMOTES if r.tier == "must")
        c.execute("INSERT INTO core.source_check (source_id, status) VALUES (%s,'blocked')", (must_id,))
        c.commit()
    assert rep(names=clean)["G13"]["status"] == kpi.FAIL
    # G1: 카드 없는 아이디어가 있으면 FAIL 사유로 드러난다
    assert "카드 없음 0" in rows["G1"]["value"]
    # 공개된 진단에서 근거를 떼면(트리거 우회) G9가 잡는다
    with psycopg.connect(fresh) as c:
        c.execute("ALTER TABLE core.x_evidence DISABLE TRIGGER x_evidence_revoke")
        c.execute("DELETE FROM core.x_evidence WHERE target_type='diagnosis'")
        c.execute("ALTER TABLE core.x_evidence ENABLE TRIGGER x_evidence_revoke")
        c.commit()
    with psycopg.connect(fresh) as c:
        assert kpi.audit_g9(c)["diagnosis"] == 1


@db_only
def test_name_leaks_end_to_end(fresh, tmp_path):
    """원본 파일을 같은 익명화 키로 다시 읽어 공개 글에 이름이 남았는지 센다. 파일이 없거나 키가 다르면 대조 안 됨."""
    import csv

    from bluebird import cards, db, ingest, publish
    from bluebird.funnel import dumps

    (tmp_path / "secret").write_bytes(b"s" * 32)
    (tmp_path / "other").write_bytes(b"o" * 32)
    cfg = tmp_path / "sources.toml"
    cfg.write_text('[[source]]\nid="d"\nadapter="design_idea_csv"\nfile="d.csv"\nname="n"\nlicense="l"\nlayer=2\n'
                   'public_ok=true\nexport_grade="O"\npolicy_approved_by="t"\npolicy_approved_at="2026-10-06"\n',
                   encoding="utf-8")
    with (tmp_path / "d.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["등록번호", "연도", "포상", "수상자", "제목", "내용"])
        w.writerow(["1", "2022", "대상", "이민수", "휠체어 충전 테이블", "이민수가 만든 압전 충전 테이블"])
        w.writerow(["2", "2022", "상", "최준영", "경계를 잇다", "길 위의 벤치"])
    ingest.ingest(dsn=fresh, config=cfg, seed_dir=tmp_path, secret_path=tmp_path / "secret")
    cards.build(dsn=fresh)
    pub = _pub_db()
    publish.push(core_dsn=fresh, publish_dsn=pub)
    secret = (tmp_path / "secret").read_bytes()

    def leaks(**kw):
        with db.connect(pub) as pc:
            return kpi.name_leaks(pc, **{"config": cfg, "seed_dir": tmp_path, "secret": secret, **kw})

    clean = leaks()
    assert (clean["name_matches"], clean["compared"], clean["source_files"], clean["missing_files"]) == (0, 2, 1, 0)
    assert kpi.names_checked(clean) and "이민수" not in dumps(clean)
    with psycopg.connect(pub) as c:  # 공개 글에 이름이 새어 나간 경우
        c.execute("UPDATE publish.idea SET body = body || ' 문의: 최준영' WHERE title = '경계를 잇다'")
        c.commit()
    assert leaks()["name_matches"] == 1
    wrong = leaks(secret=(tmp_path / "other").read_bytes())  # 키가 다르면 ID가 안 맞아 대조 0
    assert wrong["compared"] == 0 and not kpi.names_checked(wrong)
    (tmp_path / "d.csv").rename(tmp_path / "gone.csv")
    gone = leaks()
    assert gone["missing_files"] == 1 and not kpi.names_checked(gone)
    with db.connect(fresh) as conn, db.connect(pub) as pc:
        assert kpi.audit_g10(conn, pc, names=gone)["name_matches"] is None


@db_only
def test_g6_counts_published_window_changes_and_fails_after_window(fresh, monkeypatch):
    from datetime import date

    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.commit()
    pub = _pub_db()
    from bluebird import publish
    publish.push(core_dsn=fresh, publish_dsn=pub)
    rows = {r["goal"]: r for r in kpi.report(dsn=fresh, publish_dsn=pub)}
    assert rows["G6"]["status"] == kpi.PROGRESS and "창 안 신규 0건" in rows["G6"]["value"]
    monkeypatch.setattr(kpi, "today_kst", lambda: date(2026, 12, 8))
    rows = {r["goal"]: r for r in kpi.report(dsn=fresh, publish_dsn=pub)}
    assert rows["G6"]["status"] == kpi.FAIL  # 창이 닫혔는데 10건 미만


@db_only
def test_report_g3_uses_100_sample_not_pilot(fresh):
    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.execute("INSERT INTO core.coding_sample VALUES ('pilot30',%s,'s:-',1)", (IID,))
        c.commit()
    pub = _pub_db()
    from bluebird import publish
    publish.push(core_dsn=fresh, publish_dsn=pub)
    g3 = {r["goal"]: r for r in kpi.report(dsn=fresh, publish_dsn=pub)}["G3"]
    assert g3["status"] == kpi.HUMAN and "100건 표본 없음" in g3["value"]  # 파일럿 표본은 기준이 아니다
    g3 = {r["goal"]: r for r in kpi.report(dsn=fresh, publish_dsn=pub, kappa_sample="nope")}["G3"]
    assert g3["status"] == kpi.HUMAN and "nope 없음" in g3["value"]


@db_only
def test_cli_exit_codes(fresh):
    from bluebird import cli
    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.commit()
    gold = "year,item,final\n2019,제목,none\n"
    import io
    import sys
    old = sys.stdin
    try:
        sys.stdin = io.StringIO(gold)
        assert cli.main(["eval", "goldset", "--dsn", fresh, "--gold", "-"]) == 0  # 진행 중
    finally:
        sys.stdin = old
    pub = _pub_db()
    from bluebird import publish
    publish.push(core_dsn=fresh, publish_dsn=pub)
    assert cli.main(["verify", "top20", "--dsn", fresh, "--publish-dsn", pub]) == 0  # Top 없음 → 진행 중
    assert cli.main(["kpi", "report", "--dsn", fresh, "--publish-dsn", pub, "--secret", "/nonexistent"]) == 1  # G1 FAIL
