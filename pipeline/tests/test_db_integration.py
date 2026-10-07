"""DB 통합 테스트. BB_TEST_DSN(빈 pgvector DB, superuser)이 있을 때만 실행한다.

    docker run -d --rm --name bb-testdb -e POSTGRES_PASSWORD=t -p 55432:5432 pgvector/pgvector:pg16
    BB_TEST_DSN=postgresql://postgres:t@localhost:55432/postgres uv run pytest tests/test_db_integration.py
"""

import os
from datetime import date

import psycopg
import pytest

from bluebird import db, publish
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
              " VALUES ('ID-2019-aaaaaaaaaa','full','제목',%s,'human')", (missing_data,))


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
