"""Console consumer flows against a migrated core DB, including real bb_api grants."""

from datetime import date

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from bluebird import funnel
from tests import test_console as console_fixtures
from tests.test_console import IID, H
from tests.test_db_integration import DSN, _seed_idea

pytestmark = pytest.mark.skipif(not DSN, reason="BB_TEST_DSN not set")
client = console_fixtures.client
fresh = console_fixtures.fresh


@pytest.fixture()
def api_role(client, fresh, monkeypatch):
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("ALTER ROLE bb_api LOGIN PASSWORD 'apitest'")
    dsn = make_conninfo(fresh, user="bb_api", password="apitest")
    monkeypatch.setenv("BB_DSN", dsn)
    return client, dsn


def seed(dsn):
    with psycopg.connect(dsn) as conn:
        _seed_idea(conn)
        conn.execute("UPDATE core.source SET public_ok=true WHERE id='s'")
        conn.execute("INSERT INTO core.catalog_snapshot VALUES (0,'2026-10-06','f','x',0,0)")
    return funnel.change_add(dsn=dsn, kind="policy_news", url="https://example.org/policy",
                             title="지원 사업 시행", occurred_at=date(2026, 1, 1), by="seed")


def payloads(change):
    return {
        "trace": {"result": "none", "note": "외부 자료 검토 완료", "url": "https://example.org/search"},
        "diagnosis": {"cause": "M", "rationale": "정책 지원 필요",
                      "evidence": [{"url": "https://example.org/barrier", "excerpt": "지원 조건"}]},
        "match": {"change_id": change, "verdict": "human", "what_changed": ["지원 사업 시행"],
                  "how_now": "지원 신청 가능"},
        "score": {"scores": {"tech": 4, "data": None, "regulation": None, "policy": 5},
                  "evidence": {"tech": "https://example.org/tech", "policy": "https://example.org/policy"}},
    }


def post(cl, action, body, token="rev", idea=IID):
    return cl.post(f"/api/ideas/{idea}/{action}", headers=H(token), json=body)


def test_authoring_chain_as_real_api_role(api_role, fresh):
    cl, dsn = api_role
    bodies = payloads(seed(fresh))
    assert cl.get("/healthz").json() == {"ok": True}
    for action, body in bodies.items():
        response = post(cl, action, body)
        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True}
    detail = cl.get(f"/api/ideas/{IID}", headers=H("rev")).json()
    assert detail["stage"]["s4"] and not detail["stage"]["s5"]
    assert detail["diagnosis"]["decided_by"] == "kim"
    assert detail["timeliness"]["scored_by"] == "kim"
    assert detail["timeliness"]["evidence"] == bodies["score"]["evidence"]
    manual = next(c for c in detail["trace"]["checks"] if c["item"] == "manual")
    assert manual["detail"]["by"] == "kim"
    assert manual["detail"]["url"] == bodies["trace"]["url"]
    assert post(cl, "review", {"round": "final", "decision": "approve"}).json()["stage"]["s5"]
    # Re-saving linked evidence revokes approval, even at the same score.
    assert post(cl, "score", bodies["score"]).status_code == 200
    assert not cl.get(f"/api/ideas/{IID}", headers=H("rev")).json()["stage"]["s5"]
    assert post(cl, "review", {"round": "final", "decision": "approve"}).status_code == 200
    assert post(cl, "diagnosis", {"cause": "T", "rationale": "기술 조건 필요",
                                 "evidence": [{"url": "https://example.org/technical"}]}).status_code == 200
    detail = cl.get(f"/api/ideas/{IID}", headers=H("rev")).json()
    assert not detail["stage"]["s5"] and detail["matches"][0]["status"] == "rejected"
    assert detail["diagnosis"]["evidence"] == [{"url": "https://example.org/technical", "excerpt": None}]
    # Provider credentials/audit, DDL and approval-history deletion remain inaccessible.
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT current_user").fetchone()[0] == "bb_api"
        assert conn.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user").fetchone()[0] is False
        for sql in ("CREATE TABLE core.api_owned (id int)", "SELECT * FROM core.egress_call",
                    "SELECT * FROM core.export_policy", "UPDATE core.source SET name='forbidden'",
                    "DELETE FROM core.publication", "INSERT INTO core.pipeline_run(stage,status) VALUES ('x','ok')"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql)
            conn.rollback()


