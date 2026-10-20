"""적재 시점 식별정보 처리. 팀명 원문: 이 모듈에서만 소비, DB 저장 없음.

- 익명 ID: HMAC(익명화 비밀키, source + 원천키). 비밀키 = .runtime/secrets 전용, DB 없음
- 팀명 마스킹: 본문 내 팀명 → ○○
- team_kind: 흔적 판정 규칙(파일럿 step1/step2)용 팀명 유형 신호. 팀명 자체 전달 없음
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
# 팀 목록에서 떼어 내도 이름이 아닌 흔한 낱말(본문의 같은 낱말까지 ○○가 되면 카드가 망가진다)
_NOT_NAME = frozenset({"외", "등", "팀", "및", "데이터", "정보", "서비스", "스마트", "연구소", "연구실", "플랫폼",
                       "솔루션", "주식회사", "컴퍼니", "랩", "그룹", "대학교", "학교", "센터", "시스템"})
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


_MASK_CHAR = re.compile(r"[○*]")


def name_variants(team: str) -> list[str]:
    """팀명·성명 → 본문 출현 가능 형태(긴 순, 2자 이상). mask_team·G10 감사 공용.
    부분 마스킹 팀('이**(브레싱스)'): 브랜드 부분 유지."""
    if not team:
        return []
    cleaned = clean_team(team)
    variants = {team.strip(), cleaned}
    if _PAREN.search(team) or _LIST_SEP.search(team):
        # 괄호 앞 팀명은 통째로('데이터 연구소(홍길동)' → '데이터 연구소')
        variants.add(_PAREN.split(team, 1)[0].strip())
        # '메디뷰(MediView)' → '메디뷰', 'MediView' / '팀명(이름1, 이름2)'·'이름1, 이름2' → 이름마다
        variants.update(t for t in _LIST_SPLIT.split(_PAREN.sub(" ", team)) if _maskable_token(t))
    return sorted((v for v in variants if len(v) >= 2), key=len, reverse=True)


def audit_variants(team: str) -> list[str]:
    """G10 대조용 형태: 마스킹 문자(○·*)가 든 형태는 이미 가려진 것이라 뺀다('이**(브레싱스)' → '브레싱스'만)."""
    return [v for v in name_variants(team) if not _MASK_CHAR.search(v)]


def _name_re(v: str) -> str:
    # 라틴 문자로 시작·끝나는 변형은 단어 경계에서만(maintain 안의 'AI' 같은 오치환 방지)
    pre = r"(?<![A-Za-z0-9])" if v[0].isascii() and v[0].isalnum() else ""
    post = r"(?![A-Za-z0-9])" if v[-1].isascii() and v[-1].isalnum() else ""
    return pre + re.escape(v) + post


def find_name(text: str | None, variants: list[str]) -> bool:
    """text에 이름 형태가 남아 있는가(G10 성명 일치 감사). 대소문자 무시, 라틴 낱말은 경계에서만."""
    return bool(text) and any(re.search(_name_re(v), text, flags=re.IGNORECASE) for v in variants)


def mask_team(text: str, team: str) -> str:
    """text 내 팀명(원형·정리형) → ○○. 2자 미만 팀명 = 오탐 → 치환 안 함."""
    if not text:
        return text
    for v in name_variants(team):
        text = re.sub(_name_re(v), MASK, text, flags=re.IGNORECASE)
    return text


# 시민제안 본문 연락처·'제안자 성명' 형태. 적재 전 고정 치환
# 휴대전화 01x · 지역번호 02~064 · 인터넷전화 070 · 수신자부담 080 · 평생번호 050x
_PHONE = re.compile(r"(?<!\d)(?:01[016789]|0[2-6]\d?|070|080|050\d)[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 명시 구분자 있는 형태만('제안자: 홍길동', '작성자(홍길동)', '신청인 홍길동 외 3명'). '제안자 본인이' 같은 일반 문장 보존
_ROLE = r"(제안자|신청인|작성자|제안인|대표자|성명)"
_PROPOSER = re.compile(
    rf"{_ROLE}\s*[:：]\s*[가-힣]{{2,4}}(?![가-힣])"
    rf"|{_ROLE}\s*[(（]\s*[가-힣]{{2,4}}\s*[)）]"
    rf"|{_ROLE}\s+[가-힣]{{2,4}}(?=\s*(?:외|등)\s*\d*\s*(?:명|인))")


def mask_contacts(text: str | None) -> str | None:
    """전화·이메일·'제안자 홍길동' → 고정 토큰. 본문 나머지 원문 유지."""
    if not text:
        return text
    text = _PHONE.sub("[전화]", text)
    text = _EMAIL.sub("[이메일]", text)
    return _PROPOSER.sub(lambda m: f"{next(g for g in m.groups() if g)} {MASK}", text)


def _maskable_token(t: str) -> bool:
    """팀 목록에서 떼어 낸 낱말 중 이름처럼 보이는 것만: 한글 2–4자 이름 또는 숫자가 아닌 3자 이상."""
    if t in _NOT_NAME or _COUNT_TOKEN.match(t):
        return False
    return bool(_PERSON_NAME.match(t)) or len(t) >= 3
