"""KPI 검증 도구(계획 §5 G1–G13 중 원본 DB로 잴 수 있는 것).

- kappa: κ 표본(2인 독립 코딩) 일치도. 코딩 없음 → human_blocked
- goldset: 파일럿 골드셋(흔적 5클래스) vs 흔적 판정, 혼동행렬·macro-F1. CSV에 팀명 있음 → 실행 시 읽기만, 저장 없음(연도·제목 매칭 id·클래스만 기록)
- report: G1·G3·G4·G9·G10·G12·G13 현황표. 사람 입력 대기 → human_blocked, 키 없음 → key_required
"""

from __future__ import annotations

import csv
import io
from collections import Counter

from psycopg.types.json import Jsonb

from . import db
from .signals.catalog import KST
from .sources import ADAPTERS, load_sources
from .sources_check import BLOCKED, REMOTES

CODES = ("T", "D", "R", "M", "C", "O", "U")
TRACE_CLASSES = ("realized", "pivot", "similar_unlinked", "award_only", "none")
KAPPA_TARGET = 0.7
KAPPA_MIN_SAMPLE = 100  # 기획서 약속: 100건 2인 독립 코딩(30건 파일럿 = 미통과)
GOLD_F1_DROP_PT = 5.0
GOLD_MIN_DECIDED = 0.8  # 회귀 비교 최소 판정 비율

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
        elif len(pairs) < size or size < KAPPA_MIN_SAMPLE:
            status = PROGRESS  # 코딩이 덜 됐거나 파일럿 표본(100건 미만)
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
    """gold_csv = 파일럿 결과 CSV(열 year·item·final). 연도+제목(공백 정규화) 매칭 → trace_verdict.status 비교.
    pending = '판정 전' 별도 집계, macro-F1 제외."""
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
        base = None if baseline else _latest(conn, "kpi-goldset-baseline")
        matched_n = len(gold) - unmatched
        keys_waiting = conn.execute(
            """SELECT count(*) FROM (SELECT DISTINCT ON (source_id) status FROM core.source_check
                WHERE source_id IN ('naver_search_news', 'kipris_plus_patent')
                ORDER BY source_id, checked_at DESC) x WHERE status = 'key_required'""").fetchone()[0]
        if not matched_n or len(matched) < GOLD_MIN_DECIDED * matched_n:
            # 판정 건수 부족 → 비교 안 함. 흔적 검색 키 부재 → key_required
            status = KEY if keys_waiting else PROGRESS
        elif baseline:
            status = PASS  # 이번 실행이 기준선(W4 첫 무팀명 실행)
        elif base is None:
            status = PROGRESS  # 기준선 없음 → 회귀 판단 불가
        else:
            status = PASS if base["macro_f1"] - macro <= GOLD_F1_DROP_PT else FAIL
        out = {"gold_rows": len(gold), "matched_ideas": len(gold) - unmatched, "unmatched": unmatched,
               "pending": pending, "decided": len(matched), "confusion": conf, "f1": f1s, "macro_f1": macro,
               "realized_pivot_recall": recall_rp, "baseline_macro_f1": base["macro_f1"] if base else None,
               "baseline_run": baseline, "status": status}
        _log(conn, "kpi-goldset", "ok", out)
        if baseline and status == PASS:
            _log(conn, "kpi-goldset-baseline", "ok", out)
        conn.commit()
    return out


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


def name_leaks(conn, *, config, seed_dir, secret: bytes) -> dict[str, int]:
    """G10 성명 일치: 원본 파일 팀명·수상자·지도교사 이름을 메모리에서만 재독 → 원본 DB 글(제목·본문·카드 문제·해결)
    잔존 집계. 공개 허용 소스, 유효·보류 아님 대상. 이름 저장·출력 없음, 개수만 반환."""
    from .anonymize import find_name

    names: dict[str, list[str]] = {}
    files = missing = 0
    for spec in load_sources(config, seed_dir):
        if not spec.public_ok:
            continue
        if not spec.path.exists():
            missing += 1  # 공개 소스 원본이 없으면 대조를 못 한 것이다(G10 통과 아님)
            continue
        for _ in ADAPTERS[spec.adapter](spec, secret, names):
            pass
        files += 1
    hits = compared = 0
    for iid, title, body, problem, solution in conn.execute(
            """SELECT i.id, i.title, i.body, k.problem, k.solution FROM core.idea i
                 LEFT JOIN core.idea_card k ON k.idea_id = i.id
                WHERE i.id = ANY(%s) AND i.retired_at IS NULL AND i.withheld_at IS NULL""", (list(names),)):
        compared += 1
        if any(find_name(t, names[iid]) for t in (title, body, problem, solution)):
            hits += 1
    return {"name_matches": hits, "compared": compared, "ideas_with_names": len(names),
            "source_files": files, "missing_files": missing}