def test_queue_overview_and_changes(api_role, fresh):
    cl, _ = api_role
    change = seed(fresh)
    first = cl.get("/api/queue?stage=s0&limit=1", headers=H("rev")).json()
    assert first["total"] == 1 and first["limit"] == 1 and first["offset"] == 0
    assert first["items"][0]["idea_id"] == IID
    page = cl.get("/api/queue?stage=s0&limit=1&offset=1", headers=H("rev")).json()
    assert page["items"] == [] and page["total"] == 1
    found = cl.get("/api/queue", params={"stage": "s0", "q": IID}, headers=H("rev")).json()
    assert found["total"] == 1
    absent = cl.get("/api/queue", params={"stage": "s0", "q": "' OR true --"}, headers=H("rev")).json()
    assert absent["total"] == 0 and absent["counts"]["s0"] == 1
    for stage in range(1, 6):
        response = cl.get(f"/api/queue?stage=s{stage}", headers=H("rev"))
        assert response.status_code == 200 and response.json()["total"] == 0
    overview = cl.get("/api/overview", headers=H("exp")).json()
    assert overview["counts"]["s0"] == 1
    assert overview["sources"][0]["ideas"] == 1
    assert overview["sources"][0]["check_status"] is None
    assert overview["runs"] == []
    assert overview["checks"] == []
    with psycopg.connect(fresh) as conn:
        conn.execute(
            """INSERT INTO core.source_check(source_id,status,checked_at,note,sample) VALUES
               ('external_news','ok','2026-01-01','private provider detail','{"secret":"private"}'),
               ('external_news','key_required','2026-01-02','private provider detail','{"secret":"private"}'),
               ('external_patent','blocked','2026-01-02','private provider detail','{"secret":"private"}')""")
    checked = cl.get("/api/overview", headers=H("exp"))
    assert [(c["source_id"], c["status"]) for c in checked.json()["checks"]] == [
        ("external_news", "key_required"), ("external_patent", "blocked")]
    assert all(set(c) == {"source_id", "status", "checked_at"} for c in checked.json()["checks"])
    assert "private provider detail" not in checked.text and "secret" not in checked.text
    changes = cl.get("/api/changes", params={"q": "지원"}, headers=H("rev")).json()["items"]
    assert [c["id"] for c in changes] == [change]
    for path in ("/api/overview", "/api/changes", "/api/queue"):
        assert cl.get(path, headers=H("ca")).status_code == 403


