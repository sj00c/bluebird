"""G004: backend-api(콘솔)·2인 독립 코딩. BB_TEST_DSN이 있을 때만 실행."""

import hashlib
import json

import psycopg
import pytest

from bluebird import coding
from tests.test_db_integration import DSN, _seed_idea

pytestmark = pytest.mark.skipif(not DSN, reason="BB_TEST_DSN not set")
IID = "ID-2019-aaaaaaaaaa"
TOKENS = {"rev": ("kim", ["reviewer"]), "ca": ("lee", ["coder"]), "cb": ("park", ["coder"]),
          "cc": ("choi", ["coder"]), "exp": ("jung", ["expert"]), "aud": ("han", ["auditor"])}


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
    from bluebird.http.auth import load_users
    users = {hashlib.sha256(t.encode()).hexdigest(): {"user": u, "roles": r} for t, (u, r) in TOKENS.items()}
    (tmp_path / "users.json").write_text(json.dumps(users))
    monkeypatch.setenv("BB_API_USERS", str(tmp_path / "users.json"))
    monkeypatch.setenv("BB_DSN", fresh)
    load_users.cache_clear()
    yield TestClient(api.app)
    load_users.cache_clear()


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


def test_console_approve(client, fresh):
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
    # 타 코더 코드 비공개
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
    # 상세 화면도 코더 기록 비공개
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
        coding.make_sample(dsn=fresh, size=100, seed=7)
    a = coding.make_sample(dsn=fresh, size=10, seed=7, sample_id="a")
    b = coding.make_sample(dsn=fresh, size=10, seed=7, sample_id="b")
    with psycopg.connect(fresh) as c:
        pick = {s: {r[0] for r in c.execute("SELECT idea_id FROM core.coding_sample WHERE sample_id=%s", (s,))}
                for s in ("a", "b")}
    assert a["size"] == b["size"] == 10 and pick["a"] == pick["b"]
    with pytest.raises(ValueError, match="already exists"):
        coding.make_sample(dsn=fresh, size=10, seed=7, sample_id="a")


def test_coder_only_cannot_see_predictions(client, fresh):
    _to_stage4(fresh)
    for path in ("/api/queue?stage=s4", f"/api/ideas/{IID}"):
        assert client.get(path, headers=H("ca")).status_code == 403, path
    assert client.post(f"/api/ideas/{IID}/review", headers=H("ca"),
                       json={"round": "final", "decision": "approve"}).status_code == 403
    # 제어문자(NUL 등)가 든 메모는 422(500 아님)
    assert client.post(f"/api/ideas/{IID}/review", headers=H("rev"),
                       json={"round": "final", "decision": "approve", "note": "a\x00"}).status_code == 422
    # 없는 아이디어 반려는 기록을 남기지 않고 404
    assert client.post("/api/ideas/ID-2019-bbbbbbbbbb/review", headers=H("rev"),
                       json={"round": "final", "decision": "reject", "note": "x"}).status_code == 404
    with psycopg.connect(fresh) as c:
        assert c.execute("SELECT count(*) FROM core.review WHERE target_id='ID-2019-bbbbbbbbbb'").fetchone()[0] == 0


def test_api_works_as_least_privilege_role(fresh, tmp_path, monkeypatch):
    """backend-api(bb_api 역할): 승인·반려·코딩 가능, DDL·원본 수정 불가."""
    from fastapi.testclient import TestClient

    from bluebird import api
    from bluebird.http.auth import load_users
    _to_stage4(fresh)
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("ALTER ROLE bb_api LOGIN PASSWORD 'apitest'")
    api_dsn = psycopg.conninfo.make_conninfo(fresh, user="bb_api", password="apitest")
    users = {hashlib.sha256(t.encode()).hexdigest(): {"user": u, "roles": r} for t, (u, r) in TOKENS.items()}
    (tmp_path / "u.json").write_text(json.dumps(users))
    monkeypatch.setenv("BB_API_USERS", str(tmp_path / "u.json"))
    monkeypatch.setenv("BB_DSN", api_dsn)
    load_users.cache_clear()
    cl = TestClient(api.app)
    assert cl.post(f"/api/ideas/{IID}/review", headers=H("rev"), json={"round": "final", "decision": "approve"}
                   ).status_code == 200
    assert cl.post(f"/api/ideas/{IID}/review", headers=H("rev"),
                   json={"round": "final", "decision": "reject", "note": "재검토"}).status_code == 200
    with psycopg.connect(fresh) as c:
        c.execute("INSERT INTO core.coding_sample VALUES ('k',%s,'s',1)", (IID,))
        c.commit()
    assert cl.post(f"/api/coding/{IID}", headers=H("ca"), json={"code": "R"}).status_code == 200
    load_users.cache_clear()
    with psycopg.connect(api_dsn) as c:
        for sql in ("CREATE TABLE core.x (a int)", "UPDATE core.idea SET title='x'", "DELETE FROM core.review",
                    "SELECT 1 FROM core.egress_call"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
            c.rollback()
