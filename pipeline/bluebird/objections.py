"""이의 제기 왕복(G11)과 2인 독립 코딩 표본.

이의: 국민 → portal → DMZ inbox.objection(INSERT만) → backend-jobs가 pull(건수·크기 상한, 검증) →
core.objection 저장 → DMZ에서 삭제 → 콘솔에서 사람이 처리 → 수용이면 공개 철회(필요하면 원본까지 공개 중단) →
다음 publish 주기에 반영. 연결은 항상 업무망이 연다.
"""

from __future__ import annotations

import random
import re
from datetime import datetime
from uuid import UUID

from . import db, wording

KINDS = ("fact", "cause", "change", "privacy", "other")
ID_RE = re.compile(r"^ID-[0-9]{4}-[0-9a-f]{10}$")
MAX_BODY = 2000
PULL_LIMIT = 200  # 한 번에 가져오는 건수 상한(DMZ가 넘겨도 나머지는 다음 주기)
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validate(row: tuple) -> tuple[dict | None, str | None]:
    """DMZ에서 온 행은 믿지 않는다: DB CHECK와 같은 규칙을 다시 검사하고 제어문자를 지운다."""
    dmz_id, dmz_uid, idea_id, kind, body, submitted_at = row
    if not isinstance(dmz_id, int) or not isinstance(dmz_uid, UUID) or not isinstance(submitted_at, datetime):
        return None, "bad id/time"
    if not isinstance(idea_id, str) or not ID_RE.match(idea_id):
        return None, "bad idea_id"
    if kind not in KINDS:
        return None, "bad kind"
    if not isinstance(body, str):
        return None, "bad body"
    body = CTRL.sub("", body).strip()
    if not 1 <= len(body) <= MAX_BODY:
        return None, "bad body length"
    return {"dmz_id": dmz_id, "dmz_uid": dmz_uid, "idea_id": idea_id, "kind": kind, "body": body, "submitted_at": submitted_at}, None


def pull(*, dsn: str, inbox_dsn: str, limit: int = PULL_LIMIT) -> dict:
    """inbox에서 최대 limit건을 읽어 검증·저장한 뒤, 읽은 행만 DMZ에서 지운다(core 커밋 뒤). 다시 돌려도 안전하다."""
    stats = {"read": 0, "stored": 0, "duplicate": 0, "invalid": 0, "unknown_idea": 0, "deleted": 0, "backlog": 0}
    with db.pipeline_run(dsn, "objections-pull") as run:
        with db.connect(inbox_dsn) as dmz:
            rows = dmz.execute(
                "SELECT id, uid, idea_id, kind, left(body, %s), submitted_at FROM inbox.objection ORDER BY id LIMIT %s",
                (MAX_BODY + 1, limit)).fetchall()
            dmz.rollback()
        stats["read"] = len(rows)
        if not rows:
            run.update(stats)
            print(f"[objections] pull {stats}")
            return stats
        with db.connect(dsn) as core:
            for row in rows:
                obj, why = validate(row)
                if obj is None:  # 본문은 남기지 않고 사유별 건수만
                    stats["invalid"] += 1
                    stats[f"invalid:{why}"] = stats.get(f"invalid:{why}", 0) + 1
                    continue
                if core.execute("SELECT 1 FROM core.idea WHERE id=%s", (obj["idea_id"],)).fetchone() is None:
                    stats["unknown_idea"] += 1
                    continue
                if core.execute("SELECT 1 FROM core.objection WHERE dmz_uid IS NULL AND dmz_id=%s AND submitted_at=%s",
                                (obj["dmz_id"], obj["submitted_at"])).fetchone():
                    stats["duplicate"] += 1  # uid 도입 전에 가져왔지만 DMZ에서 지우기 전에 끊긴 행
                    continue
                n = core.execute(
                    """INSERT INTO core.objection (dmz_id, dmz_uid, idea_id, kind, body, submitted_at)
                       VALUES (%(dmz_id)s,%(dmz_uid)s,%(idea_id)s,%(kind)s,%(body)s,%(submitted_at)s)
                       ON CONFLICT (dmz_uid) DO NOTHING""", obj).rowcount
                stats["stored" if n else "duplicate"] += 1
            core.commit()
        with db.connect(inbox_dsn) as dmz:
            stats["deleted"] = dmz.execute("DELETE FROM inbox.objection WHERE id = ANY(%s)",
                                           ([r[0] for r in rows],)).rowcount
            dmz.commit()
            # 상한 때문에 남은 건수(다음 주기). 계속 쌓이면 스팸·처리 지연 신호다.
            stats["backlog"] = dmz.execute("SELECT count(*) FROM inbox.objection").fetchone()[0]
            dmz.rollback()
        run.update(stats)
    print(f"[objections] pull {stats}")
    return stats


def resolve(*, dsn: str, objection_id: int, decision: str, resolution: str, by: str, withhold: bool = False) -> dict:
    """사람 처리. accepted면 그 아이디어의 공개 승인을 모두 철회하고, withhold면 원본 카드까지 공개를 멈춘다."""
    if decision not in ("accepted", "rejected"):
        raise ValueError("decision must be accepted|rejected")
    resolution = (resolution or "").strip()
    if not resolution:
        raise ValueError("resolution is required")
    if withhold and decision != "accepted":
        raise ValueError("withhold only with accepted")
    wording.check(resolution)
    with db.connect(dsn) as conn:
        row = conn.execute("SELECT idea_id, status FROM core.objection WHERE id=%s FOR UPDATE",
                           (objection_id,)).fetchone()
        if row is None:
            raise KeyError(f"no objection {objection_id}")
        idea_id, status = row
        if status != "open":
            raise ValueError(f"objection {objection_id} already {status}")
        conn.execute(
            """UPDATE core.objection SET status=%s, resolution=%s, resolved_at=now(), resolved_by=%s, withheld=%s
                WHERE id=%s""", (decision, resolution, by, withhold, objection_id))
        conn.execute("INSERT INTO core.review (target_type, target_id, reviewer, round, decision, note)"
                     " VALUES ('objection',%s,%s,'final',%s,%s)",
                     (str(objection_id), by, "approve" if decision == "accepted" else "reject", resolution))
        if decision == "accepted":
            conn.execute("SELECT core.revoke_idea(%s)", (idea_id,))
            if withhold:
                conn.execute("UPDATE core.idea SET withheld_at=now(), withheld_reason=%s WHERE id=%s",
                             (f"objection {objection_id}", idea_id))
        conn.commit()
    return {"objection_id": objection_id, "idea_id": idea_id, "decision": decision, "withheld": withhold}


# ----------------------------------------------------------------------------- κ 표본(2인 독립 코딩)

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
        while sum(quota.values()) > size:  # 반올림 초과분은 큰 층에서 뺀다
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