def test_raw_queue_exposes_ingested_originals_without_cards(api_role, fresh, tmp_path):
    from bluebird import ingest

    cl, _ = api_role
    secret = tmp_path / "secret"
    secret.write_bytes(b"s" * 32)
    config = tmp_path / "sources.toml"
    config.write_text(
        '[[source]]\nid="official"\nadapter="mapped_contest_csv"\nfile="official.csv"\n'
        'name="공식 제안"\nlicense="l"\nlayer=2\npublic_ok=false\nexport_grade="pending"\n'
        'record_kind="contest_award"\n'
        'topic="t"\nshare=false\n'
        '[source.columns]\ntitle="제안명"\nbody=["설명"]\n', encoding="utf-8")
    source = tmp_path / "official.csv"
    source.write_text(
        "제안명,설명\n빗물 회수,지붕의 빗물을 저장하는 장치\n"
        "그늘 쉼터,정류장에 그늘을 제공하는 시설\n"
        "공개 중단,이의 처리로 숨겨진 원본\n퇴역 원본,원천에서 사라진 기록\n", encoding="utf-8")
    ingest.ingest(dsn=fresh, config=config, seed_dir=tmp_path, secret_path=secret)
    with psycopg.connect(fresh) as conn:
        assert conn.execute("SELECT count(*) FROM core.idea_card").fetchone()[0] == 0
        conn.execute("UPDATE core.idea SET withheld_at=now() WHERE title='공개 중단'")
        conn.execute("UPDATE core.idea SET retired_at=now() WHERE title='퇴역 원본'")
        originals = conn.execute(
            """SELECT id, title, year, source_id FROM core.idea
                WHERE retired_at IS NULL AND withheld_at IS NULL ORDER BY id""").fetchall()

    response = cl.get("/api/queue?stage=raw&limit=1", headers=H("rev"))
    assert response.status_code == 200, response.text
    first = response.json()
    assert (first["total"], first["limit"], first["offset"]) == (2, 1, 0)
    assert first["counts"] == {"raw": 2, **{f"s{n}": 0 for n in range(6)}}
    expected = [
        dict(zip(("idea_id", "title", "year", "source_id"), row),
             cause=None, s=None, verdict=None, stage="raw")
        for row in originals
    ]
    assert first["items"] == expected[:1]
    page = cl.get("/api/queue?stage=raw&limit=1&offset=1", headers=H("rev")).json()
    assert page["items"] == expected[1:] and page["total"] == 2 and page["offset"] == 1
    end = cl.get("/api/queue?stage=raw&limit=1&offset=2", headers=H("rev")).json()
    assert end["items"] == [] and end["total"] == 2
    assert cl.get("/api/queue", headers=H("rev")).json()["items"] == expected
    for term in (originals[0][0], originals[0][1]):
        found = cl.get("/api/queue", params={"stage": "raw", "q": term}, headers=H("rev")).json()
        assert found["items"] == expected[:1] and found["total"] == 1 and found["counts"]["raw"] == 2
    for term in ("공개 중단", "퇴역 원본", "' OR true --"):
        absent = cl.get("/api/queue", params={"stage": "raw", "q": term}, headers=H("rev")).json()
        assert absent["items"] == [] and absent["total"] == 0 and absent["counts"]["raw"] == 2
    for stage in range(6):
        analytic = cl.get(f"/api/queue?stage=s{stage}", headers=H("rev")).json()
        assert analytic["items"] == [] and analytic["total"] == 0 and analytic["counts"] == first["counts"]
    assert cl.get("/api/overview", headers=H("exp")).json()["counts"] == first["counts"]
    assert cl.get(f"/api/ideas/{originals[0][0]}", headers=H("rev")).status_code == 200
    assert cl.get("/api/queue?stage=raw").status_code == 401
    assert cl.get("/api/queue?stage=raw", headers=H("ca")).status_code == 403
    for params in ({"stage": "invalid"}, {"stage": "s6"}, {"stage": "raw", "limit": 0},
                   {"stage": "raw", "limit": 501}, {"stage": "raw", "offset": -1},
                   {"stage": "raw", "q": "x" * 201}):
        assert cl.get("/api/queue", params=params, headers=H("rev")).status_code == 422


def test_roles_authorship_validation_and_domain_errors(client, fresh):
    bodies = payloads(seed(fresh))
    for action, body in bodies.items():
        for token in ("ca", "exp", "aud"):
            assert post(client, action, body, token).status_code == 403
        assert post(client, action, {**body, "by": "forged"}).status_code == 422
        assert post(client, action, body, idea="missing").status_code == 404
    for value in (-1, 6, 1.5, True, "4"):
        assert post(client, "score", {"scores": {"tech": value}, "evidence": {}}).status_code == 422
    assert post(client, "score", {"scores": {"unknown": 4}, "evidence": {}}).status_code == 422
    for url in ("javascript:alert(1)", "https://", "https://a.kr/a\x00", "https://user:secret@a.kr"):
        assert post(client, "trace", {"result": "found", "note": "근거", "url": url}).status_code == 422
    for note in (" ", "a\x00", "x" * 4001):
        assert post(client, "trace", {"result": "none", "note": note}).status_code == 422
    assert post(client, "trace", {"result": "found", "note": "근거"}).status_code == 409
    assert post(client, "diagnosis", {"cause": "M", "rationale": "근거 없음", "evidence": []}).status_code == 409
    assert post(client, "diagnosis", bodies["diagnosis"]).status_code == 200
    assert post(client, "match", {**bodies["match"], "change_id": "missing"}).status_code == 404
    assert post(client, "score", {"scores": {"tech": 4}, "evidence": {}}).status_code == 409
    # A real DB trigger rejects an incompatible change as an actionable conflict, not a 500.
    assert post(client, "diagnosis", {"cause": "T", "rationale": "기술 조건",
                                      "evidence": [{"url": "https://example.org/t"}]}).status_code == 200
    assert post(client, "match", bodies["match"]).status_code == 409


