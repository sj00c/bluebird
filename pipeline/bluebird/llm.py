"""상용 LLM 호출 공통부. 실제 전송은 egress.llm만 한다(본문 생성·반출 검사·감사).

공급자는 키가 있는 쪽을 쓴다(BB_LLM_PROVIDER로 고정 가능). 키가 없으면 None → 호출자는 규칙·사람 경로로 간다.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from .egress import LLM_ENDPOINTS, Egress, Field

DEFAULT_MODELS = {"openai": "gpt-4.1-mini", "anthropic": "claude-sonnet-4-5"}


@dataclass(frozen=True)
class Provider:
    name: str
    model: str


def provider() -> Provider | None:
    want = os.environ.get("BB_LLM_PROVIDER")
    order = [want] if want else ["openai", "anthropic"]
    for name in order:
        if name in LLM_ENDPOINTS and os.environ.get(LLM_ENDPOINTS[name][1]):
            return Provider(name, os.environ.get("BB_LLM_MODEL") or DEFAULT_MODELS[name])
    return None


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.DOTALL)


def ask_json(eg: Egress, p: Provider, *, system: str, instruction: str, fields: dict[str, Field],
             max_tokens: int = 1500) -> tuple[dict, int | None]:
    text, resp = eg.llm(provider=p.name, model=p.model, system=system, instruction=instruction,
                        fields=fields, max_tokens=max_tokens)
    data = json.loads(_FENCE.sub("", text.strip()))
    if not isinstance(data, dict):
        raise ValueError("LLM did not return a JSON object")  # noqa: TRY004 — 응답 형식 오류로 취급
    return data, resp.egress_call_id
