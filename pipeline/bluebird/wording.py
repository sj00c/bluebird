"""공개 문구 규칙(계획 §2.1 원칙 1, §3.4).

날짜만으로 "그때는 없었다"를 증명하지 못하므로 그런 문구를 쓰지 않는다. 사람이 입력한 how_now·rationale 등
공개될 수 있는 글은 저장 전에 check()를 통과해야 한다. 화면 문구는 test_forbidden_phrases가 소스를 훑는다.
"""

from __future__ import annotations

import re

# 과거 시점 말(그때·그땐·그때까지·당시·예전·과거·이전) + 부재 서술(없던·없었…·존재하지 않…·미개방·비공개이던)
_PAST = r"(?:그\s*때|그\s*땐|당시|예전|과거|이전|제출\s*당시|공모\s*당시)\s*(?:까지(?:는|만\s*해도)?|에는|에서는|에도|에|엔|는|은|만\s*해도)?"
_ABSENT = (r"(?:없(?:던|었)|존재하지\s*않(?:던|았)|나오지\s*않(?:던|았)|공개되지\s*않(?:던|았)"
           r"|개방되지\s*않(?:던|았)|(?:미개방|비공개)(?:이던|이었|였))")
FORBIDDEN = re.compile(_PAST + r"\s*(?:[가-힣A-Za-z0-9]+\s+){0,3}?" + _ABSENT
                       + r"|존재하지\s*않던|그\s*당시\s*존재하지\s*않")

# 카탈로그 tier별 화면 문구(§3.10). 날짜는 "관측"·"등록"으로만 말한다.
TIER_TEXT = {
    "observed_new": "파랑새 관측 {first_seen_at} 신규",
    "reappeared": "{first_seen_at} 목록에 다시 나타남, 포털 등록 {registered_at}",
    "portal_registered": "포털 등록 {registered_at}",
}


class WordingError(ValueError):
    pass


def find(text: str | None) -> str | None:
    m = FORBIDDEN.search(text) if text else None
    return m.group(0) if m else None


def check(*texts: str | None) -> None:
    for t in texts:
        if hit := find(t):
            raise WordingError(f"금지 문구 {hit!r}: 날짜만으로 '그때 없었다'고 말하지 않는다")
