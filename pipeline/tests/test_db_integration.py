"""DB 통합 테스트. BB_TEST_DSN(빈 pgvector DB, superuser)이 있을 때만 실행한다.

    docker run -d --rm --name bb-testdb -e POSTGRES_PASSWORD=t -p 55432:5432 pgvector/pgvector:pg16
    BB_TEST_DSN=postgresql://postgres:t@localhost:55432/postgres uv run pytest tests/test_db_integration.py
"""

import os
from datetime import date

import psycopg
import pytest

from bluebird import db, publish, wording
from bluebird.db import MigrationChecksumError
from bluebird.signals import catalog

DSN = os.environ.get("BB_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="BB_TEST_DSN not set")

HEADER = list(catalog.COLS)


def _csv(path, rows):
    import csv
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for r in rows:
            w.writerow([r.get(h, "") for h in HEADER])
    return path


def _row(pk, title, org_code="100", registered="2015-01-01"):
    return {"목록키": pk, "목록유형": "FILE", "목록명": title, "제공기관코드": org_code, "제공기관": "기관",
            "등록일": registered, "수정일": registered, "설명": "d", "이용허락범위": "제한 없음"}


@pytest.fixture()
def fresh(tmp_path):
    name = "bbtest"
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {name}")
    dsn = DSN.rsplit("/", 1)[0] + f"/{name}"
    db.migrate(dsn, "core")
    return dsn


def test_migration_checksum_guard(fresh, monkeypatch):
    files = db.migration_files("core")
    monkeypatch.setattr(db, "migration_files", lambda t: [(files[0][0], "0" * 64, files[0][2])])
    with pytest.raises(MigrationChecksumError):
        db.migrate(fresh, "core")


def test_catalog_tiers_and_reregistration(fresh, tmp_path):
    s0 = _csv(tmp_path / "s0.csv", [_row("1", "서울시_자전거 대여소_20240101"), _row("2", "기존 데이터")])
    catalog.import_snapshot(dsn=fresh, path=s0, taken_at=date(2026, 10, 6))
    s1 = _csv(tmp_path / "s1.csv", [
        _row("1", "서울시_자전거 대여소_20240101"), _row("2", "기존 데이터"),
        _row("3", "새 데이터", registered="2026-10-08"),               # 관측 신규
        _row("4", "오래된 데이터", registered="2019-03-01"),          # 다시 나타남
        _row("5", "서울시 자전거 대여소(2026년)", registered="2026-10-09"),  # 1의 재등록
        _row("6", "서울시 자전거 대여소", org_code="999", registered="2026-10-09"),  # 다른 기관 → 신규
    ])
    res = catalog.import_snapshot(dsn=fresh, path=s1, taken_at=date(2026, 10, 12))
    assert res["snapshot_id"] == 1 and res["new"] == 4
    with psycopg.connect(fresh) as c:
        got = dict(c.execute("SELECT public_data_pk, tier || coalesce(':' || rereg_of, '') FROM core.signal_dataset"))
        changes = {r[0] for r in c.execute("SELECT ref_id FROM core.condition_change")}
    assert got == {"1": "portal_registered", "2": "portal_registered", "3": "observed_new", "4": "reappeared",
                   "5": "observed_new:1", "6": "observed_new"}
    assert changes == {"3", "4", "6"}
    # 같은 파일은 다시 적재하지 않는다
    assert catalog.import_snapshot(dsn=fresh, path=s1, taken_at=date(2026, 10, 19)) == {"skipped": True}


def _seed_idea(c, missing_data="[]"):
    c.execute("INSERT INTO core.source VALUES ('s','n','l','',2,true,'O',true,'op',now(),now())")
    c.execute("INSERT INTO core.ingest_run (source_id, status) VALUES ('s','ok')")
    c.execute("INSERT INTO core.contest VALUES ('C-1','s','대회','',2019)")
    c.execute("INSERT INTO core.idea (id, source_id, contest_id, year, title, team_kind, first_ingest_id,"
              " last_ingest_id) VALUES ('ID-2019-aaaaaaaaaa','s','C-1',2019,'제목','empty',1,1)")
    c.execute("INSERT INTO core.idea_card (idea_id, card_kind, title, missing_data, extractor)"
              " VALUES ('ID-2019-aaaaaaaaaa','local_extract','제목',%s,'human')", (missing_data,))


def test_diagnosis_requires_evidence_and_missing_data(fresh):
    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.commit()
        c.execute("INSERT INTO core.diagnosis (idea_id, \"primary\", extractor) VALUES ('ID-2019-aaaaaaaaaa','R','human')")
        with pytest.raises(psycopg.errors.RaiseException, match="requires evidence"):
            c.commit()
    with psycopg.connect(fresh) as c:
        c.execute("INSERT INTO core.evidence (kind, url) VALUES ('manual','https://x.go.kr') ")
        c.execute("INSERT INTO core.x_evidence VALUES ('diagnosis','ID-2019-aaaaaaaaaa',1)")
        c.execute("INSERT INTO core.diagnosis (idea_id, \"primary\", extractor) VALUES ('ID-2019-aaaaaaaaaa','D','human')")
        with pytest.raises(psycopg.errors.RaiseException, match="missing_data"):
            c.commit()
    with psycopg.connect(fresh) as c:  # U는 근거 없이 가능
        c.execute("INSERT INTO core.diagnosis (idea_id, \"primary\", extractor) VALUES ('ID-2019-aaaaaaaaaa','U','human')")
        c.commit()


def test_publish_swap(fresh):
    """publish 템플릿 교체: 두 번 push해도 publish 하나만 남고, 미등록 템플릿·역행 스냅샷은 거부."""
    pub = fresh.rsplit("/", 1)[0] + "/bbtest_pub"
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("DROP DATABASE IF EXISTS bbtest_pub WITH (FORCE)")
        c.execute("CREATE DATABASE bbtest_pub")
        for role in ("bb_portal", "bb_publisher", "bb_inbox_reader"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                c.execute(f"CREATE ROLE {role}")
    with psycopg.connect(pub, autocommit=True) as c:
        c.execute("CREATE EXTENSION pg_trgm")
    db.migrate(pub, "publish")
    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.commit()
    with pytest.raises(publish.PublishError, match="not the registered"):
        publish.push(core_dsn=fresh, publish_dsn=pub)
    publish.register_template(pub)
    r1 = publish.push(core_dsn=fresh, publish_dsn=pub)
    r2 = publish.push(core_dsn=fresh, publish_dsn=pub)
    assert r1["idea"] == r2["idea"] == 1 and r2["snapshot_id"] > r1["snapshot_id"]
    with psycopg.connect(pub) as c:
        schemas = {r[0] for r in c.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'publish%'")}
        assert schemas == {"publish"}
        assert c.execute("SELECT count(*) FROM meta.snapshot_log").fetchone()[0] == 2
        assert c.execute("SELECT has_table_privilege('bb_portal','publish.idea','SELECT')").fetchone()[0]
        # 승인 안 된 카드 내용(problem)은 나가지 않는다
        assert c.execute("SELECT problem FROM publish.idea").fetchone()[0] is None


def test_ingest_retires_vanished_rows_and_cards_follow(fresh, tmp_path):
    """원본 파일이 갱신돼 사라진 행은 retired_at, 다시 나타나면 복귀. 절반 넘게 사라지면 멈춘다."""
    import csv

    from bluebird import cards, ingest

    (tmp_path / "secret").write_bytes(b"s" * 32)
    (tmp_path / "sources.toml").write_text(
        '[[source]]\nid="d"\nadapter="design_idea_csv"\nfile="d.csv"\nname="n"\nlicense="l"\nlayer=2\n'
        'public_ok=true\nexport_grade="O"\npolicy_approved_by="t"\npolicy_approved_at="2026-10-06"\n',
        encoding="utf-8")

    def write(rows):
        with (tmp_path / "d.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["등록번호", "연도", "포상", "수상자", "제목", "내용"])
            w.writerows([[str(i), "2022", "상", "", f"제목{i}", f"제목{i}의 본문. 정류장 데이터가 없어 불편하다."]
                         for i in rows])

    def run(**kw):
        return ingest.ingest(dsn=fresh, config=tmp_path / "sources.toml", seed_dir=tmp_path,
                             secret_path=tmp_path / "secret", **kw)

    def live():
        with psycopg.connect(fresh) as c:
            return c.execute("SELECT count(*) FILTER (WHERE retired_at IS NULL), count(*) FROM core.idea").fetchone()

    write(range(1, 5))
    run()
    cards.build(dsn=fresh)
    write([1, 2, 3, 9])            # 4 사라짐, 9 신규
    assert run()[0]["retired"] == 1
    assert live() == (4, 5)
    write([1, 2, 3, 4, 9])         # 4 복귀
    run()
    assert live() == (5, 5)
    write([1])                     # 4/5 사라짐 → 파일 이상으로 중단
    with pytest.raises(ingest.IngestError, match="would be retired"):
        run()
    with pytest.raises(ingest.IngestError, match="would be retired"):
        run(force=True)            # force는 재적재만, 퇴역 허용 아님
    assert live() == (5, 5)
    rep = cards.build(dsn=fresh)
    assert rep["by_kind"]["local_extract"]["with_missing_data"] == 5  # 키 없음 → full 아님


def _pub_db(name="bbtest_pub2"):
    pub = DSN.rsplit("/", 1)[0] + f"/{name}"
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {name}")
        for role in ("bb_portal", "bb_publisher", "bb_inbox_reader"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                c.execute(f"CREATE ROLE {role}")
    with psycopg.connect(pub, autocommit=True) as c:
        c.execute("CREATE EXTENSION pg_trgm")
    db.migrate(pub, "publish")
    publish.register_template(pub)
    return pub


LAW_XML = ("<?xml version='1.0' encoding='UTF-8'?><법령><기본정보><법령명_한글><![CDATA[드론법]]></법령명_한글>"
           "<공포일자>20251001</공포일자><공포번호>12345</공포번호><시행일자>20260101</시행일자></기본정보></법령>")


def _law_egress(dsn):
    import httpx

    from bluebird.egress import Egress, Policy, db_recorder

    def h(req):
        assert req.url.path == "/DRF/lawService.do" and req.url.params["MST"] == "777"
        return httpx.Response(200, text=LAW_XML)

    with psycopg.connect(dsn) as c:
        pol = Policy.load(c)
    return Egress(policy=pol, recorder=db_recorder(dsn), proxy="", transport=httpx.MockTransport(h))


def test_funnel_end_to_end_human_path(fresh, tmp_path):
    """키 없는 경로: 사람 흔적·진단(근거) → 사람이 넣은 바뀐 것 → 사람 판정 → S → 승인 → push → 6단계."""
    from bluebird import funnel

    s0 = _csv(tmp_path / "s0.csv", [_row("1", "드론 비행 데이터")])
    catalog.import_snapshot(dsn=fresh, path=s0, taken_at=date(2026, 10, 6))
    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.commit()
    iid = "ID-2019-aaaaaaaaaa"

    def stage():
        with psycopg.connect(fresh) as c:
            return c.execute("SELECT s0,s1,s2,s3,s4,s5,s6 FROM core.revival_candidate WHERE idea_id=%s",
                             (iid,)).fetchone()

    assert stage() == (True, False, False, False, False, False, False)
    funnel.trace_pending(dsn=fresh)  # 사람 manual 없으면 pending
    assert stage()[1] is False
    funnel.trace_manual(dsn=fresh, idea_id=iid, result="none", status=None, url=None, note="검색 결과 없음", by="t")
    assert stage()[:2] == (True, True)
    with pytest.raises(ValueError, match="requires at least one"):
        funnel.diagnose_set(dsn=fresh, idea_id=iid, cause="R", rationale="규제", evidence=[], by="t")
    funnel.diagnose_set(dsn=fresh, idea_id=iid, cause="R", rationale="비행 규제",
                        evidence=[("https://www.law.go.kr/x", "비행 승인")], by="t")
    assert stage()[2] is True
    # 종류 불일치(R 아이디어 ↔ 데이터 개방)는 만들 수 없다
    with psycopg.connect(fresh) as c:
        c.execute("INSERT INTO core.condition_change (id, kind, ref_id, occurred_at, url, title)"
                  " VALUES ('dataset:1','dataset_opened','1','2020-01-01','https://www.data.go.kr/data/1','d')")
        c.commit()
        with pytest.raises(psycopg.errors.RaiseException, match="does not fit"):
            c.execute("INSERT INTO core.change_match (change_id, idea_id) VALUES ('dataset:1',%s)", (iid,))
    # 사람이 넣는 바뀐 것은 dataset_opened 불가, 금지 문구 불가
    with pytest.raises(ValueError):
        funnel.change_add(dsn=fresh, kind="dataset_opened", url="https://x", title="t",
                          occurred_at=date(2026, 1, 1), by="t")
    with pytest.raises(ValueError, match="law-mst"):
        funnel.change_add(dsn=fresh, kind="law_effective", url="https://www.law.go.kr/lsInfoP.do?lsiSeq=1",
                          title="드론 배송 허용", occurred_at=date(2026, 1, 1), by="t")
    with pytest.raises(ValueError, match="시행일자"):  # API의 시행일자와 다르면 거부
        funnel.change_add(dsn=fresh, kind="law_effective", url="https://www.law.go.kr/lsInfoP.do?lsiSeq=1",
                          title="드론 배송 허용", occurred_at=date(2026, 1, 2), by="t", egress=_law_egress(fresh),
                          law_mst="777")
    cid = funnel.change_add(dsn=fresh, kind="law_effective", url="https://www.law.go.kr/lsInfoP.do?lsiSeq=1",
                            title="드론 배송 허용", occurred_at=date(2026, 1, 1), by="t", egress=_law_egress(fresh),
                            law_mst="777")
    with psycopg.connect(fresh) as c:
        assert c.execute("SELECT verify_status, verify_detail->>'promulgation_no', egress_call_id IS NOT NULL"
                         " FROM core.condition_change WHERE id=%s", (cid,)).fetchone() == ("api_verified", "12345", True)
    with pytest.raises(wording.WordingError):
        funnel.match_set(dsn=fresh, change_id=cid, idea_id=iid, verdict="yes", what_changed=[],
                         how_now="그때 없던 제도", by="t")
    funnel.match_set(dsn=fresh, change_id=cid, idea_id=iid, verdict="yes", what_changed=["배송 허용"],
                     how_now="이제 배송 사업 신청 가능", by="t")
    assert stage()[3] is True
    # 바뀐 것 날짜가 as_of 스냅샷 다음 스냅샷 이후면 그 시점 기준으로는 통과하지 않는다
    with psycopg.connect(fresh) as c:
        # 스냅샷 0(10-06)의 기준일은 다음 스냅샷(10-07). 그날 이후에 일어난 바뀐 것은 스냅샷 0 기준으로 통과하지 않는다
        c.execute("UPDATE core.condition_change SET occurred_at='2026-10-07' WHERE id=%s", (cid,))
        c.execute("INSERT INTO core.catalog_snapshot VALUES (1,'2026-10-07','f','x',0,1)")
        assert c.execute("SELECT s3 FROM core.funnel_stage(0) WHERE idea_id=%s", (iid,)).fetchone()[0] is False
        assert c.execute("SELECT s3 FROM core.funnel_stage(1) WHERE idea_id=%s", (iid,)).fetchone()[0] is True
        c.rollback()
    with pytest.raises(ValueError, match="evidence URL"):
        funnel.score_set(dsn=fresh, idea_id=iid, scores={"regulation": 5, "tech": 4}, evidence={}, by="t")
    sc = funnel.score_set(dsn=fresh, idea_id=iid, scores={"regulation": 5, "tech": 4},
                          evidence={"regulation": "https://www.law.go.kr/x", "tech": "https://a.kr"}, by="t")
    assert sc.verdict == "now"
    assert stage()[4] is True
    funnel.approve(dsn=fresh, idea_id=iid, by="t")
    assert stage()[5] is True and stage()[6] is False
    with psycopg.connect(fresh) as c:  # 공개는 public_ok 소스만, push 후에만 6단계
        c.execute("UPDATE core.source SET public_ok = true WHERE id='s'")
        c.commit()
    pub = _pub_db()
    funnel.compute_top(dsn=fresh, week=date(2026, 10, 12))
    res = publish.push(core_dsn=fresh, publish_dsn=pub)
    assert (res["diagnosis"], res["change"], res["timeliness"], res["weekly_top"]) == (1, 1, 1, 1)
    assert stage()[6] is True
    with psycopg.connect(pub) as c:
        url = c.execute("SELECT url FROM publish.change").fetchone()[0]
        ev = c.execute("SELECT count(*) FROM publish.evidence").fetchone()[0]
    assert url.startswith("https://www.law.go.kr/") and ev >= 2
    rep = funnel.report(dsn=fresh)
    assert rep["total"]["s6"] == 1

    # 승인 뒤 진단을 고치면 공개가 철회되고, 다시 push해도 나가지 않는다(검토한 내용만 공개)
    funnel.diagnose_set(dsn=fresh, idea_id=iid, cause="R", rationale="비행 규제(수정)",
                        evidence=[("https://www.law.go.kr/x", "비행 승인")], by="t2")
    assert stage()[5:] == (False, False)
    res = publish.push(core_dsn=fresh, publish_dsn=pub)
    assert (res["diagnosis"], res["change"], res["timeliness"], res["weekly_top"]) == (0, 0, 0, 0)
    # 다시 승인하면 공개, 이어서 반려하면 아이디어·바뀐 것·weekly_top 모두 내려간다
    funnel.approve(dsn=fresh, idea_id=iid, by="t")
    funnel.compute_top(dsn=fresh, week=date(2026, 10, 12))
    res = publish.push(core_dsn=fresh, publish_dsn=pub)
    assert (res["diagnosis"], res["change"], res["weekly_top"]) == (1, 1, 1) and stage()[6] is True
    funnel.reject(dsn=fresh, idea_id=iid, by="t", note="근거 부족")
    res = publish.push(core_dsn=fresh, publish_dsn=pub)
    assert (res["diagnosis"], res["change"], res["timeliness"], res["weekly_top"]) == (0, 0, 0, 0)
    assert stage()[5:] == (False, False)
    # 원인을 바꾸면 맞지 않는 매칭은 rejected로 빠진다
    funnel.diagnose_set(dsn=fresh, idea_id=iid, cause="T", rationale="기술", evidence=[("https://a.kr/t", "기술")],
                        by="t")
    with psycopg.connect(fresh) as c:
        assert c.execute("SELECT status FROM core.change_match WHERE idea_id=%s", (iid,)).fetchone()[0] == "rejected"
        assert c.execute("SELECT count(*) FROM core.x_evidence WHERE target_type='diagnosis' AND target_id=%s",
                         (iid,)).fetchone()[0] == 1  # 이전 원인(R)의 근거는 떨어졌다


def test_s6_needs_applied_snapshot_and_future_change_does_not_pass(fresh):
    """push가 DMZ에 반영되지 않으면(applied_at 없음) 6단계가 아니다. 시행일이 미래인 바뀐 것은 3단계를 통과하지 않는다."""
    from bluebird import funnel

    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.execute("INSERT INTO core.catalog_snapshot VALUES (0,'2026-10-06','f','x',0,0)")
        c.commit()
    iid = "ID-2019-aaaaaaaaaa"
    funnel.trace_manual(dsn=fresh, idea_id=iid, result="none", status=None, url=None, note="없음", by="t")
    funnel.diagnose_set(dsn=fresh, idea_id=iid, cause="M", rationale="정책", evidence=[("https://a.kr/m", "정책")],
                        by="t")
    future = date(2099, 1, 1)
    cid = funnel.change_add(dsn=fresh, kind="policy_news", url="https://a.kr/p", title="정책 시행 예정",
                            occurred_at=future, by="t")
    funnel.match_set(dsn=fresh, change_id=cid, idea_id=iid, verdict="human", what_changed=["지원"], how_now="신청 가능",
                     by="t")
    with psycopg.connect(fresh) as c:
        assert c.execute("SELECT verify_status FROM core.condition_change WHERE id=%s", (cid,)).fetchone()[0] == "attested"
        assert c.execute("SELECT s3 FROM core.revival_candidate WHERE idea_id=%s", (iid,)).fetchone()[0] is False
        c.execute("UPDATE core.condition_change SET occurred_at='2026-01-01' WHERE id=%s", (cid,))
        c.commit()
        assert c.execute("SELECT s3 FROM core.revival_candidate WHERE idea_id=%s", (iid,)).fetchone()[0] is True
    funnel.score_set(dsn=fresh, idea_id=iid, scores={"policy": 4, "tech": 4},
                     evidence={"policy": "https://a.kr/p", "tech": "https://a.kr/t"}, by="t")
    with psycopg.connect(fresh) as c:
        c.execute("UPDATE core.source SET public_ok = true WHERE id='s'")
        c.commit()
    funnel.approve(dsn=fresh, idea_id=iid, by="t")
    with psycopg.connect(fresh) as c:  # push가 기록만 하고 반영 전에 실패한 경우
        c.execute("INSERT INTO core.publish_snapshot (template_version, template_sha256, rows) VALUES ('v1','x','{}')")
        c.commit()
        assert c.execute("SELECT s5, s6 FROM core.revival_candidate WHERE idea_id=%s", (iid,)).fetchone() == (True, False)
    publish.push(core_dsn=fresh, publish_dsn=_pub_db())
    with psycopg.connect(fresh) as c:
        assert c.execute("SELECT s6 FROM core.revival_candidate WHERE idea_id=%s", (iid,)).fetchone()[0] is True
        assert c.execute("SELECT revived_ids FROM core.publish_snapshot WHERE applied_at IS NOT NULL"
                         " ORDER BY id DESC LIMIT 1").fetchone()[0] == [iid]


def test_publish_refuses_forbidden_wording_in_own_text(fresh):
    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.execute("UPDATE core.source SET public_ok = true WHERE id='s'")
        c.execute("UPDATE core.idea_card SET problem='그때까지 없던 데이터로 푼다'")
        c.execute("INSERT INTO core.publication (target_type, target_id, scope, approved_by)"
                  " VALUES ('idea','ID-2019-aaaaaaaaaa','card','t')")
        c.commit()
        with pytest.raises(publish.PublishError, match="forbidden wording"):
            publish.collect(c)


def test_match_judge_llm_path(fresh, monkeypatch):
    """키가 있으면 후보 매칭을 LLM이 판정(egress 감사 행), status는 candidate 유지 — 승인은 사람. 키가 없으면 key_required."""
    import json as _json

    import httpx

    from bluebird import funnel
    from bluebird.egress import Egress, Policy, db_recorder

    with psycopg.connect(fresh) as c:
        _seed_idea(c, missing_data='[{"name": "배차 데이터", "excerpt": "배차 데이터가 없다"}]')
        c.execute("INSERT INTO core.diagnosis (idea_id, \"primary\", extractor) VALUES ('ID-2019-aaaaaaaaaa','D','rule')")
        c.execute("INSERT INTO core.evidence (id, kind, url) VALUES (900,'body_excerpt','https://a.kr/i')")
        c.execute("INSERT INTO core.x_evidence VALUES ('diagnosis','ID-2019-aaaaaaaaaa',900)")
        c.execute("INSERT INTO core.condition_change (id, kind, ref_id, occurred_at, url, title)"
                  " VALUES ('dataset:9','dataset_opened','9','2024-01-01','https://www.data.go.kr/data/9','버스 배차 정보')")
        c.execute("INSERT INTO core.change_match (change_id, idea_id, similarity) VALUES ('dataset:9','ID-2019-aaaaaaaaaa',0.5)")
        c.commit()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert funnel.match_judge(dsn=fresh)["key_required"] is True
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    sent = []

    def h(req):
        sent.append(req.content.decode())
        body = {"verdict": "partial", "what_changed": ["배차 정보 개방"], "how_now": "배차 정보로 대기시간을 알린다"}
        return httpx.Response(200, json={"choices": [{"message": {"content": _json.dumps(body, ensure_ascii=False)}}]})

    with psycopg.connect(fresh) as c:
        pol = Policy.load(c)
    eg = Egress(policy=pol, recorder=db_recorder(fresh), proxy="", transport=httpx.MockTransport(h))
    assert funnel.match_judge(dsn=fresh, egress=eg)["partial"] == 1
    with psycopg.connect(fresh) as c:
        row = c.execute("SELECT llm_verdict, status, how_now FROM core.change_match").fetchone()
        assert row == ("partial", "candidate", "배차 정보로 대기시간을 알린다")
        assert c.execute("SELECT count(*) FROM core.egress_call WHERE purpose='llm'").fetchone()[0] == 1
    assert "https://www.data.go.kr" not in sent[0]  # 이벤트 URL은 보내지 않는다


def test_cards_llm_path_fallback_and_full_check(fresh, tmp_path, monkeypatch):
    """P1: 성공 → full + egress_call 연결, 전송 실패 → 규칙(local_extract)으로 남고 배치 계속, 본문 바뀌면 다시 만든다.
    DB도 full ⇒ llm + egress_call_id를 강제한다."""
    import json as _json

    import httpx

    from bluebird import cards
    from bluebird.egress import Egress, db_recorder

    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.execute("UPDATE core.idea SET body='정류장 위치는 있다. 저상버스 배차 데이터가 공개되지 않아 기다린다.'")
        c.execute("INSERT INTO core.idea (id, source_id, contest_id, year, title, body, team_kind, first_ingest_id,"
                  " last_ingest_id) VALUES ('ID-2019-bbbbbbbbbb','s','C-1',2019,'둘째','둘째 본문입니다.','empty',1,1)")
        c.execute("DELETE FROM core.idea_card")
        c.commit()
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("INSERT INTO core.idea_card (idea_id, card_kind, title, extractor)"
                      " VALUES ('ID-2019-aaaaaaaaaa','full','t','rule')")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    answer = {"problem": "대기", "solution": "예측", "missing_data": [
        {"name": "저상버스 배차 데이터", "excerpt": "저상버스 배차 데이터가 공개되지 않아 기다린다."}]}

    def h(req):
        if "둘째" in req.content.decode():
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json={"choices": [{"message": {"content": _json.dumps(answer, ensure_ascii=False)}}]})

    def eg():
        with psycopg.connect(fresh) as c:
            from bluebird.egress import Policy
            pol = Policy.load(c)
        return Egress(policy=pol, recorder=db_recorder(fresh), proxy="", transport=httpx.MockTransport(h))

    cards.build(dsn=fresh, egress=eg())
    with psycopg.connect(fresh) as c:
        got = dict(c.execute("SELECT idea_id, card_kind || ':' || extractor || ':' || (egress_call_id IS NOT NULL)"
                             " FROM core.idea_card"))
        md = c.execute("SELECT missing_data FROM core.idea_card WHERE idea_id='ID-2019-aaaaaaaaaa'").fetchone()[0]
        audited = c.execute("SELECT count(*) FROM core.egress_call WHERE purpose='llm'").fetchone()[0]
    assert got == {"ID-2019-aaaaaaaaaa": "full:llm:true", "ID-2019-bbbbbbbbbb": "local_extract:rule:false"}
    assert md[0]["name"] == "저상버스 배차 데이터" and audited == 2  # 실패한 호출도 감사 행이 남는다
    # 본문이 바뀌면 LLM 카드도 다시 만든다(본문이 비면 title_only)
    with psycopg.connect(fresh) as c:
        c.execute("UPDATE core.idea SET body=NULL WHERE id='ID-2019-aaaaaaaaaa'")
        c.commit()
    cards.build(dsn=fresh, egress=eg())
    with psycopg.connect(fresh) as c:
        assert c.execute("SELECT card_kind, extractor, missing_data FROM core.idea_card"
                         " WHERE idea_id='ID-2019-aaaaaaaaaa'").fetchone() == ("title_only", "rule", [])
