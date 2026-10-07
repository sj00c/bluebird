"""적재 시점 식별정보 처리. 팀명 원문은 이 모듈에서 소비되고 DB에 저장되지 않는다.

- 익명 ID: HMAC(익명화 비밀키, source + 원천키). 비밀키는 업무망 backend 비밀 경로에만 있고 DB·DMZ에는 없다.
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
_LIST_SEP = re.compile(r"[,，、·/]")
_LIST_SPLIT = re.compile(r"[\s,，、·/]+")
_NOT_NAME = frozenset({"외", "등", "팀", "및"})
_COUNT_TOKEN = re.compile(r"^\d+\s*(명|인|개)?$")


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
    if _PAREN.search(team) or _LIST_SEP.search(team):
        # '메디뷰(MediView)' → '메디뷰', 'MediView' / '팀명(이름1, 이름2)'·'이름1, 이름2' → 이름마다 마스킹
        variants.update(t for t in _LIST_SPLIT.split(_PAREN.sub(" ", team)) if _maskable_token(t))
    for v in sorted((v for v in variants if len(v) >= 2), key=len, reverse=True):
        # 라틴 문자로 시작·끝나는 변형은 단어 경계에서만(maintain 안의 'AI' 같은 오치환 방지)
        pre = r"(?<![A-Za-z0-9])" if v[0].isascii() and v[0].isalnum() else ""
        post = r"(?![A-Za-z0-9])" if v[-1].isascii() and v[-1].isalnum() else ""
        text = re.sub(pre + re.escape(v) + post, MASK, text, flags=re.IGNORECASE)
    return text


def _maskable_token(t: str) -> bool:
    """팀 목록에서 떼어 낸 낱말 중 이름처럼 보이는 것만: 한글 2–4자 이름 또는 숫자가 아닌 3자 이상."""
    if t in _NOT_NAME or _COUNT_TOKEN.match(t):
        return False
    return bool(_PERSON_NAME.match(t)) or len(t) >= 3
