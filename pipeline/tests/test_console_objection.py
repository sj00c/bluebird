"""G004: backend-api(콘솔)·2인 독립 코딩·이의 왕복. BB_TEST_DSN이 있을 때만 실행."""

import hashlib
import json

import psycopg
import pytest

from bluebird import objections, publish
from tests.test_db_integration import DSN, _pub_db, _seed_idea

pytestmark = pytest.mark.skipif(not DSN, reason="BB_TEST_DSN not set")
IID = "ID-2019-aaaaaaaaaa"
TOKENS = {"rev": ("kim", ["reviewer"]), "ca": ("lee", ["coder"]), "cb": ("park", ["coder"]),
          "cc": ("choi", ["coder"]), "exp": ("jung", ["expert"])}


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


@pytest.fixture()
def client(fresh, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from bluebird import api
    users = {hashlib.sha256(t.encode()).hexdigest(): {"user": u, "roles": r} for t, (u, r) in TOKENS.items()}
    (tmp_path / "users.json").write_text(json.dumps(users))
    monkeypatch.setenv("BB_API_USERS", str(tmp_path / "users.json"))
    monkeypatch.setenv("BB_DSN", fresh)
    api._users.cache_clear()
    yield TestClient(api.app)
    api._users.cache_clear()


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def _to_stage4(dsn):
    from datetime import date

    from bluebird import funnel
    with psycopg.connect(dsn) as c:
        _seed_idea(c)
        c.execute("UPDATE core.source SET public_ok = true WHERE id='s'")
        c.execute("INSERT INTO core.catalog_snapshot VALUES (0,'2026-10-06','f','x',0,0)")
        c.commit()
    funnel.trace_manual(dsn=dsn, idea_id=IID, result="none", status=None, url=None, note="없음", by="t")
    funnel.diagnose_set(dsn=dsn, idea_id=IID, cause="M", rationale="정책", evidence=[("https://a.kr/m", "정책")],
                        by="t")
    cid = funnel.change_add(dsn=dsn, kind="policy_news", url="https://a.kr/p", title="지원 사업 시행",
                            occurred_at=date(2026, 1, 1), by="t")
    funnel.match_set(dsn=dsn, change_id=cid, idea_id=IID, verdict="human", what_changed=["지원"],
                     how_now="신청 가능", by="t")
    funnel.score_set(dsn=dsn, idea_id=IID, scores={"policy": 4, "tech": 4},
                     evidence={"policy": "https://a.kr/p", "tech": "https://a.kr/t"}, by="t")


def test_auth_and_roles(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers=H("nope")).status_code == 401
    assert client.get("/api/me", headers=H("rev")).json() == {"user": "kim", "roles": ["reviewer"]}
    assert client.get("/api/coding", headers=H("rev")).status_code == 403
    assert client.post("/api/objections/1/resolve", headers=H("ca"),
                       json={"decision": "rejected", "resolution": "x"}).status_code == 403


def test_console_approve_then_publish(client, fresh):
    _to_stage4(fresh)
    q = client.get("/api/queue?stage=s4", headers=H("rev")).json()
    assert [i["idea_id"] for i in q["items"]] == [IID] and q["counts"]["s4"] == 1
    # 전문가 라운드는 expert 역할만
    assert client.post(f"/api/ideas/{IID}/review", headers=H("rev"),
                       json={"round": "expert", "decision": "approve"}).status_code == 403
    assert client.post(f"/api/ideas/{IID}/review", headers=H("exp"),
                       json={"round": "expert", "decision": "approve", "note": "타당"}).status_code == 200
    # 금지 문구 메모는 거부
    assert client.post(f"/api/ideas/{IID}/review", headers=H("rev"),
                       json={"round": "final", "decision": "approve", "note": "그때 없던 제도"}).status_code == 409
    r = client.post(f"/api/ideas/{IID}/review", headers=H("rev"), json={"round": "final", "decision": "approve"})
    assert r.status_code == 200 and r.json()["stage"]["s5"] is True
    d = client.get(f"/api/ideas/{IID}", headers=H("rev")).json()
    assert d["diagnosis"]["evidence"][0]["url"] == "https://a.kr/m" and d["matches"][0]["eligible"] is True
    publish.push(core_dsn=fresh, publish_dsn=_pub_db())
    assert client.get(f"/api/ideas/{IID}", headers=H("rev")).json()["stage"]["s6"] is True
    # 없는 아이디어는 404
    assert client.post("/api/ideas/ID-2019-bbbbbbbbbb/review", headers=H("rev"),
                       json={"round": "final", "decision": "approve"}).status_code == 404


def test_blind_coding(client, fresh):
    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        c.commit()
    assert client.get("/api/coding", headers=H("ca")).json() == {"sample_id": None, "items": []}
    with psycopg.connect(fresh) as c:
        c.execute("INSERT INTO core.coding_sample (sample_id, idea_id, stratum, seed) VALUES ('k1',%s,'s:-',1)",
                  (IID,))
        c.commit()
    assert client.post(f"/api/coding/{IID}", headers=H("ca"), json={"code": "R"}).status_code == 200
    # 다른 코더는 상대 코드를 보지 못한다
    items = client.get("/api/coding", headers=H("cb")).json()["items"]
    assert items[0]["my_code"] is None and "R" not in json.dumps(items)
    assert client.get("/api/coding", headers=H("ca")).json()["items"][0]["my_code"] == "R"
    assert client.post(f"/api/coding/{IID}", headers=H("cb"), json={"code": "D"}).status_code == 200
    # 자기 코드 수정은 같은 슬롯, 세 번째 코더는 거부
    assert client.post(f"/api/coding/{IID}", headers=H("ca"), json={"code": "M"}).status_code == 200
    assert client.post(f"/api/coding/{IID}", headers=H("cc"), json={"code": "T"}).status_code == 409
    with psycopg.connect(fresh) as c:
        rows = c.execute("SELECT round, reviewer, code FROM core.review WHERE round LIKE 'coder_%' ORDER BY round").fetchall()
        assert rows == [("coder_a", "lee", "M"), ("coder_b", "park", "D")]
        with pytest.raises(psycopg.errors.RaiseException, match="other coder slot"):  # DB도 같은 사람 두 슬롯 거부
            c.execute("UPDATE core.review SET reviewer='lee' WHERE round='coder_b'")
    # 상세 화면도 코더 기록을 보여주지 않는다
    assert client.get(f"/api/ideas/{IID}", headers=H("rev")).json()["reviews"] == []
    # 표본에 없는 아이디어는 404
    assert client.post("/api/coding/ID-2019-bbbbbbbbbb", headers=H("ca"), json={"code": "R"}).status_code == 404


def test_coding_sample_is_stratified_and_reproducible(fresh):
    with psycopg.connect(fresh) as c:
        _seed_idea(c)
        for n in range(1, 30):
            iid = f"ID-2019-{n:010x}"
            c.execute("INSERT INTO core.idea (id, source_id, contest_id, year, title, team_kind, first_ingest_id,"
                      " last_ingest_id) VALUES (%s,'s','C-1',2019,'t','empty',1,1)", (iid,))
            c.execute("INSERT INTO core.idea_card (idea_id, card_kind, title, extractor)"
                      " VALUES (%s,'local_extract','t','rule')", (iid,))
            c.execute("INSERT INTO core.trace_verdict (idea_id, status, profile_version, external_search)"
                      " VALUES (%s,'pending','full_v1','not_done')", (iid,))
        c.commit()
    with pytest.raises(ValueError, match="population"):
        objections.make_sample(dsn=fresh, size=100, seed=7)
    a = objections.make_sample(dsn=fresh, size=10, seed=7, sample_id="a")
    b = objections.make_sample(dsn=fresh, size=10, seed=7, sample_id="b")
    with psycopg.connect(fresh) as c:
        pick = {s: {r[0] for r in c.execute("SELECT idea_id FROM core.coding_sample WHERE sample_id=%s", (s,))}
                for s in ("a", "b")}
    assert a["size"] == b["size"] == 10 and pick["a"] == pick["b"]
    with pytest.raises(ValueError, match="already exists"):
        objections.make_sample(dsn=fresh, size=10, seed=7, sample_id="a")


def _inbox_dsn(pub):
    return pub  # 테스트는 superuser로 같은 DB에 접속(권한 분리는 deploy/test/verify.sh가 확인)


def test_objection_round_trip(client, fresh):
    _to_stage4(fresh)
    assert client.post(f"/api/ideas/{IID}/review", headers=H("rev"),
                       json={"round": "final", "decision": "approve"}).status_code == 200
    pub = _pub_db()
    assert publish.push(core_dsn=fresh, publish_dsn=pub)["diagnosis"] == 1
    with psycopg.connect(pub) as c:  # portal이 넣는 것과 같은 INSERT
        for idea, kind, body in [(IID, "privacy", "팀원 이름이 보입니다\x07"), ("ID-2019-bbbbbbbbbb", "fact", "x"),
                                 (IID, "cause", "원인이 다릅니다")]:
            c.execute("INSERT INTO inbox.objection (idea_id, kind, body) VALUES (%s,%s,%s)", (idea, kind, body))
        c.commit()
    st = objections.pull(dsn=fresh, inbox_dsn=_inbox_dsn(pub), limit=2)  # 상한: 2건만
    assert (st["read"], st["stored"], st["unknown_idea"], st["deleted"]) == (2, 1, 1, 2)
    st = objections.pull(dsn=fresh, inbox_dsn=_inbox_dsn(pub))
    assert (st["read"], st["stored"], st["deleted"]) == (1, 1, 1)
    with psycopg.connect(pub) as c:
        assert c.execute("SELECT count(*) FROM inbox.objection").fetchone()[0] == 0
    with psycopg.connect(fresh) as c:
        assert c.execute("SELECT stats->>'stored' FROM core.pipeline_run WHERE stage='objections-pull'"
                         " ORDER BY id").fetchall() == [("1",), ("1",)]
    items = client.get("/api/objections", headers=H("rev")).json()["items"]
    assert [(o["kind"], o["body"]) for o in items] == [("privacy", "팀원 이름이 보입니다"), ("cause", "원인이 다릅니다")]
    privacy, cause = items[0]["id"], items[1]["id"]
    assert client.post(f"/api/objections/{cause}/resolve", headers=H("rev"),
                       json={"decision": "rejected", "resolution": "근거 확인 결과 유지", "withhold": True}
                       ).status_code == 409  # withhold는 수용일 때만
    assert client.post(f"/api/objections/{cause}/resolve", headers=H("rev"),
                       json={"decision": "rejected", "resolution": "근거 확인 결과 유지"}).status_code == 200
    assert publish.push(core_dsn=fresh, publish_dsn=pub)["diagnosis"] == 1  # 기각은 공개 유지
    assert client.post(f"/api/objections/{privacy}/resolve", headers=H("rev"),
                       json={"decision": "accepted", "resolution": "이름 노출 확인, 카드 내림", "withhold": True}
                       ).status_code == 200
    assert client.post(f"/api/objections/{privacy}/resolve", headers=H("rev"),
                       json={"decision": "accepted", "resolution": "again"}).status_code == 409
    res = publish.push(core_dsn=fresh, publish_dsn=pub)
    assert (res["diagnosis"], res["change"], res["timeliness"]) == (0, 0, 0)
    with psycopg.connect(pub) as c:
        assert c.execute("SELECT count(*) FROM publish.idea WHERE id=%s", (IID,)).fetchone()[0] == 0
    d = client.get(f"/api/ideas/{IID}", headers=H("rev")).json()
    assert d["stage"]["s5"] is False and d["idea"]["withheld_at"] is not None
    assert [o["status"] for o in d["objections"]] == ["accepted", "rejected"]


def test_pull_validation():
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    assert objections.validate((1, IID, "fact", " a\x00b ", now))[0]["body"] == "ab"
    assert objections.validate((1, "ID-19-x", "fact", "a", now))[1] == "bad idea_id"
    assert objections.validate((1, IID, "spam", "a", now))[1] == "bad kind"
    assert objections.validate((1, IID, "fact", "\x01", now))[1] == "bad body length"
    assert objections.validate((1, IID, "fact", "a" * 2001, now))[1] == "bad body length"