def names_checked(names: dict[str, int] | None) -> bool:
    """이름 대조 실제 수행 여부: 공개 소스 파일 전부 존재 + 대조 1건 이상(익명화 키가 다르면 ID가 안 맞아 0건)."""
    return bool(names) and names["missing_files"] == 0 and names["source_files"] > 0 and (
        names["ideas_with_names"] == 0 or names["compared"] > 0)


def audit_g10(conn, *, names: dict[str, int] | None) -> dict[str, int | None]:
    """names = name_leaks() 결과. 원본 파일·익명화 키가 없어 이름 대조를 못 하면 None(→ G10 진행 중)."""
    from .egress import NEVER_EXPORT, RETIRED_HOSTS, Policy, host_allowed

    pol = Policy.load(conn)
    calls = conn.execute(
        "SELECT dest_host, source_ids, fields_sent, purpose FROM core.egress_call WHERE decision='allowed'").fetchall()
    off_host = sum(1 for h, *_ in calls if not host_allowed(h) and h not in RETIRED_HOSTS)
    bad_field = sum(1 for _, sids, fields, purpose in calls if purpose in ("llm", "trace")
                    for s in sids for f in fields if f in NEVER_EXPORT or pol.check(s, f, purpose))
    # card_kind=full = 허용된 LLM 호출(감사 행) 카드만. 본문 해시·전송 해시 대조 = egress 전송 직전
    full_without_llm_call = conn.execute(
        """SELECT count(*) FROM core.idea_card k JOIN core.egress_call e ON e.id = k.egress_call_id
            WHERE k.card_kind='full' AND (e.decision <> 'allowed' OR e.purpose <> 'llm')""").fetchone()[0]
    full_without_llm_call += conn.execute(
        "SELECT count(*) FROM core.idea_card WHERE card_kind='full' AND egress_call_id IS NULL").fetchone()[0]
    return {"off_whitelist_calls": off_host, "forbidden_fields_sent": bad_field,
            "full_card_without_llm_call": full_without_llm_call,
            "name_matches": names["name_matches"] if names_checked(names) else None}


