"""아이디어 판정 + 가공(LLM 1회): quality.idea_label + idea_fields(목표·해결책·핵심기능·도메인).

- 대상: 쓸 행(exclude_reasons = '{}') 중 판정 전(quality.idea_label NULL)
- 소스 단위 10행 묶음 1회 호출. 내용 = egress fields(반출 검사·감사), 지시문 = 코드 고정
- 본문 [라벨]은 힌트(목표 쪽·해결책 쪽)로만. 출력은 쓸 수 있게 다시 쓴 문장
- 검증: evidence가 제목·본문에 그대로 있어야 verified. idea 아닌 행 = 판정만 저장
- 다음 단계: bluebird master reasons (idea_label → exclude_reasons)
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import db, llm
from .egress import Egress, EgressBlocked, EgressTransportError

PROMPT_VERSION = "extract-v2"
LABELS = ("idea", "idea_thin", "complaint", "abusive", "off_topic")
TYPES = ("product", "research", "policy")
DOMAINS = ("행정", "복지", "교통", "환경", "경제", "교육", "안전", "문화", "보건", "과학기술", "생활", "기타")
BODY_LIMIT = 2500

SYSTEM = ("너는 한국 공모전·시민 제안 데이터를 쓸 수 있게 가공하는 편집자다. 입력에 근거가 있는 내용만 쓴다. "
          "반드시 JSON 객체 하나만 출력한다.")
INSTRUCTION = (
    "<category>는 소스 정보, <body>는 항목 배열(id, title, body, contest)이다. body의 [제안취지]·[발명동기] 같은 라벨은 "
    "목표 쪽, [사업내용]·[발명내용] 같은 라벨은 해결책 쪽이라는 힌트다.\n"
    "항목마다:\n"
    "- label: idea(문제·목표와 방법이 있음) / idea_thin(아이디어는 있으나 너무 짧아 목표·방법을 못 뽑음) / "
    "complaint(제안 없이 불만·항의) / abusive(욕설·비방 중심) / off_topic(광고·홍보·무의미)\n"
    "label이 idea일 때만 아래를 채운다(아니면 생략):\n"
    "- type: product(발명·제품·디자인·서비스) / research(과학 탐구·실험) / policy(정책·사업·시민 제안)\n"
    "- goal: 한 문장. product·policy = 해결하려는 문제, research = 알아내려는 것\n"
    "- solution: 한 문장. product·policy = 만든 것·방법, research = 탐구 방법과 알아낸 결과\n"
    "- features: 핵심 기능 0~3개(짧은 명사구 배열). research는 만든 장치·앱이 있을 때만\n"
    f"- domain: 1~2개(배열): {', '.join(DOMAINS)}. 생활 = 생활용품·가사·위생\n"
    "- evidence: solution의 근거인 body(없으면 title)의 한 문장 안에서 이어진 구절 하나를 글자 하나 바꾸지 않고 복사"
    "(10~40자). 여러 곳을 잇거나 줄이거나 '...'을 넣지 않는다\n"
    '출력: {"items": [{"id": ..., "label": ..., "type": ..., "goal": ..., "solution": ..., "features": [...], '
    '"domain": [...], "evidence": ...}]} — 입력 항목 수·id 그대로.'
)


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "")


def _text(value) -> str | None:
    return " ".join(value.split()) or None if isinstance(value, str) else None


def parse(items: list[dict], rows: list[tuple], model: str) -> tuple[list[tuple], list[tuple]]:
    """응답 → (quality 판정 행, idea_fields 행). 형식 어긋난 항목 = 버림(다음 실행에서 다시)."""
    by_id = {str(i.get("id")): i for i in items if isinstance(i, dict)}
    labels, fields = [], []
    for n, (api, key, title, body, _contest) in enumerate(rows):
        item = by_id.get(str(n))
        label = item and item.get("label")
        if label not in LABELS:
            continue
        labels.append((label, model, api, key))
        if label != "idea":
            continue
        kind = item.get("type") if item.get("type") in TYPES else None
        domain = [d for d in dict.fromkeys(item.get("domain") or []) if d in DOMAINS][:2] or ["기타"]
        evidence = _text(item.get("evidence"))
        if kind is None:
            labels.pop()   # 유형 없는 idea = 형식 오류 → 다음 실행에서 다시
            continue
        fields.append((api, key, kind, _text(item.get("goal")), _text(item.get("solution")),
                       [f for f in (_text(x) for x in item.get("features") or []) if f][:3], domain, evidence,
                       bool(evidence) and _norm(evidence) in _norm(f"{title} {body}"), model, PROMPT_VERSION))
    return labels, fields


def _context(spec: dict) -> str:
    parts = [("소스명", spec.get("name")), ("주제", spec.get("topic")), ("주관기관", spec.get("host_org"))]
    return "\n".join(f"{k}: {v}" for k, v in parts if v)


def _call(eg: Egress, p: llm.Provider, source: str, spec: dict, rows: list[tuple]) -> list[dict]:
    batch = [{"id": i, "title": t, "body": (b or "")[:BODY_LIMIT], "contest": c}
             for i, (_a, _k, t, b, c) in enumerate(rows)]
    fields = {"category": (source, _context(spec)), "body": (source, batch)}
    for wait in (5, 20, 60, 180, None):
        try:
            data, _ = llm.ask_json(eg, p, system=SYSTEM, instruction=INSTRUCTION, fields=fields,
                                   max_tokens=300 * len(rows) + 200)
            return data.get("items") or []
        except (EgressTransportError, json.JSONDecodeError, ValueError):
            pass
        except EgressBlocked as exc:
            if not any(code in str(exc) for code in ("HTTP 429", "HTTP 5")):
                raise
        if wait is None:
            return []
        time.sleep(wait)
    return []


def extract(*, dsn: str, egress: Egress, sources: list[dict], only: str | None = None, sample: int | None = None,
            batch: int = 10, workers: int = 8) -> list[dict]:
    p = llm.provider()
    if p is None:
        raise RuntimeError("no LLM key (OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    specs = {s["id"]: s for s in sources}
    with db.connect(dsn) as conn:
        todo = conn.execute(
            "SELECT api, key, title, body, contest FROM ("
            " SELECT m.api, m.key, m.title, m.body, coalesce(pg.name, m.contest) contest,"
            "  row_number() OVER (PARTITION BY m.api ORDER BY md5(m.key)) rn"
            " FROM master m JOIN quality q USING (api, key) LEFT JOIN program pg ON pg.id = m.program_id"
            " WHERE m.exclude_reasons = '{}' AND q.idea_label IS NULL"
            " AND (%(only)s::text IS NULL OR m.api = %(only)s)) t"
            " WHERE %(sample)s::int IS NULL OR rn <= %(sample)s ORDER BY api, rn",
            {"only": only, "sample": sample}).fetchall()
    jobs: list[tuple[str, list[tuple]]] = []
    for row in todo:
        if jobs and jobs[-1][0] == row[0] and len(jobs[-1][1]) < batch:
            jobs[-1][1].append(row)
        else:
            jobs.append((row[0], [row]))

    def run(job):
        source, rows = job
        return parse(_call(egress, p, source, specs.get(source, {}), rows), rows, p.model)

    done: dict[str, dict[str, int]] = {}
    with db.connect(dsn) as conn, ThreadPoolExecutor(workers) as pool:
        for n, ((source, _rows), (labels, fields)) in enumerate(zip(jobs, pool.map(run, jobs), strict=True), 1):
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO idea_fields (api, key, item_type, goal, solution, features, domain,"
                                " evidence, verified, model, prompt_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                                " ON CONFLICT (api, key) DO UPDATE SET item_type = EXCLUDED.item_type,"
                                " goal = EXCLUDED.goal, solution = EXCLUDED.solution, features = EXCLUDED.features,"
                                " domain = EXCLUDED.domain, evidence = EXCLUDED.evidence, verified = EXCLUDED.verified,"
                                " model = EXCLUDED.model, prompt_version = EXCLUDED.prompt_version, at = now()", fields)
                cur.executemany("UPDATE quality SET idea_label = %s, idea_model = %s, idea_at = now()"
                                " WHERE api = %s AND key = %s", labels)
            stat = done.setdefault(source, {"rows": 0, "judged": 0, "idea": 0, "verified": 0})
            stat["rows"] += len(_rows)
            stat["judged"] += len(labels)
            stat["idea"] += len(fields)
            stat["verified"] += sum(f[8] for f in fields)
            if n % 20 == 0:
                conn.commit()
        conn.commit()
    return [{"source": s, "status": "ok", **v} for s, v in sorted(done.items())] or [{"status": "ok", "rows": 0}]
