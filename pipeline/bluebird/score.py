"""시의성 S 규칙(계획 §3.7). 순수 함수 — DB와 무관하게 테스트한다.

- 항목 tech·data·regulation·policy(0–5 또는 None). 점수 있는 항목만 쓰고 가중치를 재정규화한다(기본 0.25).
- now(S≥4.0)·conditional(3.0≤S<4.0)은 점수 있는 항목 ≥2 이고, 매칭된 바뀐 것의 축이 점수 있는 항목에 들 때만.
  아니면 hold("판단 불가").
"""

from __future__ import annotations

from dataclasses import dataclass

AXES = ("tech", "data", "regulation", "policy")
EVIDENCE_EXCERPT = "시의성 축: "  # S 근거 excerpt 머리말(축 이름만, 채점자 없음). publish가 형식을 확인한다.
AXIS_KO = {"tech": "기술", "data": "데이터", "regulation": "규제", "policy": "정책"}
DEFAULT_WEIGHTS = dict.fromkeys(AXES, 0.25)
# 바뀐 것 종류 → S 축(D→data, R→regulation, C·M→policy, T→tech)
KIND_AXIS = {"dataset_opened": "data", "law_effective": "regulation", "announcement": "policy",
             "policy_news": "policy", "tech": "tech"}


@dataclass(frozen=True)
class Score:
    n_scored: int
    s: float | None
    verdict: str
    resolve_condition: str | None


def compute(scores: dict[str, int | None], change_kinds: set[str],
            weights: dict[str, float] | None = None) -> Score:
    w = weights or DEFAULT_WEIGHTS
    for k, v in scores.items():
        if k not in AXES:
            raise ValueError(f"unknown axis {k}")
        if v is not None and not 0 <= v <= 5:
            raise ValueError(f"{k}={v} out of 0..5")
    scored = {k: v for k, v in scores.items() if v is not None}
    if not scored:
        return Score(0, None, "hold", "판단 불가: 채점된 항목 없음")
    total_w = sum(w[k] for k in scored)
    raw = sum(w[k] * v for k, v in scored.items()) / total_w
    s = round(raw, 2)
    axes = {KIND_AXIS[k] for k in change_kinds if k in KIND_AXIS}
    if len(scored) < 2:
        return Score(len(scored), s, "hold", "판단 불가: 채점된 항목이 2개 미만")
    if not axes & scored.keys():
        return Score(len(scored), s, "hold", "판단 불가: 바뀐 것의 축이 채점되지 않음")
    if raw >= 4.0:
        return Score(len(scored), s, "now", None)
    if raw >= 3.0:
        low = min((v, k) for k, v in scored.items())[1]
        return Score(len(scored), s, "conditional", f"{AXIS_KO[low]}({low}) 조건 보완 필요")
    return Score(len(scored), s, "hold", "점수 3.0 미만")
