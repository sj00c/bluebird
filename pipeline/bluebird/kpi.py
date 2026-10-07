"""KPI 검증 도구(계획 §5 G1–G13).

- kappa: κ 표본(2인 독립 코딩) 일치도. 코딩이 없으면 human_blocked.
- goldset: 파일럿 골드셋(흔적 5클래스)과 우리 흔적 판정 비교, 혼동행렬·macro-F1.
  골드셋 CSV에는 팀명이 있으므로 파일은 실행 때 읽기만 하고 저장하지 않는다(연도·제목으로 맞춘 id·클래스만 기록).
- verify_top20: 주간 Top 20 = 전문가 승인 = 공개 weekly_top.
- report: G1–G13 현황표. 사람 입력이 필요한데 아직 없으면 human_blocked, 키가 없으면 key_required.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import date

from psycopg.types.json import Jsonb

from . import db
from .publish import QUERIES, columns
from .sources_check import REMOTES

CODES = ("T", "D", "R", "M", "C", "O", "U")
TRACE_CLASSES = ("realized", "pivot", "similar_unlinked", "award_only", "none")
KAPPA_TARGET = 0.7
GOLD_F1_DROP_PT = 5.0

PASS, FAIL, PROGRESS, HUMAN, KEY = "pass", "fail", "in_progress", "human_blocked", "key_required"


def _log(conn, stage: str, status: str, stats: dict) -> None:
    conn.execute("INSERT INTO core.pipeline_run (stage, status, stats, finished_at) VALUES (%s,%s,%s,now())",
                 (stage, status, Jsonb(stats)))


def _latest(conn, stage: str) -> dict | None:
    row = conn.execute("SELECT stats FROM core.pipeline_run WHERE stage=%s AND status='ok' ORDER BY id DESC LIMIT 1",
                       (stage,)).fetchone()
    return row[0] if row else None


# ----------------------------------------------------------------------------- G3 κ

def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def kappa(*, dsn: str, sample_id: str) -> dict:
    """표본의 coder_a·coder_b 코드로 κ, 코드별 일치율(양쪽 중 한 명이라도 그 코드를 준 건 중 둘 다 준 비율), U 비율."""
    with db.connect(dsn) as conn:
        size = conn.execute("SELECT count(*) FROM core.coding_sample WHERE sample_id=%s", (sample_id,)).fetchone()[0]
        if size == 0:
            raise KeyError(f"no coding sample {sample_id}")
        rows = conn.execute(
            """SELECT s.idea_id, a.code, b.code FROM core.coding_sample s
                 LEFT JOIN core.review a ON a.target_type='idea' AND a.target_id=s.idea_id AND a.round='coder_a'
                 LEFT JOIN core.review b ON b.target_type='idea' AND b.target_id=s.idea_id AND b.round='coder_b'
                WHERE s.sample_id=%s""", (sample_id,)).fetchall()
        pairs = [(a, b) for _, a, b in rows if a and b]
        k = cohen_kappa(pairs)
        per_code = {}
        for c in CODES:
            either = sum(1 for a, b in pairs if c in (a, b))
            if either:
                per_code[c] = round(sum(1 for a, b in pairs if a == b == c) / either, 3)
        u_share = round(sum((a == "U") + (b == "U") for a, b in pairs) / (2 * len(pairs)), 3) if pairs else None
        if not pairs:
            status = HUMAN
        elif len(pairs) < size:
            status = PROGRESS
        else:
            status = PASS if k is not None and k >= KAPPA_TARGET and (u_share or 0) <= 0.2 else FAIL
        out = {"sample_id": sample_id, "size": size, "coded_pairs": len(pairs),
               "coded_a": sum(1 for _, a, _ in rows if a), "coded_b": sum(1 for _, _, b in rows if b),
               "kappa": None if k is None else round(k, 3), "per_code_agreement": per_code, "u_share": u_share,
               "target": KAPPA_TARGET, "status": status}
        _log(conn, "kpi-kappa", "ok", out)
        conn.commit()
    return out


# ----------------------------------------------------------------------------- G4 골드셋

def _norm(s: str) -> str:
    return " ".join(s.split())


def goldset(*, dsn: str, gold_csv: str, baseline: bool = False) -> dict:
    """gold_csv: 파일럿 결과 CSV 내용(열 year·item·final). 연도+제목(공백 정규화) 일치로 아이디어를 찾고
    trace_verdict.status와 비교한다. pending은 '판정 전'으로 따로 세고 macro-F1에서 뺀다."""
    gold = list(csv.DictReader(io.StringIO(gold_csv.lstrip("\ufeff"))))
    missing = {"year", "item", "final"} - set(gold[0] if gold else ())
    if missing:
        raise ValueError(f"gold csv lacks columns {sorted(missing)}")
    with db.connect(dsn) as conn:
        ideas: dict[tuple[int, str], list[tuple[str, str | None]]] = {}
        years = sorted({int(g["year"]) for g in gold})
        for iid, y, title, st in conn.execute(
                """SELECT i.id, i.year, i.title, t.status FROM core.idea i
                     LEFT JOIN core.trace_verdict t ON t.idea_id = i.id
                    WHERE i.retired_at IS NULL AND i.year = ANY(%s)""", (years,)):
            ideas.setdefault((y, _norm(title)), []).append((iid, st))
        matched, pending, unmatched = [], 0, 0
        for g in gold:
            if g["final"] not in TRACE_CLASSES:
                raise ValueError(f"gold class {g['final']!r} not in {TRACE_CLASSES}")
            hit = ideas.get((int(g["year"]), _norm(g["item"])))
            if not hit:
                unmatched += 1
                continue
            iid, pred = min(hit)
            if pred is None or pred == "pending":
                pending += 1
                continue
            matched.append((iid, g["final"], pred))
        conf = {g: {p: 0 for p in TRACE_CLASSES} for g in TRACE_CLASSES}
        for _, g, p in matched:
            conf[g][p] += 1
        f1s = {}
        for c in TRACE_CLASSES:
            tp = conf[c][c]
            fp = sum(conf[g][c] for g in TRACE_CLASSES if g != c)
            fn = sum(conf[c][p] for p in TRACE_CLASSES if p != c)
            if tp + fp + fn:
                f1s[c] = round(2 * tp / (2 * tp + fp + fn), 3)
        macro = round(100 * sum(f1s.values()) / len(f1s), 1) if f1s else None
        rp = [x for x in matched if x[1] in ("realized", "pivot")]
        recall_rp = round(sum(1 for _, g, p in rp if p in ("realized", "pivot")) / len(rp), 3) if rp else None
        base = _latest(conn, "kpi-goldset-baseline")
        if not matched:
            status = KEY  # 흔적 외부 검색(NAVER 뉴스·KIPRIS Plus) 키가 없어 판정이 전부 pending
        elif base is None or baseline:
            status = PASS
        else:
            status = PASS if macro is not None and base["macro_f1"] - macro <= GOLD_F1_DROP_PT else FAIL
        out = {"gold_rows": len(gold), "matched_ideas": len(gold) - unmatched, "unmatched": unmatched,
               "pending": pending, "decided": len(matched), "confusion": conf, "f1": f1s, "macro_f1": macro,
               "realized_pivot_recall": recall_rp, "baseline_macro_f1": base["macro_f1"] if base else None,
               "status": status}
        _log(conn, "kpi-goldset", "ok", out)
        if baseline and matched:
            _log(conn, "kpi-goldset-baseline", "ok", out)
        conn.commit()
    return out


# ----------------------------------------------------------------------------- G5 Top 20

def _week(conn, week: date | None) -> date | None:
    return week or conn.execute("SELECT max(week) FROM core.weekly_top").fetchone()[0]


def verify_top20(*, dsn: str, publish_dsn: str, week: date | None = None) -> dict:
    with db.connect(dsn) as conn:
        week = _week(conn, week)
        if week is None:
            return {"week": None, "status": PROGRESS, "detail": "weekly_top 없음"}
        top = {r[0] for r in conn.execute(
            "SELECT idea_id FROM core.weekly_top WHERE week=%s AND rank <= 20", (week,))}
        expert = {r[0] for r in conn.execute(
            """SELECT DISTINCT r.target_id FROM core.review r JOIN core.weekly_top t
                 ON t.idea_id = r.target_id AND t.week = %s AND t.rank <= 20
                WHERE r.round='expert' AND r.target_type='idea' AND r.decision='approve'""", (week,))}
    with db.connect(publish_dsn) as pc:
        pub = {r[0] for r in pc.execute("SELECT idea_id FROM publish.weekly_top WHERE week=%s AND rank <= 20",
                                        (week,))}
    target = min(20, len(top))
    if not expert:
        status = HUMAN
    elif top == expert == pub and len(top) == target and target > 0:
        status = PASS
    else:
        status = FAIL
    return {"week": week, "core_top": len(top), "expert_approved": len(expert), "published": len(pub),
            "target": target, "same_set": top == expert == pub, "missing_expert": sorted(top - expert),
            "status": status}


# ----------------------------------------------------------------------------- G1–G13

def _row(g: str, name: str, status: str, value: str, check: str) -> dict:
    return {"goal": g, "name": name, "status": status, "value": value, "check": check}


def audit_g9(conn) -> dict[str, int]:
    """공개 중(철회 안 됨)인 비-U 진단·바뀐 것 매칭·S 중 근거(x_evidence) 없는 행 수."""
    q = {
        "diagnosis": """SELECT count(*) FROM core.diagnosis d JOIN core.publication p ON p.target_type='idea'
                          AND p.target_id=d.idea_id AND p.scope='diagnosis' AND p.revoked_at IS NULL
                         WHERE d."primary" <> 'U' AND NOT EXISTS (SELECT 1 FROM core.x_evidence x
                           WHERE x.target_type='diagnosis' AND x.target_id=d.idea_id)""",
        "change": """SELECT count(*) FROM core.change_match m JOIN core.publication p ON p.target_type='change_match'
                       AND p.target_id=m.id::text AND p.scope='change' AND p.revoked_at IS NULL
                      WHERE NOT EXISTS (SELECT 1 FROM core.x_evidence x
                        WHERE x.target_type='change_match' AND x.target_id=m.id::text)""",
        "timeliness": """SELECT count(*) FROM core.timeliness t JOIN core.publication p ON p.target_type='idea'
                           AND p.target_id=t.idea_id AND p.scope='timeliness' AND p.revoked_at IS NULL
                          WHERE t.n_scored > (SELECT count(*) FROM core.x_evidence x WHERE x.target_type='timeliness'
                            AND x.target_id = t.idea_id || '@' || t.as_of::text)
                            AND t.as_of = (SELECT max(as_of) FROM core.timeliness t2 WHERE t2.idea_id=t.idea_id)""",
    }
    return {k: conn.execute(v).fetchone()[0] for k, v in q.items()}


def audit_g10(conn, pc) -> dict[str, int]:
    from .egress import NEVER_EXPORT, Policy, host_allowed

    pol = Policy.load(conn)
    calls = conn.execute(
        "SELECT dest_host, source_ids, fields_sent, purpose FROM core.egress_call WHERE decision='allowed'").fetchall()
    off_host = sum(1 for h, *_ in calls if not host_allowed(h))
    bad_field = sum(1 for _, sids, fields, purpose in calls if purpose in ("llm", "trace")
                    for s in sids for f in fields if f in NEVER_EXPORT or pol.check(s, f, purpose))
    # card_kind=full은 허용된 LLM 호출(감사 행)로 만든 카드만. 본문 해시와 전송 해시 대조는 egress가 전송 직전에 한다.
    full_without_llm_call = conn.execute(
        """SELECT count(*) FROM core.idea_card k JOIN core.egress_call e ON e.id = k.egress_call_id
            WHERE k.card_kind='full' AND (e.decision <> 'allowed' OR e.purpose <> 'llm')""").fetchone()[0]
    full_without_llm_call += conn.execute(
        "SELECT count(*) FROM core.idea_card WHERE card_kind='full' AND egress_call_id IS NULL").fetchone()[0]
    allowed_cols = {t: set(columns(t)) for t in (*QUERIES, "evidence")}
    extra_cols = 0
    for t, cols in allowed_cols.items():
        live = {r[0] for r in pc.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='publish' AND table_name=%s", (t,))}
        extra_cols += len(live - cols)
    name_cols = pc.execute(
        """SELECT count(*) FROM information_schema.columns WHERE table_schema='publish'
             AND column_name IN ('team', 'team_name', 'team_kind', 'member', 'members', 'leader',
                                 'person_name', 'contact')""").fetchone()[0]
    return {"off_whitelist_calls": off_host, "forbidden_fields_sent": bad_field, "full_card_without_llm_call": full_without_llm_call,
            "publish_columns_outside_template": extra_cols, "publish_name_columns": name_cols}


def report(*, dsn: str, publish_dsn: str, inbox_dsn: str | None = None, p95_ms: float | None = None,
           week: date | None = None) -> list[dict]:
    rows: list[dict] = []
    with db.connect(dsn) as conn, db.connect(publish_dsn) as pc:
        kinds = dict(conn.execute(
            """SELECT k.card_kind, count(*) FROM core.idea_card k JOIN core.idea i ON i.id=k.idea_id
                WHERE i.retired_at IS NULL GROUP BY 1"""))
        total = sum(kinds.values())
        rows.append(_row("G1", "구조화 카드", PASS if total >= 10_000 else FAIL,
                         f"{total:,} ({', '.join(f'{k} {v:,}' for k, v in sorted(kinds.items()))})", "≥10,000"))

        allowed = conn.execute(
            """SELECT count(*) FROM core.idea i JOIN core.source s ON s.id=i.source_id
                WHERE s.public_ok AND i.retired_at IS NULL AND i.withheld_at IS NULL""").fetchone()[0]
        pub = pc.execute("SELECT count(*) FROM publish.idea").fetchone()[0]
        rows.append(_row("G2", "공개 카드", PASS if pub == allowed and pub > 0 else FAIL,
                         f"publish {pub:,} = core 공개 허용 {allowed:,}", "publish.idea = core public_ok"))

        k = _latest(conn, "kpi-kappa")
        nsample = conn.execute("SELECT count(DISTINCT sample_id) FROM core.coding_sample").fetchone()[0]
        if k:
            rows.append(_row("G3", "원인 분류 κ", k["status"],
                             f"κ={k['kappa']} 코딩 {k['coded_pairs']}/{k['size']} U {k['u_share']}", "κ ≥0.7, U ≤20%"))
        else:
            rows.append(_row("G3", "원인 분류 κ", HUMAN, f"표본 {nsample}개, 코딩 0 (2인 코더 필요)", "κ ≥0.7"))

        g = _latest(conn, "kpi-goldset")
        rows.append(_row("G4", "골드셋 회귀", g["status"] if g else PROGRESS,
                         f"판정 {g['decided']}/{g['matched_ideas']} (pending {g['pending']}), macro-F1 {g['macro_f1']}"
                         if g else "미실행(bluebird eval goldset)", "macro-F1 하락 ≤5pt"))

        week = _week(conn, week)
    t = verify_top20(dsn=dsn, publish_dsn=publish_dsn, week=week)
    rows.append(_row("G5", "재조명 Top 20", t["status"],
                     f"주 {t['week']} Top {t.get('core_top', 0)}, 전문가 승인 {t.get('expert_approved', 0)}, "
                     f"공개 {t.get('published', 0)}", "1–20위 전부 전문가 승인(E3에서 min(20, 후보) 조정)"))

    with db.connect(dsn) as conn, db.connect(publish_dsn) as pc:
        g6 = conn.execute(
            """SELECT count(DISTINCT c.id) FROM core.condition_change c
                 JOIN core.signal_dataset s ON 'dataset:' || s.public_data_pk = c.id
                 JOIN core.change_match m ON m.change_id = c.id AND m.status = 'approved'
                 JOIN core.publication p ON p.target_type='change_match' AND p.target_id=m.id::text
                  AND p.scope='change' AND p.revoked_at IS NULL
                WHERE c.kind='dataset_opened' AND s.tier='observed_new' AND s.rereg_of IS NULL
                  AND s.first_seen_at BETWEEN '2026-10-12' AND '2026-12-07'""").fetchone()[0]
        snaps = conn.execute("SELECT count(*) FROM core.catalog_snapshot WHERE taken_at >= '2026-10-12'").fetchone()[0]
        rows.append(_row("G6", "바뀐 것 데모(신규 개방)", PASS if g6 >= 10 else PROGRESS,
                         f"{g6}건 (창 2026-10-12~12-07, 창 안 스냅샷 {snaps}개)", "≥10 [W4 확정]"))

        demo = pc.execute(
            """SELECT coalesce(max(n), 0) FROM (SELECT count(*) n FROM publish.announcement_match
                GROUP BY announcement_id) x""").fetchone()[0]
        ks = conn.execute(
            """SELECT status FROM core.source_check WHERE source_id='kstartup_announcement_15125364'
                ORDER BY checked_at DESC LIMIT 1""").fetchone()
        g7 = PASS if demo >= 3 else (KEY if ks and ks[0] == KEY else PROGRESS)
        rows.append(_row("G7", "공고 매칭 데모", g7, f"공고 1건당 최대 승인 매칭 {demo}", "≥3 (K-Startup 공고)"))

        rows.append(_row("G8", "검색 속도(pg_trgm)", PROGRESS if p95_ms is None else (PASS if p95_ms < 300 else FAIL),
                         "미측정(deploy/test/p95.sh)" if p95_ms is None else f"p95 {p95_ms}ms", "p95 < 300ms"))

        a9 = audit_g9(conn)
        rows.append(_row("G9", "근거 무결성", PASS if not any(a9.values()) else FAIL,
                         ", ".join(f"{k} {v}" for k, v in a9.items()), "근거 없는 공개 행 0"))

        a10 = audit_g10(conn, pc)
        rows.append(_row("G10", "반출 통제", PASS if not any(a10.values()) else FAIL,
                         ", ".join(f"{k} {v}" for k, v in a10.items()), "전부 0 (+ test_no_direct_http)"))

        ob = conn.execute(
            """SELECT count(*) FILTER (WHERE pulled_at IS NOT NULL), count(*) FILTER (WHERE resolved_at IS NOT NULL)
                 FROM core.objection""").fetchone()
        inbox = None
        if inbox_dsn:
            with db.connect(inbox_dsn) as ic:
                inbox = ic.execute("SELECT count(*) FROM inbox.objection").fetchone()[0]
        g11 = PASS if ob[1] >= 1 and inbox == 0 else (PROGRESS if inbox is None or ob[1] == 0 else FAIL)
        rows.append(_row("G11", "이의 제기", g11, f"가져옴 {ob[0]}, 처리 {ob[1]}, DMZ 남은 {inbox}",
                         "제출→pull→DMZ 삭제→처리→반영 ≥1"))

        audit = conn.execute(
            """SELECT count(*), count(*) FILTER (WHERE decision='approve') FROM core.review
                WHERE target_type='change_match' AND round='audit'""").fetchone()
        judged = conn.execute(
            """SELECT count(*) FILTER (WHERE status='approved'), count(*) FILTER (WHERE status IN ('approved','rejected'))
                 FROM core.change_match""").fetchone()
        rate = f"{judged[0]}/{judged[1]}" if judged[1] else "0/0"
        g12 = HUMAN if audit[0] < 20 else (PASS if audit[1] >= 16 else FAIL)
        rows.append(_row("G12", "바뀐 것 정밀도", g12, f"맹검 {audit[1]}/{audit[0]}, 승인율 {rate}", "무작위 20건 중 ≥16"))

        tiers = {r.id: r.tier for r in REMOTES}
        latest = conn.execute(
            """SELECT DISTINCT ON (source_id) source_id, status FROM core.source_check
                ORDER BY source_id, checked_at DESC""").fetchall()
        must = [(s, st) for s, st in latest if tiers.get(s, "must") == "must" and st != "blocked"]
        bad = [s for s, st in must if st == "error"]
        waiting = [s for s, st in must if st == KEY]
        rows.append(_row("G13", "소스 점검", FAIL if bad else PASS,
                         f"must {len(must)}: ok {sum(st == 'ok' for _, st in must)}, 키 대기 {len(waiting)}"
                         + (f", 실패 {','.join(bad)}" if bad else ""), "must 중 키 없는 것 전부 ok, error 0"))
        _log(conn, "kpi-report", "ok", {"rows": rows})
        conn.commit()
    return rows


def print_report(rows: list[dict]) -> None:
    print(f"{'목표':5} {'항목':18} {'상태':14} 값  [기준]")
    for r in rows:
        print(f"{r['goal']:5} {r['name']:18} {r['status']:14} {r['value']}  [{r['check']}]")
    c = Counter(r["status"] for r in rows)
    print("요약: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, indent=1)
