"""master LLM 컬럼 채우기: keyword·problem·feature·target·domain, 빈 contest.

- 소스 단위 묶음(기본 10행) 1회 호출. 내용 = egress fields(소스별 반출 검사·감사), 지시문 = 코드 고정
- 소스 맥락(레지스트리 이름·주제·주관·대회/제도명) = 본문이 짧거나 없는 행의 단서
- 근거 없는 problem·feature·target = null(지어내지 않음). contest = 원본 값 유지, 빈 행만 채움
- 재실행 = keyword 빈 행만. 429·5xx = 대기 후 재시도
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

from . import db, llm
from .egress import Egress, EgressBlocked, EgressTransportError

DOMAINS = ("행정", "복지", "교통", "환경", "경제", "교육", "안전", "문화", "보건", "과학기술", "기타")
BODY_LIMIT = 2500   # 행당 본문 앞부분(토큰 상한)

SYSTEM = (
    "너는 한국 공공 아이디어·제안 데이터를 정리하는 분류기다. 입력의 각 항목에 대해 근거가 입력 안에 있는 내용만 쓴다. "
    "추측·창작 금지. 반드시 JSON 객체 하나만 출력한다."
)
INSTRUCTION = (
    "<category>는 이 항목들이 나온 데이터 소스 정보(소스명·주제·주관기관·대회/제도명)다. <body>는 항목 배열(id, title, body, contest)이다.\n"
    "항목마다 다음을 만든다.\n"
    "- keyword: 내용을 대표하는 한국어 명사 키워드 2~3개(배열)\n"
    "- problem: 해결하려는 문제 한 문장. 제목·본문에 근거가 없으면 null\n"
    "- feature: 제안의 핵심 기능·방법 한 문장. 근거가 없으면 null\n"
    "- target: 주된 대상(수혜·사용자) 짧은 명사구. 근거가 없으면 null\n"
    f"- domain: 다음 중 해당하는 것 1개 이상(배열): {', '.join(DOMAINS)}\n"
    "- contest: 입력 contest가 있으면 그대로. 없으면 본문에 나온 공모전·대회명, 그것도 없으면 소스 정보의 대회/제도명. "
    "어디에도 없으면 null. 이름을 지어내지 않는다\n"
    '출력 형식: {"items": [{"id": ..., "keyword": [...], "problem": ..., "feature": ..., "target": ..., '
    '"domain": [...], "contest": ...}]} — 입력 항목 수와 id를 그대로 맞춘다.'
)


def _context(spec: dict) -> str:
    parts = [("소스명", spec.get("name")), ("주제", spec.get("topic")), ("주관기관", spec.get("host_org")),
             ("대회/제도명", spec.get("contest_name"))]
    return "\n".join(f"{k}: {v}" for k, v in parts if v)


def _text(value) -> str | None:
    text = " ".join(str(value).split()) if isinstance(value, str) else ""
    return text or None


def parse(items: list[dict], rows: list[tuple]) -> list[tuple]:
    """LLM 응답 → UPDATE 값. 형식이 어긋난 항목 = 버림(다음 실행에서 다시)."""
    by_id = {str(item.get("id")): item for item in items if isinstance(item, dict)}
    out = []
    for i, (api, key, *_rest) in enumerate(rows):
        item = by_id.get(str(i))
        if item is None:
            continue
        keyword = [k for k in (_text(x) for x in item.get("keyword") or []) if k][:3]
        # 목록 밖·빈 domain(제목만 있는 행에서 나옴) = 기타
        domain = [d for d in dict.fromkeys(item.get("domain") or []) if d in DOMAINS] or ["기타"]
        if not keyword:
            continue
        out.append((keyword, _text(item.get("problem")), _text(item.get("feature")), _text(item.get("target")),
                    domain, _text(item.get("contest")), api, key))
    return out


def _call(eg: Egress, p: llm.Provider, source: str, spec: dict, rows: list[tuple]) -> list[dict]:
    batch = [{"id": i, "title": title, "body": (body or "")[:BODY_LIMIT] or None, "contest": contest}
             for i, (_api, _key, title, body, contest) in enumerate(rows)]
    fields = {"category": (source, _context(spec)), "body": (source, batch)}
    for wait in (5, 20, 60, 180, None):
        try:
            data, _ = llm.ask_json(eg, p, system=SYSTEM, instruction=INSTRUCTION, fields=fields,
                                   max_tokens=350 * len(rows) + 200)
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


def fill(*, dsn: str, egress: Egress, sources: list[dict], only: str | None = None, skip: list[str] = (),
         sample: int | None = None, batch: int = 10, workers: int = 8) -> list[dict]:
    p = llm.provider()
    if p is None:
        raise RuntimeError("no LLM key (OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    specs = {s["id"]: s for s in sources}
    with db.connect(dsn) as conn:
        todo = conn.execute(
            "SELECT api, key, title, body, contest FROM ("
            " SELECT api, key, title, body, contest, row_number() OVER (PARTITION BY api ORDER BY md5(key)) rn"
            " FROM master WHERE keyword IS NULL AND (%(only)s::text IS NULL OR api = %(only)s)"
            " AND NOT api = ANY(%(skip)s)) t"
            " WHERE %(sample)s::int IS NULL OR rn <= %(sample)s ORDER BY api, rn",
            {"only": only, "skip": list(skip), "sample": sample}).fetchall()
    jobs: list[tuple[str, list[tuple]]] = []
    for row in todo:
        if jobs and jobs[-1][0] == row[0] and len(jobs[-1][1]) < batch:
            jobs[-1][1].append(row)
        else:
            jobs.append((row[0], [row]))

    def run(job: tuple[str, list[tuple]]) -> list[tuple]:
        source, rows = job
        return parse(_call(egress, p, source, specs.get(source, {}), rows), rows)

    filled: dict[str, int] = {}
    with db.connect(dsn) as conn, ThreadPoolExecutor(workers) as pool:
        for n, values in enumerate(pool.map(run, jobs), start=1):
            with conn.cursor() as cur:
                cur.executemany(
                    # 본문 없는 행 = 근거 없음 → 문제·기능·대상 저장 안 함(refine과 같은 규칙)
                    "UPDATE master SET keyword = %s,"
                    " problem = CASE WHEN coalesce(body, '') = '' THEN NULL ELSE %s END,"
                    " feature = CASE WHEN coalesce(body, '') = '' THEN NULL ELSE %s END,"
                    " target = CASE WHEN coalesce(body, '') = '' THEN NULL ELSE %s END, domain = %s,"
                    " contest = coalesce(contest, %s), origin = CASE WHEN contest IS NOT NULL THEN origin"
                    " WHEN %s::text IS NOT NULL THEN 'X' END WHERE api = %s AND key = %s",
                    [(*v[:6], v[5], *v[6:]) for v in values])
            for v in values:
                filled[v[6]] = filled.get(v[6], 0) + 1
            if n % 20 == 0:
                conn.commit()
        conn.commit()
    return [{"source": s, "status": "ok", "rows": sum(r[0] == s for r in todo), "filled": filled.get(s, 0)}
            for s in sorted({r[0] for r in todo})]
