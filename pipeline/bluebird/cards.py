"""아이디어 카드(P1) 생성 — 계획 §3.6.

card_kind는 "P1이 실제로 무엇을 받았나"로 정한다(계획 §3.6).
- full          : 본문이 egress를 거쳐 외부 LLM(P1)에 전송되어 만든 카드. export_grade=O 소스 + LLM 키가 있을 때만.
- local_extract : 본문을 업무망 안에서만 규칙으로 추출한 카드(KIPRIS 약관 대기, 또는 LLM 키 없음).
- title_only    : 본문이 없는 소스(제목·활용 데이터만).
LLM 응답의 missing_data는 본문 안에 실제로 있는 문장(excerpt)만 받아들인다 — 위치(char_span)를 본문에서 다시 찾는다.
missing_data는 본문이 스스로 밝힌 부족·미개방 데이터 문장만 담는다(D 원인·D 신호의 아이디어 쪽 키).
경진대회 "활용 데이터"(used_data)는 이미 쓴 데이터라 missing_data가 아니다.
"""

from __future__ import annotations

import hashlib
import re

from psycopg.types.json import Jsonb

from . import db, llm
from .egress import Egress, EgressError

RULE_VERSION = "rule-v1"
P1_VERSION = "p1-v1"
P1_SYSTEM = (
    "너는 공모전 아이디어 본문에서 사실만 뽑는 추출기다. 본문에 없는 내용은 만들지 않는다. "
    "출력은 JSON 객체 하나만 낸다."
)
P1_INSTRUCTION = (
    "아래 아이디어의 제목(title)과 본문(body)에서 다음을 뽑아 JSON으로 답하라. "
    '{"problem": 해결하려는 문제 한 문장|null, "solution": 제안한 해결 방식 한 문장|null, '
    '"target_user": 대상 사용자|null, "required_tech": [필요 기술], '
    '"missing_data": [{"name": 본문이 없다·부족하다·공개되지 않았다고 밝힌 데이터 이름, '
    '"excerpt": 그렇게 밝힌 본문 문장을 글자 그대로}]}. '
    "missing_data는 본문이 스스로 부족·미개방이라고 쓴 경우만 넣고, 단지 활용한 데이터는 넣지 않는다."
)

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


def card_kind(has_body: bool, sent_to_llm: bool) -> str:
    if not has_body:
        return "title_only"
    return "full" if sent_to_llm else "local_extract"


_CUE = re.compile(r"없|부족|미개방|비공개|공개되지\s*않|개방되지\s*않|구하기\s*어렵|확보|제공되지\s*않|부재|흩어져|분산")
_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_GENERIC = frozenset({"데이터", "정보", "자료", "통계"})
EXCERPT_MIN, EXCERPT_MAX = 10, 300


def _anchor_missing(body: str, items: object) -> list[dict]:
    """LLM이 낸 missing_data 중 다음을 모두 만족하는 것만 남긴다(지어낸 부족 데이터가 D 원인으로 가는 것을 막음).
    - excerpt가 본문에 글자 그대로 있고 길이 10–300자
    - excerpt에 부족·미개방 표현이 있음
    - name의 일반어(데이터·정보…)가 아닌 낱말 하나 이상이 excerpt에 있음"""
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        ex, name = str(it.get("excerpt") or "").strip(), str(it.get("name") or "").strip()
        if not name or not EXCERPT_MIN <= len(ex) <= EXCERPT_MAX or not _CUE.search(ex):
            continue
        tokens = [t for t in _TOKEN.findall(name) if t not in _GENERIC]
        if not tokens or not any(t in ex for t in tokens):
            continue
        pos = body.find(ex)
        if pos < 0:
            continue
        out.append({"name": name[:120], "excerpt": ex, "char_span": [pos, pos + len(ex)], "origin": "body"})
    return out


def llm_card(eg: Egress, p: llm.Provider, idea: dict) -> tuple[dict, int | None]:
    sid = idea["source_id"]
    data, call_id = llm.ask_json(eg, p, system=P1_SYSTEM, instruction=P1_INSTRUCTION,
                                 fields={"title": (sid, idea["title"]), "body": (sid, idea["body"])})
    def s(k):
        v = data.get(k)
        return str(v).strip()[:500] if v else None
    tech = data.get("required_tech")
    return {
        "problem": s("problem"), "solution": s("solution"), "target_user": s("target_user"),
        "required_tech": [str(t)[:80] for t in tech][:10] if isinstance(tech, list) else [],
        "missing_data": _anchor_missing(idea["body"], data.get("missing_data")),
    }, call_id


def body_sha(body: str | None) -> str:
    return hashlib.sha256((body or "").strip().encode()).hexdigest()


