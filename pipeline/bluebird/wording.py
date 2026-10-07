"""공개 문구 규칙(계획 §2.1 원칙 1, §3.4).

날짜만으로 "그때는 없었다"를 증명하지 못하므로 그런 문구를 쓰지 않는다. 사람이 입력한 how_now·rationale 등
공개될 수 있는 글은 저장 전에 check()를 통과해야 한다. 화면 문구는 test_forbidden_phrases가 소스를 훑는다.
"""

from __future__ import annotations

import re

FORBIDDEN = re.compile(
    r"그\s*때\s*(는|엔|에는)?\s*없(던|었던|었다|었음)"
    r"|당시(에는|엔|에)?\s*없(던|었던|었다|었음)"
    r"|당시(에는|엔|에)?\s*(미개방|비공개)(이던|이었던|였던)"
    r"|그\s*당시\s*존재하지\s*않"
)

# 카탈로그 tier별 화면 문구(§3.10). 날짜는 "관측"·"등록"으로만 말한다.
TIER_TEXT = {
    "observed_new": "파랑새 관측 {first_seen_at} 신규",
    "reappeared": "{first_seen_at} 목록에 다시 나타남, 포털 등록 {registered_at}",
    "portal_registered": "포털 등록 {registered_at}",
}


class WordingError(ValueError):
    pass


def check(*texts: str | None) -> None:
    for t in texts:
        if t and (m := FORBIDDEN.search(t)):
            raise WordingError(f"금지 문구 {m.group(0)!r}: 날짜만으로 '그때 없었다'고 말하지 않는다")