def test_health_reports_database_unavailable(client, monkeypatch):
    monkeypatch.setenv("BB_DSN", "postgresql://unused:unused@127.0.0.1:1/unavailable?connect_timeout=1")
    response = client.get("/healthz")
    assert response.status_code == 503 and response.json() == {"detail": "core database unavailable"}


def test_trace_edits_cannot_restore_old_approval(api_role, fresh):
    cl, _ = api_role
    bodies = payloads(seed(fresh))
    for action, body in bodies.items():
        response = post(cl, action, body)
        assert response.status_code == 200, response.text
    approval = {"round": "final", "decision": "approve"}
    assert post(cl, "review", approval).json()["stage"]["s5"]
    # A refresh of identical human findings/links only advances timestamps.
    assert post(cl, "trace", bodies["trace"]).status_code == 200
    assert cl.get(f"/api/ideas/{IID}", headers=H("rev")).json()["stage"]["s5"]
    found = {**bodies["trace"], "result": "found", "status": "realized"}
    assert post(cl, "trace", found).status_code == 200
    assert not cl.get(f"/api/ideas/{IID}", headers=H("rev")).json()["stage"]["s5"]
    assert post(cl, "trace", bodies["trace"]).status_code == 200
    restored = cl.get(f"/api/ideas/{IID}", headers=H("rev")).json()
    assert restored["stage"]["s4"] and not restored["stage"]["s5"]
    assert post(cl, "review", approval).json()["stage"]["s5"]
    # URL is stored as linked evidence, not in trace_check.detail.
    assert post(cl, "trace", {**bodies["trace"], "url": "https://example.org/new-search"}).status_code == 200
    assert not cl.get(f"/api/ideas/{IID}", headers=H("rev")).json()["stage"]["s5"]
    assert post(cl, "review", approval).json()["stage"]["s5"]
    assert post(cl, "trace", {**bodies["trace"], "note": "검색 범위를 추가로 검토"}).status_code == 200
    assert not cl.get(f"/api/ideas/{IID}", headers=H("rev")).json()["stage"]["s5"]


@pytest.mark.parametrize(("round_", "token", "reviewer"), [
    ("expert", "exp", "jung"), ("audit", "aud", "han"),
])
@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_nonfinal_review_preserves_attribution_and_privileges(api_role, fresh, round_, token, reviewer, decision):
    cl, dsn = api_role
    seed(fresh)
    body = {"round": round_, "decision": decision, "note": "  검토 근거  "}
    assert post(cl, "review", body, token="rev").status_code == 403
    response = post(cl, "review", body, token=token)
    assert response.status_code == 200
    assert response.json()["ok"] is True and response.json()["stage"]["s5"] is False
    with psycopg.connect(dsn) as conn:
        assert conn.execute(
            "SELECT reviewer, round, decision, note FROM core.review WHERE target_id=%s", (IID,)
        ).fetchall() == [(reviewer, round_, decision, "검토 근거")]
        assert conn.execute("SELECT count(*) FROM core.publication").fetchone()[0] == 0


def test_detail_query_missing_idea(fresh):
    from bluebird.http import queries

    seed(fresh)
    assert queries.idea_detail(dsn=fresh, idea_id="missing") is None
    assert queries.idea_detail(dsn=fresh, idea_id=IID)["idea"]["id"] == IID
