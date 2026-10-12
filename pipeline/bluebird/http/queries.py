"""Read-only console projections; no HTTP, request models, or role resolution.

Callers authorize access before invoking these queries. Idea detail never includes
coder rounds; blind coding only returns the requesting person's own code. The
objection projection is opt-in because its text can contain personal information.
"""

from __future__ import annotations

import psycopg

from .. import db, score

STAGES = ("s0", "s1", "s2", "s3", "s4", "s5", "s6")


def _rows(cur: psycopg.Cursor) -> list[dict]:
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _snapshot_id(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT coalesce(max(id), -1) FROM core.catalog_snapshot").fetchone()[0]


def _counts(conn: psycopg.Connection, snapshot_id: int) -> dict:
    stages = conn.execute(
        "SELECT " + ", ".join(f"count(*) FILTER (WHERE {s})" for s in STAGES)
        + " FROM core.funnel_stage(%s)", (snapshot_id,)).fetchone()
    raw = conn.execute(
        "SELECT count(*) FROM core.idea WHERE retired_at IS NULL AND withheld_at IS NULL").fetchone()[0]
    return {"raw": raw, **dict(zip(STAGES, stages))}


def check_database(*, dsn: str) -> None:
    with db.connect(dsn) as conn:
        conn.execute("SELECT 1 FROM core.source LIMIT 1").fetchone()


def overview(*, dsn: str) -> dict:
    with db.connect(dsn) as conn:
        counts = _counts(conn, _snapshot_id(conn))
        sources = _rows(conn.execute(
            """SELECT s.id, s.name, s.public_ok, s.export_grade,
                      (SELECT count(*) FROM core.idea i WHERE i.source_id=s.id AND i.retired_at IS NULL) AS ideas,
                      c.status AS check_status, c.checked_at
                 FROM core.source s LEFT JOIN LATERAL (
                     SELECT status, checked_at FROM core.source_check WHERE source_id=s.id
                      ORDER BY checked_at DESC, id DESC LIMIT 1) c ON true ORDER BY s.id"""))
        checks = _rows(conn.execute(
            """SELECT DISTINCT ON (source_id) source_id, status, checked_at FROM core.source_check
                ORDER BY source_id, checked_at DESC, id DESC"""))
        latest = _rows(conn.execute(
            "SELECT id, created_at, applied_at FROM core.publish_snapshot ORDER BY id DESC LIMIT 1"))
        runs = _rows(conn.execute(
            "SELECT stage, status, started_at, finished_at FROM core.pipeline_run ORDER BY id DESC LIMIT 20"))
    return {"counts": counts, "sources": sources,
            "latest_publish": latest[0] if latest else None, "runs": runs, "checks": checks}


def changes(*, dsn: str, q: str, limit: int) -> dict:
    with db.connect(dsn) as conn:
        items = _rows(conn.execute(
            """SELECT id, kind, title, url, occurred_at, verify_status FROM core.condition_change
                WHERE title ILIKE %s OR id ILIKE %s ORDER BY occurred_at DESC, id LIMIT %s""",
            (f"%{q}%", f"%{q}%", limit)))
    return {"items": items}


def queue(*, dsn: str, stage: str, q: str, limit: int, offset: int) -> dict:
    search = f"%{q}%"
    with db.connect(dsn) as conn:
        snap = _snapshot_id(conn)
        counts = _counts(conn, snap)
        if stage == "raw":
            where = "i.retired_at IS NULL AND i.withheld_at IS NULL AND (i.title ILIKE %s OR i.id ILIKE %s)"
            total = conn.execute(
                f"SELECT count(*) FROM core.idea i WHERE {where}", (search, search)).fetchone()[0]
            items = _rows(conn.execute(
                f"""SELECT i.id AS idea_id, i.title, i.year, i.source_id, d."primary" AS cause, t.s, t.verdict
                      FROM core.idea i LEFT JOIN core.diagnosis d ON d.idea_id=i.id
                      LEFT JOIN LATERAL (SELECT s, verdict FROM core.timeliness x WHERE x.idea_id=i.id
                                          ORDER BY as_of DESC LIMIT 1) t ON true
                     WHERE {where}
                     ORDER BY i.id LIMIT %s OFFSET %s""",
                (search, search, limit, offset)))
        else:
            nxt = STAGES[STAGES.index(stage) + 1] if stage != "s6" else None
            where = f"f.{stage} " + (f"AND NOT f.{nxt} " if nxt else "")
            where += "AND (i.title ILIKE %s OR i.id ILIKE %s)"
            total = conn.execute(
                f"""SELECT count(*) FROM core.funnel_stage(%s) f JOIN core.idea i ON i.id=f.idea_id
                     WHERE {where}""", (snap, search, search)).fetchone()[0]
            items = _rows(conn.execute(
                f"""SELECT f.idea_id, i.title, i.year, f.source_id, f.cause, t.s, t.verdict
                      FROM core.funnel_stage(%s) f JOIN core.idea i ON i.id = f.idea_id
                      LEFT JOIN LATERAL (SELECT s, verdict FROM core.timeliness x WHERE x.idea_id = f.idea_id
                                          ORDER BY as_of DESC LIMIT 1) t ON true
                     WHERE {where}
                     ORDER BY t.s DESC NULLS LAST, f.idea_id LIMIT %s OFFSET %s""",
                (snap, search, search, limit, offset)))
    for item in items:
        item["stage"] = stage
    return {"items": items, "counts": counts, "total": total, "limit": limit, "offset": offset}


def idea_detail(*, dsn: str, idea_id: str, include_objections: bool = False) -> dict | None:
    with db.connect(dsn) as conn:
        snap = _snapshot_id(conn)
        idea = _rows(conn.execute(
            """SELECT i.id, i.title, i.body, i.year, i.award, c.name AS contest, i.source_id, s.public_ok,
                      i.source_url, i.withheld_at
                 FROM core.idea i JOIN core.source s ON s.id = i.source_id JOIN core.contest c ON c.id = i.contest_id
                WHERE i.id = %s AND i.retired_at IS NULL""", (idea_id,)))
        if not idea:
            return None
        card = _rows(conn.execute(
            "SELECT card_kind, problem, solution, missing_data, extractor FROM core.idea_card WHERE idea_id=%s",
            (idea_id,)))
        trace = _rows(conn.execute(
            "SELECT status, profile_version, external_search FROM core.trace_verdict WHERE idea_id=%s", (idea_id,)))
        checks = _rows(conn.execute(
            "SELECT item, result, detail FROM core.trace_check WHERE idea_id=%s ORDER BY item", (idea_id,)))
        trace_urls = dict(conn.execute(
            """SELECT DISTINCT ON (x.target_id) x.target_id, e.url
                 FROM core.x_evidence x JOIN core.evidence e ON e.id=x.evidence_id
                WHERE x.target_type='trace' AND x.target_id=%s ORDER BY x.target_id, e.id DESC""",
            (f"{idea_id}:manual",)).fetchall())
        for check in checks:
            if check["item"] == "manual":
                check["detail"]["url"] = trace_urls.get(f"{idea_id}:manual")
        diag = _rows(conn.execute(
            """SELECT "primary" AS cause, secondary, rationale, extractor, decided_by FROM core.diagnosis
                WHERE idea_id=%s""", (idea_id,)))
        diag_ev = _rows(conn.execute(
            """SELECT e.url, e.excerpt FROM core.x_evidence x JOIN core.evidence e ON e.id = x.evidence_id
                WHERE x.target_type='diagnosis' AND x.target_id=%s ORDER BY e.id""", (idea_id,)))
        matches = _rows(conn.execute(
            """SELECT m.id, m.change_id, c.kind, c.title, c.url, c.occurred_at, c.verify_status, m.llm_verdict,
                      m.status, m.what_changed, m.how_now, core.match_eligible(m.id, %s) AS eligible
                 FROM core.change_match m JOIN core.condition_change c ON c.id = m.change_id
                WHERE m.idea_id=%s ORDER BY m.id""", (snap, idea_id)))
        timeliness = _rows(conn.execute(
            """SELECT as_of, tech, data, regulation, policy, n_scored, s, verdict, resolve_condition, scored_by
                 FROM core.timeliness WHERE idea_id=%s ORDER BY as_of DESC LIMIT 1""", (idea_id,)))
        if timeliness:
            links = conn.execute(
                """SELECT e.excerpt, e.url FROM core.x_evidence x JOIN core.evidence e ON e.id=x.evidence_id
                    WHERE x.target_type='timeliness' AND x.target_id=%s ORDER BY e.id""",
                (f"{idea_id}@{timeliness[0]['as_of'].isoformat()}",)).fetchall()
            axes = {f"{score.EVIDENCE_EXCERPT}{label}": axis for axis, label in score.AXIS_KO.items()}
            timeliness[0]["evidence"] = {axes[excerpt]: url for excerpt, url in links if excerpt in axes}
        stage = _rows(conn.execute(
            "SELECT " + ", ".join(STAGES) + " FROM core.funnel_stage(%s) WHERE idea_id=%s", (snap, idea_id)))
        reviews = _rows(conn.execute(  # Blind coding: never expose either coder round.
            """SELECT round, reviewer, decision, code, note, created_at FROM core.review
                WHERE target_type='idea' AND target_id=%s AND round NOT IN ('coder_a','coder_b')
                ORDER BY created_at""", (idea_id,)))
        objection_items = _rows(conn.execute(
            """SELECT id, kind, body, status, resolution, submitted_at, resolved_at, resolved_by FROM core.objection
                WHERE idea_id=%s ORDER BY id""", (idea_id,))) if include_objections else []
    if diag:
        diag[0]["evidence"] = diag_ev
    if trace:
        trace[0]["checks"] = checks
    return {"idea": idea[0], "card": card[0] if card else None, "trace": trace[0] if trace else None,
            "diagnosis": diag[0] if diag else None, "matches": matches,
            "timeliness": timeliness[0] if timeliness else None,
            "stage": stage[0] if stage else dict.fromkeys(STAGES, False), "reviews": reviews,
            "objections": objection_items}


def coding(*, dsn: str, reviewer: str) -> dict:
    with db.connect(dsn) as conn:
        sid = conn.execute("SELECT sample_id FROM core.coding_sample ORDER BY created_at DESC LIMIT 1").fetchone()
        if sid is None:
            return {"sample_id": None, "items": []}
        items = _rows(conn.execute(
            """SELECT cs.idea_id, i.title, i.body, k.problem AS card_problem, k.missing_data,
                      (SELECT r.code FROM core.review r WHERE r.target_type='idea' AND r.target_id=cs.idea_id
                          AND r.round IN ('coder_a','coder_b') AND r.reviewer=%s) AS my_code
                 FROM core.coding_sample cs JOIN core.idea i ON i.id = cs.idea_id
                 LEFT JOIN core.idea_card k ON k.idea_id = cs.idea_id
                WHERE cs.sample_id=%s ORDER BY cs.idea_id""", (reviewer, sid[0])))
    return {"sample_id": sid[0], "items": items}


def objections(*, dsn: str, status: str) -> dict:
    with db.connect(dsn) as conn:
        items = _rows(conn.execute(
            """SELECT o.id, o.idea_id, i.title, o.kind, o.body, o.status, o.submitted_at, o.pulled_at, o.resolution,
                      o.resolved_at, o.resolved_by
                 FROM core.objection o LEFT JOIN core.idea i ON i.id = o.idea_id
                WHERE o.status=%s ORDER BY o.id""", (status,)))
    return {"items": items}
