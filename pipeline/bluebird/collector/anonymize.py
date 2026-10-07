"""수집존(Z1) 전용 식별정보 처리. 이 모듈의 입력(팀명 등)은 Z1 밖으로 나가지 않는다.

- 익명 ID: HMAC(z1 비밀키, source + 원천키). 비밀키가 Z1에만 있으므로 처리존·공개존에서 원천 행으로 역추적할 수 없다.
- 팀명 마스킹: 본문에 팀명이 그대로 들어간 경우 ○○로 치환한다.
- team_kind: 흔적 판정 규칙(파일럿 step1/step2)에 필요한 팀명 유형 신호. 팀명 자체는 넘기지 않는다.
"""

from __future__ import annotations

import hashlib
import hmac
import re

MASK = "○○"
_MASKED = re.compile(r"[○Oo*]{2,}|\*")
_PAREN = re.compile(r"[\(\)（）]")
_COUNT_SUFFIX = re.compile(r"\s(외|등)(\s*\d+\s*명?)?(?=\s|$)")
_PERSON_NAME = re.compile(r"^[가-힣]{2,4}$")


def anon_id(secret: bytes, source: str, source_key: str, year: int | None) -> str:
    digest = hmac.new(secret, f"{source}\x1f{source_key}".encode(), hashlib.sha256).hexdigest()
    return f"ID-{year or 0:04d}-{digest[:10]}"


def clean_team(team: str) -> str:
    """파일럿 step1_search.clean_team 규칙."""
    t = _PAREN.sub(" ", team)
    t = _COUNT_SUFFIX.sub(" ", t)
    t = t.replace("㈜", "").replace("(주)", "").replace("주식회사", "")
    return " ".join(t.split())


def team_kind(team: str) -> str:
    """empty | masked | person | brand.

    person은 '한글 2~4자 단독' 휴리스틱으로 개인 실명 가능성을 보수적으로 잡는다(브랜드형 짧은 팀명도 포함될 수 있음).
    person/masked는 흔적 검색에서 팀명을 쓰지 않고 아이템명으로만 검색한다(파일럿 규칙).
    """
    t = clean_team(team)
    if not t or t == "-":
        return "empty"
    if _MASKED.search(t):
        return "masked"
    if _PERSON_NAME.match(t) and not t.endswith(("팀", "조")):
        return "person"
    return "brand"


def mask_team(text: str, team: str) -> str:
    """text 안의 팀명(원형·정리형)을 ○○로 치환. 2자 미만 팀명은 오탐이 커서 치환하지 않는다."""
    if not text:
        return text
    cleaned = clean_team(team)
    variants = {team.strip(), cleaned}
    if _PAREN.search(team):  # '메디뷰(MediView)' → '메디뷰', 'MediView'도 각각 마스킹
        variants.update(cleaned.split())
    for v in sorted((v for v in variants if len(v) >= 2), key=len, reverse=True):
        text = re.sub(re.escape(v), MASK, text, flags=re.IGNORECASE)
    return text
