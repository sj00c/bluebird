"""2인 독립 코딩 표본(G3 κ): 층화 표본 생성, 코더 슬롯 배정."""

from __future__ import annotations

import random

from . import db


def make_sample(*, dsn: str, size: int = 100, seed: int, sample_id: str | None = None) -> dict:
    """모집단 = (1단계 통과 ∪ 흔적 pending) ∩ card_kind ∈ {full, local_extract}. 층 = 소스 × 사전 예측 원인
    (진단이 있으면 그 원인, 없으면 '-'). 층 크기 비례 배분(최소 1), seed로 재현."""
    sample_id = sample_id or f"k{size}-s{seed}"
    with db.connect(dsn) as conn:
        if conn.execute("SELECT 1 FROM core.coding_sample WHERE sample_id=%s LIMIT 1", (sample_id,)).fetchone():
            raise ValueError(f"sample {sample_id} already exists")
        snap = conn.execute("SELECT max(id) FROM core.catalog_snapshot").fetchone()[0]
        pop = conn.execute(
            """SELECT f.idea_id, f.source_id || ':' || coalesce(f.cause, '-')
                 FROM core.funnel_stage(coalesce(%s, -1)) f
                 JOIN core.idea i ON i.id = f.idea_id AND i.withheld_at IS NULL
                WHERE (f.s1 OR f.trace_status = 'pending') AND f.card_kind IN ('full', 'local_extract')
                ORDER BY f.idea_id""", (snap,)).fetchall()
        if len(pop) < size:
            raise ValueError(f"population {len(pop)} < sample size {size}")
        strata: dict[str, list[str]] = {}
        for idea_id, st in pop:
            strata.setdefault(st, []).append(idea_id)
        rng = random.Random(seed)
        quota = {s: max(1, round(size * len(v) / len(pop))) for s, v in strata.items()}
        while sum(quota.values()) > size:  # 반올림 초과분 = 큰 층에서 차감
            big = max((s for s in quota if quota[s] > 1), key=lambda s: quota[s])
            quota[big] -= 1
        while sum(quota.values()) < size:
            big = max(strata, key=lambda s: len(strata[s]) - quota[s])
            quota[big] += 1
        picked = []
        for st in sorted(strata):
            for idea_id in rng.sample(strata[st], min(quota[st], len(strata[st]))):
                picked.append((sample_id, idea_id, st, seed))
        conn.cursor().executemany(
            "INSERT INTO core.coding_sample (sample_id, idea_id, stratum, seed) VALUES (%s,%s,%s,%s)", picked)
        conn.commit()
    out = {"sample_id": sample_id, "size": len(picked), "strata": {s: quota[s] for s in sorted(quota)}}
    print(f"[coding] sample {out}")
    return out


def code(*, dsn: str, idea_id: str, reviewer: str, code_: str, note: str | None = None,
         sample_id: str | None = None) -> str:
    """코더 한 명의 코드. 슬롯(coder_a/b)은 서버가 정한다: 내 슬롯이 있으면 갱신, 없으면 빈 슬롯."""
    if code_ not in ("T", "D", "R", "M", "C", "O", "U"):
        raise ValueError("code must be one of T D R M C O U")
    with db.connect(dsn) as conn:
        # 표본 행을 잠가 같은 아이디어의 슬롯 배정을 줄 세운다(동시 첫 코드도 409로 끝난다).
        q = "SELECT 1 FROM core.coding_sample WHERE idea_id=%s" + (" AND sample_id=%s" if sample_id else "")
        if conn.execute(q + " FOR UPDATE", (idea_id, sample_id) if sample_id else (idea_id,)).fetchone() is None:
            raise KeyError(f"{idea_id} is not in a coding sample")
        slots = dict(conn.execute(
            """SELECT round, reviewer FROM core.review WHERE target_type='idea' AND target_id=%s
                 AND round IN ('coder_a','coder_b') FOR UPDATE""", (idea_id,)).fetchall())
        mine = next((r for r, who in slots.items() if who == reviewer), None)
        if mine:
            conn.execute("""UPDATE core.review SET code=%s, note=%s, created_at=now()
                             WHERE target_type='idea' AND target_id=%s AND round=%s""", (code_, note, idea_id, mine))
        else:
            free = next((r for r in ("coder_a", "coder_b") if r not in slots), None)
            if free is None:
                raise PermissionError(f"{idea_id} already has two coders")
            conn.execute("""INSERT INTO core.review (target_type, target_id, reviewer, round, decision, code, note)
                            VALUES ('idea',%s,%s,%s,'code',%s,%s)""", (idea_id, reviewer, free, code_, note))
            mine = free
        conn.commit()
    return mine
