"""아이디어 카드(P1) 생성 — 계획 §3.6.

card_kind는 "무엇을 받아 만들었나"로 정한다.
- full          : 반출 허용(export_grade=O) 소스의 본문으로 만든 카드(LLM 키가 있으면 P1 LLM, 없으면 규칙 추출).
- local_extract : 본문은 있지만 반출이 허용되지 않은 소스(KIPRIS 약관 대기). 업무망 안 규칙 추출만.
- title_only    : 본문이 없는 소스(제목·활용 데이터만).
missing_data는 본문이 스스로 밝힌 부족·미개방 데이터 문장만 담는다(D 원인·D 신호의 아이디어 쪽 키).
경진대회 "활용 데이터"(used_data)는 이미 쓴 데이터라 missing_data가 아니다.
"""

from __future__ import annotations

import re

from psycopg.types.json import Jsonb

from . import db

RULE_VERSION = "rule-v1"

_SENT = re.compile(r"(?<=[.!?。])\s+|\n+")
_PROBLEM = re.compile(r"문제|어려|어렵|불편|부족|한계|없어|없다|없는|못하|위험|낭비|사각지대|불만|애로")
_SOLUTION = re.compile(r"서비스|플랫폼|시스템|앱|어플|제공|개발|활용|해결|지원|솔루션|장치")
# "~데이터(가|는) 없/부족/미개방/비공개/공개되지 않/구하기 어렵" 류. 본문에 실제 있는 문장만 잡는다.
_MISSING = re.compile(
    r"([가-힣A-Za-z0-9·\s]{2,30}?)\s*(데이터|정보|자료|통계|DB)\s*(?:가|는|이|도)?\s*"
    r"(없|부족|미개방|비공개|공개되지\s*않|개방되지\s*않|구하기\s*어렵|확보(?:가|하기)?\s*어렵|제공되지\s*않|부재)"
)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if s and len(s.strip()) >= 4]


def extract_missing_data(body: str) -> list[dict]:
    out, seen = [], set()
    for m in _MISSING.finditer(body or ""):
        name = (m.group(1).strip() + " " + m.group(2)).strip()
        name = re.sub(r"\s+", " ", name)
        if name in seen:
            continue
        seen.add(name)
        start = max(0, body.rfind(".", 0, m.start()) + 1)
        end = body.find(".", m.end())
        end = len(body) if end < 0 else end + 1
        out.append({"name": name, "excerpt": body[start:end].strip()[:300], "char_span": [m.start(), m.end()],
                    "origin": "body"})
    return out


def rule_card(idea: dict) -> dict:
    body = idea["body"] or ""
    sents = sentences(body)
    problem = next((s for s in sents if _PROBLEM.search(s)), None)
    solution = next((s for s in sents if _SOLUTION.search(s) and s != problem), None)
    if solution is None and sents:
        solution = sents[0] if sents[0] != problem else None
    return {
        "problem": problem[:500] if problem else None,
        "solution": solution[:500] if solution else None,
        "missing_data": extract_missing_data(body),
    }


def card_kind(has_body: bool, export_grade: str) -> str:
    if not has_body:
        return "title_only"
    return "full" if export_grade == "O" else "local_extract"


def build(*, dsn: str, rebuild: bool = False) -> dict:
    """규칙 추출로 카드를 만든다(extractor=rule). LLM P1은 diagnose 단계에서 egress로 덮어쓴다."""
    with db.pipeline_run(dsn, "cards") as stats, db.connect(dsn) as conn:
        cur = conn.execute(
            f"""SELECT i.id, i.title, i.body, i.used_data, i.category, i.year, i.source_url, s.export_grade
                  FROM core.idea i JOIN core.source s ON s.id = i.source_id
                  LEFT JOIN core.idea_card k ON k.idea_id = i.id
                 WHERE {"true" if rebuild else "k.idea_id IS NULL OR (k.extractor = 'rule' AND k.updated_at < i.updated_at)"}
                 ORDER BY i.id"""
        )
        cols = [d.name for d in cur.description]
        n = 0
        with conn.cursor() as w:
            for row in cur.fetchall():
                idea = dict(zip(cols, row))
                has_body = bool((idea["body"] or "").strip())
                kind = card_kind(has_body, idea["export_grade"])
                c = rule_card(idea) if has_body else {"problem": None, "solution": None, "missing_data": []}
                w.execute(
                    """INSERT INTO core.idea_card (idea_id, card_kind, title, problem, solution, missing_data,
                         used_data, domain, year, source_url, extractor, prompt_version)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'rule',%s)
                       ON CONFLICT (idea_id) DO UPDATE SET card_kind=EXCLUDED.card_kind, title=EXCLUDED.title,
                         problem=EXCLUDED.problem, solution=EXCLUDED.solution, missing_data=EXCLUDED.missing_data,
                         used_data=EXCLUDED.used_data, domain=EXCLUDED.domain, year=EXCLUDED.year,
                         source_url=EXCLUDED.source_url, extractor='rule', model=NULL,
                         prompt_version=EXCLUDED.prompt_version, updated_at=now()
                       WHERE core.idea_card.extractor = 'rule'""",
                    (idea["id"], kind, idea["title"], c["problem"], c["solution"], Jsonb(c["missing_data"]),
                     idea["used_data"], idea["category"], idea["year"], idea["source_url"], RULE_VERSION),
                )
                n += 1
        conn.commit()
        stats["cards"] = n
        report = g1_report(conn)
        stats["g1"] = report
    print(f"[cards] built {n}; G1 {report}")
    return report


def g1_report(conn) -> dict:
    rows = conn.execute(
        """SELECT k.card_kind, count(*), count(*) FILTER (WHERE jsonb_array_length(k.missing_data) > 0)
             FROM core.idea_card k GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    by = {kind: {"cards": n, "with_missing_data": md} for kind, n, md in rows}
    return {"by_kind": by, "total": sum(v["cards"] for v in by.values())}
