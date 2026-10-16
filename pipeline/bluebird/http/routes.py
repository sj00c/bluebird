"""Console endpoints: authorize, validate, dispatch, and translate domain errors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import psycopg
from fastapi import APIRouter, HTTPException, Query

from .. import coding as coding_samples
from .. import funnel, wording
from . import queries
from .auth import Coder, Me, Reviewer, Staff, User, require_review_round
from .config import database_dsn
from .schemas import (
    CodeIn,
    DiagnosisIn,
    MatchIn,
    ReviewIn,
    ScoreIn,
    Stage,
    TraceIn,
    no_control_characters,
)

router = APIRouter()


def _search_text(value: str) -> None:
    try:
        no_control_characters(value)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def _author(workflow: Callable[..., object], **kwargs: object) -> dict[str, bool]:
    try:
        workflow(dsn=database_dsn(), **kwargs)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    except (psycopg.errors.RaiseException, psycopg.IntegrityError) as e:
        # Domain triggers enforce evidence and cause/change compatibility at commit.
        raise HTTPException(409, e.diag.message_primary or "domain constraint rejected this change") from e
    return {"ok": True}


@router.get("/healthz")
def healthz() -> dict:
    try:
        queries.check_database(dsn=database_dsn())
    except psycopg.Error as e:
        raise HTTPException(503, "core database unavailable") from e
    return {"ok": True}


@router.get("/api/me")
def me(u: Me) -> User:
    return u


@router.get("/api/overview")
def overview(u: Staff) -> dict:
    return queries.overview(dsn=database_dsn())


@router.get("/api/changes")
def changes(u: Staff, q: Annotated[str, Query(max_length=200)] = "",
            limit: Annotated[int, Query(ge=1, le=500)] = 50) -> dict:
    _search_text(q)
    return queries.changes(dsn=database_dsn(), q=q, limit=limit)


@router.get("/api/queue")
def queue(u: Staff, stage: Stage = "raw",
          q: Annotated[str, Query(max_length=200)] = "",
          limit: Annotated[int, Query(ge=1, le=500)] = 50,
          offset: Annotated[int, Query(ge=0)] = 0) -> dict:
    _search_text(q)
    return queries.queue(dsn=database_dsn(), stage=stage, q=q, limit=limit, offset=offset)


@router.get("/api/ideas/{idea_id}")
def idea_detail(idea_id: str, u: Staff) -> dict:
    detail = queries.idea_detail(dsn=database_dsn(), idea_id=idea_id)
    if detail is None:
        raise HTTPException(404, "no such idea")
    return detail


@router.post("/api/ideas/{idea_id}/trace")
def trace_set(idea_id: str, body: TraceIn, u: Reviewer) -> dict:
    return _author(funnel.trace_manual, idea_id=idea_id, by=u.user, **body.model_dump())


@router.post("/api/ideas/{idea_id}/diagnosis")
def diagnosis_set(idea_id: str, body: DiagnosisIn, u: Reviewer) -> dict:
    return _author(funnel.diagnose_set, idea_id=idea_id, by=u.user, cause=body.cause,
                   secondary=body.secondary, rationale=body.rationale,
                   evidence=[(e.url, e.excerpt) for e in body.evidence])


@router.post("/api/ideas/{idea_id}/match")
def match_set(idea_id: str, body: MatchIn, u: Reviewer) -> dict:
    return _author(funnel.match_set, idea_id=idea_id, by=u.user, **body.model_dump())


@router.post("/api/ideas/{idea_id}/score")
def score_set(idea_id: str, body: ScoreIn, u: Reviewer) -> dict:
    return _author(funnel.score_set, idea_id=idea_id, by=u.user, **body.model_dump())


@router.post("/api/ideas/{idea_id}/review")
def review(idea_id: str, body: ReviewIn, u: Staff) -> dict:
    require_review_round(u, body.round)
    note = (body.note or "").strip() or None
    try:
        wording.check(note)
        if body.round == "final" and body.decision == "approve":
            funnel.approve(dsn=database_dsn(), idea_id=idea_id, by=u.user, note=note)
        elif body.round == "final":
            if not note:
                raise HTTPException(422, "reject needs a note")
            funnel.reject(dsn=database_dsn(), idea_id=idea_id, by=u.user, note=note)
        else:
            funnel.review_round(dsn=database_dsn(), idea_id=idea_id, by=u.user,
                                round_=body.round, decision=body.decision, note=note)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return {"ok": True, "stage": idea_detail(idea_id, u)["stage"]}


@router.get("/api/coding")
def coding(u: Coder) -> dict:
    return queries.coding(dsn=database_dsn(), reviewer=u.user)


@router.post("/api/coding/{idea_id}")
def code(idea_id: str, body: CodeIn, u: Coder) -> dict:
    try:
        coding_samples.code(dsn=database_dsn(), idea_id=idea_id, reviewer=u.user, code_=body.code, note=body.note)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except (PermissionError, psycopg.errors.UniqueViolation, psycopg.errors.RaiseException) as e:
        raise HTTPException(409, "coder slot conflict: " + str(e).splitlines()[0]) from e
    return {"ok": True}
