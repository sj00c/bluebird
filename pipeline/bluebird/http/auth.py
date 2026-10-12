"""Bearer authentication and console role policy.

BB_API_USERS maps SHA-256 token hashes to people and roles. The file is cached
until process restart, including token revocations. Coder-only users cannot read
staff queues or detail: predicted causes and reviews would contaminate coding.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, TypedDict

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

ROLES = frozenset({"reviewer", "coder", "expert", "auditor"})
STAFF_ROLES = ("reviewer", "expert", "auditor")
ROUND_ROLE = {"final": "reviewer", "expert": "expert", "audit": "auditor"}


class TokenIdentity(TypedDict):
    user: str
    roles: list[str]


@lru_cache(maxsize=1)
def load_users() -> dict[str, TokenIdentity]:
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
    for h, u in load_users().items():
        if hmac.compare_digest(h, digest):
            return User(**u)
    raise HTTPException(401, "unknown token")


def require_roles(*roles: str) -> Callable[..., User]:
    def authorized_user(u: Annotated[User, Depends(current_user)]) -> User:
        if not set(roles) & set(u.roles):
            raise HTTPException(403, f"role {'|'.join(roles)} required")
        return u
    return authorized_user


def require_review_round(user: User, round_: str) -> None:
    role = ROUND_ROLE[round_]
    if role not in user.roles:
        raise HTTPException(403, f"role {role} required for round {round_}")


def can_read_objections(user: User) -> bool:
    return bool(set(user.roles) & {"reviewer", "auditor"})


Me = Annotated[User, Depends(current_user)]
Staff = Annotated[User, Depends(require_roles(*STAFF_ROLES))]
Reviewer = Annotated[User, Depends(require_roles("reviewer"))]
Coder = Annotated[User, Depends(require_roles("coder"))]
ObjectionReader = Annotated[User, Depends(require_roles("reviewer", "auditor"))]
