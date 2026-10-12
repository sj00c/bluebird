"""Console request validation, independent of routing and database access."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from .. import objections


def no_control_characters(value: str | None) -> str | None:
    """Allow newlines and tabs, but reject controls including PostgreSQL's invalid NUL."""
    if value is not None and objections.CTRL.search(value):
        raise ValueError("control characters are not allowed")
    return value


def http_url(value: str) -> str:
    no_control_characters(value)
    parts = urlsplit(value)
    if (parts.scheme not in ("http", "https") or not parts.hostname
            or parts.username is not None or parts.password is not None
            or any(c.isspace() for c in value)):
        raise ValueError("URL must be an absolute http(s) URL without credentials or whitespace")
    try:
        _ = parts.port
    except ValueError as e:
        raise ValueError("URL has an invalid port") from e
    return value


Text = Annotated[str, Field(min_length=1, max_length=4000), AfterValidator(no_control_characters)]
HttpURL = Annotated[str, Field(min_length=1, max_length=2048), AfterValidator(http_url)]
Cause = Literal["T", "D", "R", "M", "C", "O", "U"]
Axis = Literal["tech", "data", "regulation", "policy"]
AxisScore = Annotated[int, Field(strict=True, ge=0, le=5)]
Stage = Literal["raw", "s0", "s1", "s2", "s3", "s4", "s5", "s6"]
ObjectionStatus = Literal["open", "accepted", "rejected"]


class AuthoringIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class TraceIn(AuthoringIn):
    result: Literal["found", "none"]
    status: Literal["realized", "pivot", "similar_unlinked", "award_only", "none"] | None = None
    url: HttpURL | None = None
    note: Text


class EvidenceIn(AuthoringIn):
    url: HttpURL
    excerpt: Text | None = None


class DiagnosisIn(AuthoringIn):
    cause: Cause
    secondary: Cause | None = None
    rationale: Text
    evidence: list[EvidenceIn] = Field(max_length=30)


class MatchIn(AuthoringIn):
    change_id: Annotated[str, Field(min_length=1, max_length=500), AfterValidator(no_control_characters)]
    verdict: Literal["yes", "partial", "no", "human"]
    what_changed: list[Text] = Field(min_length=1, max_length=20)
    how_now: Text


class ScoresIn(AuthoringIn):
    tech: AxisScore | None = None
    data: AxisScore | None = None
    regulation: AxisScore | None = None
    policy: AxisScore | None = None


class ScoreIn(AuthoringIn):
    scores: ScoresIn
    evidence: dict[Axis, HttpURL]
    as_of: date | None = None


class ReviewIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    round: Literal["final", "expert", "audit"]
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2000)
    _ctrl = field_validator("note")(no_control_characters)


class CodeIn(BaseModel):
    code: Cause
    note: str | None = Field(default=None, max_length=1000)
    _ctrl = field_validator("note")(no_control_characters)


class ResolveIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    decision: Literal["accepted", "rejected"]
    resolution: str = Field(min_length=1, max_length=2000)
    withhold: bool = False
    _ctrl = field_validator("resolution")(no_control_characters)