def report(*, dsn: str, kappa_sample: str | None = None, names: dict[str, int] | None = None) -> list[dict]:
    """names = name_leaks() 결과(없으면 G10 이름 대조 미실행 → 진행 중). kappa_sample = G3 기준 표본 id."""
    rows: list[dict] = []
    with db.connect(dsn) as conn:
        kinds = dict(conn.execute(
            """SELECT k.card_kind, count(*) FROM core.idea_card k JOIN core.idea i ON i.id=k.idea_id
                WHERE i.retired_at IS NULL GROUP BY 1"""))
        total = sum(kinds.values())
        no_card = conn.execute(
            """SELECT count(*) FROM core.idea i WHERE i.retired_at IS NULL
                AND NOT EXISTS (SELECT 1 FROM core.idea_card k WHERE k.idea_id = i.id)""").fetchone()[0]
        rows.append(_row("G1", "구조화 카드", PASS if total >= 10_000 and no_card == 0 else FAIL,
                         f"{total:,} ({', '.join(f'{k} {v:,}' for k, v in sorted(kinds.items()))}), 카드 없음 {no_card}",
                         "≥10,000, 살아 있는 아이디어 전부 카드"))
        # G3: 기준 표본(지정 또는 100건 이상 중 가장 최근)을 지금 코딩으로 다시 계산한다(지난 실행 기록이 아니라).
        sid = kappa_sample or (conn.execute(
            """SELECT sample_id FROM core.coding_sample GROUP BY sample_id HAVING count(*) >= %s
                ORDER BY max(created_at) DESC LIMIT 1""", (KAPPA_MIN_SAMPLE,)).fetchone() or [None])[0]
    k = None
    if sid:
        try:
            k = kappa(dsn=dsn, sample_id=sid)
        except KeyError:
            rows.append(_row("G3", "원인 분류 κ", HUMAN, f"표본 {sid} 없음(bluebird kappa로 생성)",
                             f"표본 ≥{KAPPA_MIN_SAMPLE}, κ ≥{KAPPA_TARGET}"))
    if k:
        rows.append(_row("G3", "원인 분류 κ", k["status"],
                         f"표본 {sid}: κ={k['kappa']} 코딩 {k['coded_pairs']}/{k['size']} U {k['u_share']}",
                         f"표본 ≥{KAPPA_MIN_SAMPLE}, κ ≥{KAPPA_TARGET}, U ≤20%"))
    elif not sid:
        rows.append(_row("G3", "원인 분류 κ", HUMAN, f"{KAPPA_MIN_SAMPLE}건 표본 없음(bluebird kappa로 생성)",
                         f"표본 ≥{KAPPA_MIN_SAMPLE}, κ ≥{KAPPA_TARGET}"))

    with db.connect(dsn) as conn:
        # G4: 골드셋 CSV에 팀명이 있어 리포트 때 다시 돌리지 않고 마지막 실행을 보여 준다(실행 시각 표시).
        # 기준선 설정 실행 = 비교 아님 → 미통과
        g4 = conn.execute("""SELECT stats, finished_at FROM core.pipeline_run WHERE stage='kpi-goldset' AND status='ok'
                              ORDER BY id DESC LIMIT 1""").fetchone()
        if g4:
            g, at = g4
            st = g["status"] if g["status"] != PASS or g.get("baseline_run") is False else PROGRESS
            rows.append(_row("G4", "골드셋 회귀", st,
                             f"판정 {g['decided']}/{g['matched_ideas']} (pending {g['pending']}), macro-F1 {g['macro_f1']}"
                             f", 기준선 {g['baseline_macro_f1']}{' (이번이 기준선)' if g.get('baseline_run') else ''}"
                             f", 실행 {at.astimezone(KST):%Y-%m-%d %H:%M} KST", "기준선 대비 macro-F1 하락 ≤5pt"))
        else:
            rows.append(_row("G4", "골드셋 회귀", PROGRESS, "미실행(bluebird eval goldset)", "기준선 대비 macro-F1 하락 ≤5pt"))

        a9 = audit_g9(conn)
        rows.append(_row("G9", "근거 무결성", PASS if not any(a9.values()) else FAIL,
                         ", ".join(f"{k} {v}" for k, v in a9.items()), "근거 없는 공개 행 0"))

        a10 = audit_g10(conn, names=names)
        g10 = FAIL if any(a10.values()) else (PROGRESS if a10["name_matches"] is None else PASS)
        rows.append(_row("G10", "반출 통제", g10, ", ".join(f"{k} {v}" for k, v in a10.items())
                         + ("" if names is None else
                            f" (이름 대조 {names['compared']:,}건(보류·퇴역 제외), 원본 파일 "
                            f"{names['source_files']}, 없음 {names['missing_files']})"),
                         "전부 0, 성명 일치 0"))

        audit = conn.execute(
            """SELECT count(*), count(*) FILTER (WHERE decision='approve') FROM core.review
                WHERE target_type='change_match' AND round='audit'""").fetchone()
        judged = conn.execute(
            """SELECT count(*) FILTER (WHERE status='approved'), count(*) FILTER (WHERE status IN ('approved','rejected'))
                 FROM core.change_match""").fetchone()
        rate = f"{judged[0]}/{judged[1]}" if judged[1] else "0/0"
        g12 = HUMAN if audit[0] < 20 else (PASS if audit[1] >= 16 else FAIL)
        rows.append(_row("G12", "바뀐 것 정밀도", g12, f"맹검 {audit[1]}/{audit[0]}, 승인율 {rate}", "무작위 20건 중 ≥16"))

        # G13: 범위 밖(BLOCKED 목록)만 빼고, must 소스가 막히거나(blocked) 실패하면 FAIL. 점검 기록이 없는 must 원격은 미실행.
        out_of_scope = {sid for sid, *_ in BLOCKED}
        tiers = {r.id: r.tier for r in REMOTES}
        latest = dict(conn.execute(
            """SELECT DISTINCT ON (source_id) source_id, status FROM core.source_check
                ORDER BY source_id, checked_at DESC""").fetchall())
        must = {s: st for s, st in latest.items() if s not in out_of_scope and tiers.get(s, "must") == "must"}
        bad = sorted(s for s, st in must.items() if st in ("error", "blocked"))
        waiting = sorted(s for s, st in must.items() if st == KEY)
        never = sorted(r.id for r in REMOTES if r.tier == "must" and r.id not in latest)
        g13 = FAIL if bad else (PROGRESS if never else PASS)
        rows.append(_row("G13", "소스 점검", g13,
                         f"must {len(must)}: ok {sum(st == 'ok' for st in must.values())}, 키 대기 {len(waiting)}"
                         + (f", 실패 {','.join(bad)}" if bad else "") + (f", 미점검 {','.join(never)}" if never else ""),
                         "must 중 키 없는 것 전부 ok, error·blocked 0 (키 대기는 도착 주에 통과)"))
        _log(conn, "kpi-report", "ok", {"rows": rows})
        conn.commit()
    return rows


def print_report(rows: list[dict]) -> None:
    print(f"{'목표':5} {'항목':18} {'상태':14} 값  [기준]")
    for r in rows:
        print(f"{r['goal']:5} {r['name']:18} {r['status']:14} {r['value']}  [{r['check']}]")
    c = Counter(r["status"] for r in rows)
    print("요약: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))