def build(*, dsn: str, rebuild: bool = False, egress: Egress | None = None) -> dict:
    """카드 생성. 본문 있는 export_grade=O 소스는 LLM 키가 있으면 P1(LLM, egress 경유)로, 없으면 규칙으로 만든다.

    다시 만드는 경우: 카드 없음 / 본문 해시가 바뀜(LLM·규칙 카드 모두. 사람 카드는 본문이 바뀌어도 사람이 다시 본다) /
    키가 생겨 규칙 카드를 LLM으로 올릴 수 있음. --rebuild는 사람 카드를 뺀 전부.
    """
    prov = llm.provider()
    with db.pipeline_run(dsn, "cards") as stats, db.connect(dsn) as conn:
        cur = conn.execute(
            """SELECT i.id, i.source_id, i.title, i.body, i.used_data, i.category, i.year, i.source_url,
                      s.export_grade, k.extractor, k.body_sha256
                 FROM core.idea i JOIN core.source s ON s.id = i.source_id
                 LEFT JOIN core.idea_card k ON k.idea_id = i.id
                WHERE i.retired_at IS NULL AND (k.idea_id IS NULL OR k.extractor <> 'human')
                ORDER BY i.id"""
        )
        cols = [d.name for d in cur.description]
        todo = []
        for row in cur.fetchall():
            idea = dict(zip(cols, row))
            sha = body_sha(idea["body"])
            has_body = bool((idea["body"] or "").strip())
            upgrade = prov is not None and idea["extractor"] == "rule" and has_body and idea["export_grade"] == "O"
            if rebuild or idea["extractor"] is None or idea["body_sha256"] != sha or upgrade:
                todo.append({**idea, "sha": sha, "has_body": has_body})
        own = prov is not None and egress is None
        eg = egress or (Egress.from_dsn(dsn) if prov else None)
        n = {"rule": 0, "llm": 0, "llm_failed": 0}
        try:
            with conn.cursor() as w:
                for idea in todo:
                    c, extractor, model, version, call_id, sent = None, "rule", None, RULE_VERSION, None, False
                    if idea["has_body"] and prov and idea["export_grade"] == "O":
                        try:
                            c, call_id = llm_card(eg, prov, idea)
                            extractor, model, version, sent = "llm", prov.model, P1_VERSION, True
                        except (EgressError, ValueError, KeyError, TypeError, IndexError, AttributeError) as e:
                            n["llm_failed"] += 1
                            print(f"[cards] P1 failed for {idea['id']}: {type(e).__name__}: {str(e)[:200]}")
                    if c is None:
                        c = rule_card(idea) if idea["has_body"] else {"problem": None, "solution": None,
                                                                      "missing_data": []}
                    n[extractor] += 1
                    w.execute(
                        """INSERT INTO core.idea_card (idea_id, card_kind, title, problem, solution, target_user,
                             missing_data, used_data, required_tech, domain, year, source_url, extractor, model,
                             prompt_version, body_sha256, egress_call_id)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (idea_id) DO UPDATE SET card_kind=EXCLUDED.card_kind, title=EXCLUDED.title,
                             problem=EXCLUDED.problem, solution=EXCLUDED.solution, target_user=EXCLUDED.target_user,
                             missing_data=EXCLUDED.missing_data, used_data=EXCLUDED.used_data,
                             required_tech=EXCLUDED.required_tech, domain=EXCLUDED.domain, year=EXCLUDED.year,
                             source_url=EXCLUDED.source_url, extractor=EXCLUDED.extractor, model=EXCLUDED.model,
                             prompt_version=EXCLUDED.prompt_version, body_sha256=EXCLUDED.body_sha256,
                             egress_call_id=EXCLUDED.egress_call_id, updated_at=now()
                           WHERE core.idea_card.extractor <> 'human'""",
                        (idea["id"], card_kind(idea["has_body"], sent), idea["title"], c["problem"],
                         c["solution"], c.get("target_user"), Jsonb(c["missing_data"]), idea["used_data"],
                         c.get("required_tech") or [], idea["category"], idea["year"], idea["source_url"],
                         extractor, model, version, idea["sha"], call_id),
                    )
                    if sent:  # LLM 결과는 건별로 확정(중단돼도 비용 쓴 결과는 남김)
                        conn.commit()
            conn.commit()
        finally:
            if own:
                eg.close()
        stats.update(n)
        report = g1_report(conn)
        stats["g1"] = report
    print(f"[cards] {n} (LLM {'on: ' + prov.name if prov else 'off: no key'}); G1 {report}")
    return report


def g1_report(conn) -> dict:
    rows = conn.execute(
        """SELECT k.card_kind, count(*), count(*) FILTER (WHERE jsonb_array_length(k.missing_data) > 0)
             FROM core.idea_card k JOIN core.idea i ON i.id = k.idea_id
            WHERE i.retired_at IS NULL GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    by = {kind: {"cards": n, "with_missing_data": md} for kind, n, md in rows}
    return {"by_kind": by, "total": sum(v["cards"] for v in by.values())}
