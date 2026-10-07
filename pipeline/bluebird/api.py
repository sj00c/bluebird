"""backend-api: 관리자 콘솔 전용 FastAPI(업무망 안에서만). 외부 호출 없음(egress도 쓰지 않는다).

인증: Authorization: Bearer <token>. 토큰 → 사람·역할은 BB_API_USERS(JSON 파일 경로)
    {"<sha256(token) hex>": {"user": "kim", "roles": ["reviewer", "coder"]}, ...}
토큰 원문은 서버에 두지 않는다(해시만). 파일을 바꾸면 backend-api를 다시 시작해야 반영된다(토큰 회수 포함).
역할: reviewer(최종 승인·반려·이의 처리), coder(2인 독립 코딩), expert(전문가 승인 라운드), auditor(감사 라운드).
맹검: coder_a/coder_b 코드는 어떤 응답에도 다른 사람에게 나가지 않는다(자기 코드만). 코더만인 사람은 큐·상세를 볼 수
없다(시스템 예측 원인·검토 기록을 보고 코딩하면 κ가 부풀려진다). 이의 본문(개인정보일 수 있음)은 reviewer·auditor만.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from functools import lru_cache
from typing import Annotated, Literal

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import db, funnel, objections, wording

ROLES = frozenset({"reviewer", "coder", "expert", "auditor"})
STAFF = ("reviewer", "expert", "auditor")
STAGES = ("s0", "s1", "s2", "s3", "s4", "s5", "s6")
ROUND_ROLE = {"final": "reviewer", "expert": "expert", "audit": "auditor"}

app = FastAPI(title="bluebird backend-api", docs_url=None, redoc_url=None, openapi_url=None)


def _dsn() -> str:
    dsn = os.environ.get("BB_DSN")
    if not dsn:
        raise RuntimeError("BB_DSN not set")
    return dsn


@lru_cache(maxsize=1)
def _users() -> dict[str, dict]:
    path = os.environ.get("BB_API_USERS")
    if not path:
        raise RuntimeError("BB_API_USERS not set")
    with open(path, encoding="utf-8") as f:
        users = json.load(f)
    for h, u in users.items():
        if len(h) != 64 or not isinstance(u.get("user"), str) or not isinstance(u.get("roles"), list):
            raise RuntimeError("BB_API_USERS: keys are sha256 hex, values {user, roles[]}")
        if not u["roles"] or not set(u["roles"]) <= ROLES:
            raise RuntimeError(f"BB_API_USERS: {u['user']} roles must be a non-empty subset of {sorted(ROLES)}")
    return users


class User(BaseModel):
    user: str
    roles: list[str]


def current_user(authorization: Annotated[str | None, Header()] = None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    digest = hashlib.sha256(authorization[7:].strip().encode()).hexdigest()
    for h, u in _users().items():
        if hmac.compare_digest(h, digest):
            return User(**u)
    raise HTTPException(401, "unknown token")


def need(*roles: str):
    def dep(u: Annotated[User, Depends(current_user)]) -> User:
        if not set(roles) & set(u.roles):
            raise HTTPException(403, f"role {'|'.join(roles)} required")
        return u
    return dep


Me = Annotated[User, Depends(current_user)]


def _no_ctrl(v: str | None) -> str | None:
    """메모·처리 내용에 제어문자(줄바꿈·탭 제외)는 받지 않는다(NUL은 DB가 거부해 500이 됐다)."""
    if v is not None and objections.CTRL.search(v):
        raise ValueError("control characters are not allowed")
    return v
Staff = Annotated[User, Depends(need(*STAFF))]


def _rows(cur) -> list[dict]:
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _snap(conn) -> int:
    return conn.execute("SELECT coalesce(max(id), -1) FROM core.catalog_snapshot").fetchone()[0]


# ----------------------------------------------------------------------------- 조회

@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/me")
def me(u: Me) -> User:
    return u


@app.get("/api/queue")
def queue(u: Staff, stage: Literal["s2", "s3", "s4", "s5", "s6"] = "s4",
          limit: Annotated[int, Query(ge=1, le=500)] = 50) -> dict:
    nxt = STAGES[STAGES.index(stage) + 1] if stage != "s6" else None
    with db.connect(_dsn()) as conn:
        snap = _snap(conn)
        counts = conn.execute(
            "SELECT " + ", ".join(f"count(*) FILTER (WHERE {s})" for s in STAGES)
            + " FROM core.funnel_stage(%s)", (snap,)).fetchone()
        items = _rows(conn.execute(
            f"""SELECT f.idea_id, i.title, i.year, f.source_id, f.cause, t.s, t.verdict
                  FROM core.funnel_stage(%s) f JOIN core.idea i ON i.id = f.idea_id
                  LEFT JOIN LATERAL (SELECT s, verdict FROM core.timeliness x WHERE x.idea_id = f.idea_id
                                      ORDER BY as_of DESC LIMIT 1) t ON true
                 WHERE f.{stage} {f"AND NOT f.{nxt}" if nxt else ""}
                 ORDER BY t.s DESC NULLS LAST, f.idea_id LIMIT %s""", (snap, limit)))
    for it in items:
        it["stage"] = stage
    return {"items": items, "counts": dict(zip(STAGES, counts))}


@app.get("/api/ideas/{idea_id}")
def idea_detail(idea_id: str, u: Staff) -> dict:
    with db.connect(_dsn()) as conn:
        snap = _snap(conn)
        idea = _rows(conn.execute(
            """SELECT i.id, i.title, i.body, i.year, i.award, c.name AS contest, i.source_id, s.public_ok,
                      i.withheld_at
                 FROM core.idea i JOIN core.source s ON s.id = i.source_id JOIN core.contest c ON c.id = i.contest_id
                WHERE i.id = %s AND i.retired_at IS NULL""", (idea_id,)))
        if not idea:
            raise HTTPException(404, "no such idea")
        card = _rows(conn.execute(
            "SELECT card_kind, problem, solution, missing_data, extractor FROM core.idea_card WHERE idea_id=%s",
            (idea_id,)))
        trace = _rows(conn.execute(
            "SELECT status, profile_version, external_search FROM core.trace_verdict WHERE idea_id=%s", (idea_id,)))
        checks = _rows(conn.execute(
            "SELECT item, result, detail FROM core.trace_check WHERE idea_id=%s ORDER BY item", (idea_id,)))
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
        tl = _rows(conn.execute(
            """SELECT as_of, tech, data, regulation, policy, n_scored, s, verdict, resolve_condition, scored_by
                 FROM core.timeliness WHERE idea_id=%s ORDER BY as_of DESC LIMIT 1""", (idea_id,)))
        stage = _rows(conn.execute(
            "SELECT " + ", ".join(STAGES) + " FROM core.funnel_stage(%s) WHERE idea_id=%s", (snap, idea_id)))
        reviews = _rows(conn.execute(  # 맹검: 코더 라운드는 빼고
            """SELECT round, reviewer, decision, code, note, created_at FROM core.review
                WHERE target_type='idea' AND target_id=%s AND round NOT IN ('coder_a','coder_b')
                ORDER BY created_at""", (idea_id,)))
        objs = _rows(conn.execute(
            """SELECT id, kind, body, status, resolution, submitted_at, resolved_at, resolved_by FROM core.objection
                WHERE idea_id=%s ORDER BY id""", (idea_id,)))
    if diag:
        diag[0]["evidence"] = diag_ev
    if trace:
        trace[0]["checks"] = checks
    return {"idea": idea[0], "card": card[0] if card else None, "trace": trace[0] if trace else None,
            "diagnosis": diag[0] if diag else None, "matches": matches, "timeliness": tl[0] if tl else None,
            "stage": stage[0] if stage else dict.fromkeys(STAGES, False), "reviews": reviews,
            "objections": objs}


# ----------------------------------------------------------------------------- 승인

class ReviewIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    round: Literal["final", "expert", "audit"]
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2000)
    _ctrl = field_validator("note")(_no_ctrl)


@app.post("/api/ideas/{idea_id}/review")
def review(idea_id: str, body: ReviewIn, u: Staff) -> dict:
    role = ROUND_ROLE[body.round]
    if role not in u.roles:
        raise HTTPException(403, f"role {role} required for round {body.round}")
    note = (body.note or "").strip() or None
    try:
        wording.check(note)
        if body.round == "final" and body.decision == "approve":
            funnel.approve(dsn=_dsn(), idea_id=idea_id, by=u.user, note=note)
        elif body.round == "final":
            if not note:
                raise HTTPException(422, "reject needs a note")
            funnel.reject(dsn=_dsn(), idea_id=idea_id, by=u.user, note=note)
        else:
            with db.connect(_dsn()) as conn:
                funnel._live_idea(conn, idea_id)
                conn.execute("INSERT INTO core.review (target_type, target_id, reviewer, round, decision, note)"
                             " VALUES ('idea',%s,%s,%s,%s,%s)", (idea_id, u.user, body.round, body.decision, note))
                conn.commit()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:  # 단계 미통과, 금지 문구 등
        raise HTTPException(409, str(e)) from e
    return {"ok": True, "stage": idea_detail(idea_id, u)["stage"]}


# ----------------------------------------------------------------------------- 2인 독립 코딩

@app.get("/api/coding")
def coding(u: Annotated[User, Depends(need("coder"))]) -> dict:
    with db.connect(_dsn()) as conn:
        sid = conn.execute("SELECT sample_id FROM core.coding_sample ORDER BY created_at DESC LIMIT 1").fetchone()
        if sid is None:
            return {"sample_id": None, "items": []}
        items = _rows(conn.execute(
            """SELECT cs.idea_id, i.title, i.body, k.problem AS card_problem, k.missing_data,
                      (SELECT r.code FROM core.review r WHERE r.target_type='idea' AND r.target_id=cs.idea_id
                          AND r.round IN ('coder_a','coder_b') AND r.reviewer=%s) AS my_code
                 FROM core.coding_sample cs JOIN core.idea i ON i.id = cs.idea_id
                 LEFT JOIN core.idea_card k ON k.idea_id = cs.idea_id
                WHERE cs.sample_id=%s ORDER BY cs.idea_id""", (u.user, sid[0])))
    return {"sample_id": sid[0], "items": items}


class CodeIn(BaseModel):
    code: Literal["T", "D", "R", "M", "C", "O", "U"]
    note: str | None = Field(default=None, max_length=1000)
    _ctrl = field_validator("note")(_no_ctrl)


@app.post("/api/coding/{idea_id}")
def code(idea_id: str, body: CodeIn, u: Annotated[User, Depends(need("coder"))]) -> dict:
    try:
        objections.code(dsn=_dsn(), idea_id=idea_id, reviewer=u.user, code_=body.code, note=body.note)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except (PermissionError, psycopg.errors.UniqueViolation, psycopg.errors.RaiseException) as e:
        raise HTTPException(409, "coder slot conflict: " + str(e).splitlines()[0]) from e
    return {"ok": True}


# ----------------------------------------------------------------------------- 이의 처리

@app.get("/api/objections")
def list_objections(u: Annotated[User, Depends(need("reviewer", "auditor"))], status: Literal["open", "accepted", "rejected"] = "open") -> dict:
    with db.connect(_dsn()) as conn:
        items = _rows(conn.execute(
            """SELECT o.id, o.idea_id, i.title, o.kind, o.body, o.status, o.submitted_at, o.pulled_at, o.resolution,
                      o.resolved_at, o.resolved_by
                 FROM core.objection o LEFT JOIN core.idea i ON i.id = o.idea_id
                WHERE o.status=%s ORDER BY o.id""", (status,)))
    return {"items": items}


class ResolveIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    decision: Literal["accepted", "rejected"]
    resolution: str = Field(min_length=1, max_length=2000)
    withhold: bool = False
    _ctrl = field_validator("resolution")(_no_ctrl)


@app.post("/api/objections/{objection_id}/resolve")
def resolve(objection_id: Annotated[int, Path(ge=1, le=2**63 - 1)], body: ResolveIn, u: Annotated[User, Depends(need("reviewer"))]) -> dict:
    try:
        objections.resolve(dsn=_dsn(), objection_id=objection_id, decision=body.decision,
                           resolution=body.resolution, by=u.user, withhold=body.withhold)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return {"ok": True}


def main() -> None:
    import uvicorn
    uvicorn.run(app, host=os.environ.get("BB_API_HOST", "0.0.0.0"), port=int(os.environ.get("BB_API_PORT", "8000")),
                proxy_headers=False, server_header=False)


if __name__ == "__main__":
    main()
