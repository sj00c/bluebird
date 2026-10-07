"""되살리기 깔때기 엔진(계획 §3.3–§3.7): 흔적 → 막힌 이유 → 바뀐 것 → S → 검토 → 공개.

원칙
- AI(규칙·LLM)는 제안만 하고, 공개는 사람 승인(review final + publication)으로만 한다.
- 원인·바뀐 것·S의 모든 점수에는 근거 URL이 있어야 한다(evidence + x_evidence). 근거 없는 원인은 U.
- 사람 입력 경로가 항상 있다(키가 없을 때 extractor=human, llm_verdict=human). 사람 입력은 누가 넣었는지 남긴다.
- 공개될 수 있는 사람 입력 글은 wording.check()를 통과해야 한다.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

from psycopg.types.json import Jsonb

from . import db, llm, score, wording
from .egress import Egress, EgressBlocked, EgressError
from .signals.catalog import today_kst

# ----------------------------------------------------------------------------- 공통

KIPRIS_SOURCE = "kipris_contest_idea_bulk"
PROFILE_REQUIRED = {
    # full_v1: news_web(NAVER)·ip(KIPRIS Plus)는 키가 있을 때만 필수. 키가 없으면 manual만 필수, external_search=not_done.
    "full_v1": ("news_web", "ip", "manual"),
    "kipris_local_v1": ("ip_local", "similar_local"),
}
KEY_FOR_ITEM = {"news_web": ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"), "ip": ("KIPRIS_PLUS_KEY",)}
SIMILAR_LOCAL_THRESHOLD = 0.6  # [가정, W2 보정] 제목 trigram 유사도


def profile_for(source_id: str, export_grade: str) -> str:
    return "kipris_local_v1" if source_id == KIPRIS_SOURCE and export_grade != "O" else "full_v1"


def required_items(profile: str, env: dict[str, str] | None = None) -> tuple[str, ...]:
    env = os.environ if env is None else env
    items = PROFILE_REQUIRED[profile]
    if profile == "full_v1":
        items = tuple(i for i in items if i == "manual" or all(env.get(k) for k in KEY_FOR_ITEM[i]))
    return items


def decide_trace(profile: str, checks: dict[str, dict], required: tuple[str, ...]) -> tuple[str, str]:
    """(status, external_search). 필수 항목이 하나라도 실행되지 않았으면 pending(none 금지).

    checks[item] = {"result": found|none|not_run, "status": 사람이 manual에서 정한 분류(선택)}
    """
    # external_search = 체계적 외부 검색(NAVER 뉴스·KIPRIS Plus 특허)을 실제로 돌렸는가. 사람 manual 확인은 따로 표기.
    external = "done" if any(checks.get(i, {}).get("result") in ("found", "none")
                             for i in ("news_web", "ip")) else "not_done"
    if any(checks.get(i, {}).get("result", "not_run") == "not_run" for i in required):
        return "pending", external
    manual = checks.get("manual", {})
    if manual.get("status"):  # 사람이 직접 분류한 결과가 최종
        return manual["status"], external
    if profile == "kipris_local_v1":
        # 로컬 기록에 연결(특허 연계·유사 아이디어)이 있으면 사람 확인 대상으로 남긴다.
        return ("pending" if any(checks[i]["result"] == "found" for i in required) else "none"), external
    return ("none" if all(checks[i]["result"] == "none" for i in required) else "pending"), external


def _evidence(conn, *, kind: str, url: str, title: str | None, excerpt: str | None,
              observed_at: date | None, target_type: str, target_id: str) -> int:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"evidence url must be http(s): {url!r}")
    ev = conn.execute(
        """INSERT INTO core.evidence (kind, url, title, excerpt, observed_at) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (kind, url, excerpt) DO UPDATE SET title = coalesce(EXCLUDED.title, core.evidence.title)
           RETURNING id""",
        (kind, url, title, excerpt, observed_at),
    ).fetchone()[0]
    conn.execute("INSERT INTO core.x_evidence VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (target_type, target_id, ev))
    return ev


def _idea(conn, idea_id: str) -> dict:
    cur = conn.execute(
        """SELECT i.id, i.source_id, i.title, i.body, i.year, i.source_url, s.url AS source_page, s.export_grade,
                  s.public_ok, k.card_kind, k.missing_data, k.problem, k.solution
             FROM core.idea i JOIN core.source s ON s.id = i.source_id
             LEFT JOIN core.idea_card k ON k.idea_id = i.id
            WHERE i.id = %s AND i.retired_at IS NULL""", (idea_id,))
    row = cur.fetchone()
    if row is None:
        raise KeyError(f"no live idea {idea_id}")
    return dict(zip([d.name for d in cur.description], row))


# ----------------------------------------------------------------------------- 1 흔적

def _save_verdict(conn, idea_id: str, profile: str, env=None) -> str:
    checks = {item: {"result": res, **detail} for item, res, detail in conn.execute(
        "SELECT item, result, detail FROM core.trace_check WHERE idea_id = %s", (idea_id,))}
    status, external = decide_trace(profile, checks, required_items(profile, env))
    conn.execute(
        """INSERT INTO core.trace_verdict (idea_id, status, profile_version, external_search)
           VALUES (%s,%s,%s,%s)
           ON CONFLICT (idea_id) DO UPDATE SET status=EXCLUDED.status, profile_version=EXCLUDED.profile_version,
             external_search=EXCLUDED.external_search, decided_at=now()""",
        (idea_id, status, profile, external),
    )
    return status


def trace_local(*, dsn: str) -> dict:
    """kipris_local_v1 로컬 흔적: ip_local(벌크의 특허 연계) + similar_local(코퍼스 안 유사 제목). 외부 호출 없음."""
    with db.pipeline_run(dsn, "trace-local") as stats, db.connect(dsn) as conn:
        conn.execute("SELECT set_config('pg_trgm.similarity_threshold', %s, true)", (str(SIMILAR_LOCAL_THRESHOLD),))
        ids = [r[0] for r in conn.execute(
            """SELECT i.id FROM core.idea i JOIN core.source s ON s.id = i.source_id
                WHERE i.retired_at IS NULL AND i.source_id = %s AND s.export_grade <> 'O'""", (KIPRIS_SOURCE,))]
        conn.execute(
            """INSERT INTO core.trace_check (idea_id, item, result, query_fields, detail)
               SELECT i.id, 'ip_local',
                      CASE WHEN jsonb_array_length(coalesce(i.extra->'patent_applno', '[]')) > 0 THEN 'found' ELSE 'none' END,
                      '{patent_applno}', jsonb_build_object('patent_applno', coalesce(i.extra->'patent_applno', '[]'))
                 FROM core.idea i WHERE i.id = ANY(%s)
               ON CONFLICT (idea_id, item) DO UPDATE SET result=EXCLUDED.result, detail=EXCLUDED.detail,
                 checked_at=now()""", (ids,))
        conn.execute(
            """INSERT INTO core.trace_check (idea_id, item, result, query_fields, detail)
               SELECT i.id, 'similar_local', CASE WHEN m.id IS NULL THEN 'none' ELSE 'found' END, '{title}',
                      CASE WHEN m.id IS NULL THEN '{}'::jsonb
                           ELSE jsonb_build_object('similar_idea', m.id, 'similarity', round(m.sim::numeric, 3)) END
                 FROM core.idea i
                 LEFT JOIN LATERAL (
                     SELECT o.id, similarity(o.title, i.title) AS sim FROM core.idea o
                      WHERE o.title %% i.title AND o.id <> i.id AND o.retired_at IS NULL
                        AND (o.year IS NULL OR i.year IS NULL OR o.year >= i.year)
                      ORDER BY sim DESC LIMIT 1) m ON true
                WHERE i.id = ANY(%s)
               ON CONFLICT (idea_id, item) DO UPDATE SET result=EXCLUDED.result, detail=EXCLUDED.detail,
                 checked_at=now()""", (ids,))
        out: dict[str, int] = {}
        for i in ids:
            st = _save_verdict(conn, i, "kipris_local_v1")
            out[st] = out.get(st, 0) + 1
        conn.commit()
        stats.update(out)
    print(f"[trace] kipris_local_v1 {out}")
    return out


def trace_pending(*, dsn: str) -> dict:
    """full_v1 소스 아이디어의 trace_verdict를 현재 check로 다시 계산(사람 manual이 없으면 pending)."""
    with db.connect(dsn) as conn:
        ids = [r[0] for r in conn.execute(
            """SELECT i.id FROM core.idea i JOIN core.source s ON s.id = i.source_id
                WHERE i.retired_at IS NULL AND NOT (i.source_id = %s AND s.export_grade <> 'O')""", (KIPRIS_SOURCE,))]
        out: dict[str, int] = {}
        for i in ids:
            st = _save_verdict(conn, i, "full_v1")
            out[st] = out.get(st, 0) + 1
        conn.commit()
    print(f"[trace] full_v1 {out}")
    return out


def trace_manual(*, dsn: str, idea_id: str, result: str, status: str | None, url: str | None, note: str,
                 by: str) -> str:
    """사람이 외부 검색을 직접 하고 결과를 넣는다. found면 근거 URL 필수. status는 최종 분류(선택)."""
    if result not in ("found", "none"):
        raise ValueError("result must be found|none")
    if result == "found" and not url:
        raise ValueError("found requires --url")
    if status and status not in ("realized", "pivot", "similar_unlinked", "award_only", "none"):
        raise ValueError(f"bad status {status}")
    wording.check(note)
    with db.connect(dsn) as conn:
        idea = _idea(conn, idea_id)
        detail = {"by": by, "note": note, **({"status": status} if status else {})}
        conn.execute(
            """INSERT INTO core.trace_check (idea_id, item, result, query_fields, detail)
               VALUES (%s,'manual',%s,'{title,host_org,year}',%s)
               ON CONFLICT (idea_id, item) DO UPDATE SET result=EXCLUDED.result, detail=EXCLUDED.detail,
                 checked_at=now()""", (idea_id, result, Jsonb(detail)))
        if url:
            _evidence(conn, kind="manual", url=url, title=None, excerpt=note, observed_at=today_kst(),
                      target_type="trace", target_id=f"{idea_id}:manual")
        st = _save_verdict(conn, idea_id, profile_for(idea["source_id"], idea["export_grade"]))
        conn.commit()
    return st


# ----------------------------------------------------------------------------- 2 막힌 이유

CAUSES = ("T", "D", "R", "M", "C", "O", "U")


def diagnose_rule(*, dsn: str) -> dict:
    """규칙 제안: 본문이 스스로 부족 데이터를 밝힌 카드(missing_data)는 원인 D, 근거 = 그 본문 문장 + 원문 URL.
    1단계(흔적)를 통과한 아이디어만. 사람·LLM 진단은 덮어쓰지 않는다."""
    n = 0
    with db.pipeline_run(dsn, "diagnose-rule") as stats, db.connect(dsn) as conn:
        rows = conn.execute(
            """SELECT k.idea_id, k.missing_data, coalesce(i.source_url, s.url) AS url, i.title
                 FROM core.idea_card k JOIN core.idea i ON i.id = k.idea_id AND i.retired_at IS NULL
                 JOIN core.source s ON s.id = i.source_id
                 JOIN core.trace_verdict t ON t.idea_id = k.idea_id AND t.status IN ('none', 'award_only')
                 LEFT JOIN core.diagnosis d ON d.idea_id = k.idea_id
                WHERE jsonb_array_length(k.missing_data) > 0 AND (d.idea_id IS NULL OR d.extractor = 'rule')"""
        ).fetchall()
        for idea_id, md, url, title in rows:
            if not url or not url.startswith(("http://", "https://")):
                continue
            for m in md:
                _evidence(conn, kind="body_excerpt", url=url, title=title, excerpt=m["excerpt"], observed_at=None,
                          target_type="diagnosis", target_id=idea_id)
            conn.execute(
                """INSERT INTO core.diagnosis (idea_id, "primary", confidence, rationale, extractor, prompt_version)
                   VALUES (%s,'D',NULL,%s,'rule','rule-v1')
                   ON CONFLICT (idea_id) DO UPDATE SET "primary"='D', rationale=EXCLUDED.rationale, decided_at=now()
                   WHERE core.diagnosis.extractor = 'rule'""",
                (idea_id, "본문이 밝힌 부족 데이터: " + ", ".join(m["name"] for m in md)),
            )
            n += 1
        conn.commit()
        stats["proposed_D"] = n
    print(f"[diagnose] rule D proposals: {n}")
    return {"proposed_D": n}


def diagnose_set(*, dsn: str, idea_id: str, cause: str, rationale: str, by: str,
                 evidence: list[tuple[str, str | None]], secondary: str | None = None) -> None:
    """사람 진단. 비-U는 근거 URL ≥1, D는 카드 missing_data 필요(DB 트리거가 다시 검사)."""
    if cause not in CAUSES or (secondary and secondary not in CAUSES):
        raise ValueError(f"cause must be one of {CAUSES}")
    if cause != "U" and not evidence:
        raise ValueError(f"cause {cause} requires at least one --evidence URL")
    wording.check(rationale, *(e[1] for e in evidence))
    with db.connect(dsn) as conn:
        _idea(conn, idea_id)
        prev = conn.execute('SELECT "primary" FROM core.diagnosis WHERE idea_id=%s', (idea_id,)).fetchone()
        if prev is not None and prev[0] != cause:  # 원인이 바뀌면 이전 원인의 근거는 떼어 낸다
            conn.execute("DELETE FROM core.x_evidence WHERE target_type='diagnosis' AND target_id=%s", (idea_id,))
        for url, excerpt in evidence:
            _evidence(conn, kind="manual", url=url, title=None, excerpt=excerpt, observed_at=today_kst(),
                      target_type="diagnosis", target_id=idea_id)
        conn.execute(
            """INSERT INTO core.diagnosis (idea_id, "primary", secondary, rationale, extractor, model, decided_by)
               VALUES (%s,%s,%s,%s,'human',%s,%s)
               ON CONFLICT (idea_id) DO UPDATE SET "primary"=EXCLUDED."primary", secondary=EXCLUDED.secondary,
                 rationale=EXCLUDED.rationale, extractor='human', model=EXCLUDED.model,
                 decided_by=EXCLUDED.decided_by, decided_at=now()""",
            (idea_id, cause, secondary, rationale, f"human:{by}", by),
        )
        conn.commit()


# ----------------------------------------------------------------------------- 3 바뀐 것

LAW_API = "https://www.law.go.kr/DRF/lawService.do"


def _xml_tag(text: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else None


def verify_law(egress: Egress, *, mst: str, effective: date) -> tuple[dict, int | None]:
    """국가법령정보 시행일 법령 본문(eflaw)을 egress로 열어 공포번호·공포일·시행일자를 읽는다.
    시행일자가 effective와 다르면 거부. OC는 LAW_OC(없으면 시험 계정 test)."""
    r = egress.get("collect", LAW_API,
                   params={"target": "eflaw", "MST": mst, "efYd": effective.strftime("%Y%m%d"), "type": "XML"},
                   path_template="/DRF/lawService.do", secret_params={"OC": os.environ.get("LAW_OC") or "test"})
    if r.status != 200:
        raise ValueError(f"law API HTTP {r.status}")
    t = r.text
    got = {"law_name": _xml_tag(t, "법령명_한글"), "promulgation_no": _xml_tag(t, "공포번호"),
           "promulgated": _xml_tag(t, "공포일자"), "effective": _xml_tag(t, "시행일자"), "mst": mst}
    if not got["promulgation_no"] or not got["effective"]:
        raise ValueError(f"law API MST={mst}: no 공포번호/시행일자 in response")
    if got["effective"] != effective.strftime("%Y%m%d"):
        raise ValueError(f"law API 시행일자 {got['effective']} != --occurred-at {effective}")
    return got, r.egress_call_id


def change_add(*, dsn: str, kind: str, url: str, title: str, occurred_at: date, by: str,
               summary: str | None = None, ref_id: str | None = None, egress: Egress | None = None,
               law_mst: str | None = None) -> str:
    """사람이 근거 URL로 바뀐 것(법령 시행·정책·기술·공고)을 넣는다. dataset_opened는 카탈로그 신호로만 생긴다.

    확인 상태(verify_status)를 남긴다:
    - law_effective: --law-mst로 국가법령정보 API를 egress로 열어 시행일자를 대조 → api_verified. 깔때기는 이것만 쓴다.
    - 화이트리스트 호스트 URL: egress로 열어 200이면 fetched, 아니면 거부.
    - 그 밖의 호스트: attested(사람 진술, 열어 보지 않음)."""
    if kind not in ("law_effective", "policy_news", "tech", "announcement"):
        raise ValueError("kind must be law_effective|policy_news|tech|announcement (dataset_opened는 카탈로그 신호만)")
    wording.check(title, summary)
    status, detail, call_id = "attested", None, None
    if kind == "law_effective":
        if not law_mst or egress is None:
            raise ValueError("law_effective needs --law-mst (법령일련번호): 시행일자를 국가법령정보 API로 대조한다")
        detail, call_id = verify_law(egress, mst=law_mst, effective=occurred_at)
        status = "api_verified"
        ref_id = ref_id or f"law:{law_mst}:{detail['effective']}"
    elif egress is not None:
        try:
            r = egress.get("collect", url, path_template="/human-evidence")
        except EgressBlocked as e:
            if "not in allowlist" not in str(e):
                raise
        else:
            if r.status != 200:
                raise ValueError(f"{url} returned HTTP {r.status}")
            status, detail, call_id = "fetched", {"http_status": r.status, "bytes": len(r.content)}, r.egress_call_id
    ref = ref_id or url
    cid = f"{kind}:{ref}"[:300]
    with db.connect(dsn) as conn:
        conn.execute(
            """INSERT INTO core.condition_change (id, kind, ref_id, occurred_at, tier, url, title, origin, added_by,
                 summary, verify_status, verify_detail, egress_call_id)
               VALUES (%s,%s,%s,%s,NULL,%s,%s,'human',%s,%s,%s,%s,%s)
               ON CONFLICT (kind, ref_id) DO UPDATE SET title=EXCLUDED.title, url=EXCLUDED.url,
                 occurred_at=EXCLUDED.occurred_at, summary=EXCLUDED.summary, verify_status=EXCLUDED.verify_status,
                 verify_detail=EXCLUDED.verify_detail, egress_call_id=EXCLUDED.egress_call_id""",
            (cid, kind, ref, occurred_at, url, title, by, summary, status, Jsonb(detail) if detail else None, call_id),
        )
        conn.commit()
    return cid


def _ensure_dataset_change(conn, pk: str) -> str | None:
    """기준 스냅샷(portal_registered)의 데이터셋도 매칭 대상이 되도록 condition_change를 만든다(tier 그대로)."""
    row = conn.execute(
        """SELECT public_data_pk, coalesce(registered_at, first_seen_at), tier, url, title, rereg_of
             FROM core.signal_dataset WHERE public_data_pk = %s""", (pk,)).fetchone()
    if row is None or row[5] is not None or not row[3]:
        return None
    conn.execute(
        """INSERT INTO core.condition_change (id, kind, ref_id, occurred_at, tier, url, title)
           VALUES (%s,'dataset_opened',%s,%s,%s,%s,%s) ON CONFLICT (kind, ref_id) DO NOTHING""",
        (f"dataset:{pk}", pk, row[1], row[2], row[3], row[4]),
    )
    return f"dataset:{pk}"


GENERIC_DATA_WORDS = frozenset({"데이터", "정보", "자료", "통계", "현황", "목록", "db", "DB", "관련", "대한", "위한"})


def specific_tokens(name: str) -> list[str]:
    """데이터 이름에서 일반어를 뺀 2자 이상 낱말(조사 '의·에 대한' 등은 낱말 경계에서 떨어진다)."""
    toks = [re.sub(r"(의|에|에서|에 대한|을|를|이|가|은|는)$", "", t) for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", name)]
    return [t for t in dict.fromkeys(toks) if len(t) >= 2 and t not in GENERIC_DATA_WORDS]


def match_candidates(*, dsn: str, per_idea: int = 5, min_sim: float = 0.3) -> dict:
    """후보 생성(판정 아님). 2단계를 통과한 아이디어만, 원인과 종류가 맞는 바뀐 것만.
    - D: 카드 missing_data 이름 ↔ 카탈로그 데이터셋 제목(trigram word_similarity), 아이디어당 상위 per_idea.
    - C: 공고 제목·요약 ↔ 카드 제목·문제(trigram), 공고당 상위 per_idea.
    - R·M·T: 사람이 change를 넣을 때 아이디어를 함께 지정한다(match set) — 자동 후보 없음."""
    made = {"D": 0, "C": 0}
    with db.pipeline_run(dsn, "match-candidates") as stats, db.connect(dsn) as conn:
        snap = conn.execute("SELECT max(id) FROM core.catalog_snapshot").fetchone()[0]
        stage2 = conn.execute(
            "SELECT idea_id, cause FROM core.funnel_stage(%s) WHERE s2", (snap,)).fetchall() if snap is not None else []
        for idea_id, cause in stage2:
            if cause != "D":
                continue
            names = [m["name"] for m in conn.execute(
                "SELECT missing_data FROM core.idea_card WHERE idea_id=%s", (idea_id,)).fetchone()[0]]
            seen: dict[str, float] = {}
            for name in names:
                toks = specific_tokens(name)
                if len(toks) < 2:  # '사진 정보'처럼 일반어뿐인 이름은 아무 데이터셋에나 붙으므로 후보를 만들지 않는다
                    continue
                for pk, sim in conn.execute(
                    """SELECT public_data_pk, word_similarity(%s, title) AS sim FROM core.signal_dataset
                        WHERE %s <%% title AND rereg_of IS NULL AND url IS NOT NULL
                          AND (SELECT count(*) FROM unnest(%s::text[]) t WHERE title ILIKE '%%' || t || '%%') >= 2
                        ORDER BY sim DESC LIMIT %s""", (name, name, toks, per_idea)):
                    if sim >= min_sim:
                        seen[pk] = max(sim, seen.get(pk, 0))
            for pk, sim in sorted(seen.items(), key=lambda kv: -kv[1])[:per_idea]:
                cid = _ensure_dataset_change(conn, pk)
                if cid and conn.execute(
                    """INSERT INTO core.change_match (change_id, idea_id, similarity) VALUES (%s,%s,%s)
                       ON CONFLICT (change_id, idea_id) DO NOTHING""", (cid, idea_id, sim)).rowcount:
                    made["D"] += 1
        c_ideas = [i for i, c in stage2 if c == "C"]
        if c_ideas:
            for cid, text in conn.execute(
                """SELECT c.id, a.title || ' ' || coalesce(a.summary, '') FROM core.condition_change c
                     JOIN core.announcement a ON a.id = c.ref_id WHERE c.kind = 'announcement'""").fetchall():
                for idea_id, sim in conn.execute(
                    """SELECT k.idea_id, word_similarity(k.title || ' ' || coalesce(k.problem, ''), %s) AS sim
                         FROM core.idea_card k WHERE k.idea_id = ANY(%s) ORDER BY sim DESC LIMIT %s""",
                        (text, c_ideas, per_idea)):
                    if sim >= min_sim and conn.execute(
                        """INSERT INTO core.change_match (change_id, idea_id, similarity) VALUES (%s,%s,%s)
                           ON CONFLICT (change_id, idea_id) DO NOTHING""", (cid, idea_id, sim)).rowcount:
                        made["C"] += 1
        conn.commit()
        stats.update(made)
    print(f"[match] candidates {made}")
    return made


def match_set(*, dsn: str, change_id: str, idea_id: str, verdict: str, what_changed: list[str], how_now: str,
              by: str) -> int:
    """사람 판정(llm_verdict=human 또는 yes/partial/no). 바뀐 것의 URL이 이 매칭의 근거가 된다."""
    if verdict not in ("yes", "partial", "no", "human"):
        raise ValueError("verdict must be yes|partial|no|human")
    wording.check(how_now, *what_changed)
    with db.connect(dsn) as conn:
        _idea(conn, idea_id)
        ch = conn.execute(
            "SELECT url, title, occurred_at, kind FROM core.condition_change WHERE id=%s", (change_id,)).fetchone()
        if ch is None:
            raise KeyError(f"no change {change_id}")
        mid = conn.execute(
            """INSERT INTO core.change_match (change_id, idea_id, llm_verdict, what_changed, how_now, model,
                 prompt_version, status)
               VALUES (%s,%s,%s,%s,%s,%s,'human-v1',%s)
               ON CONFLICT (change_id, idea_id) DO UPDATE SET llm_verdict=EXCLUDED.llm_verdict,
                 what_changed=EXCLUDED.what_changed, how_now=EXCLUDED.how_now, model=EXCLUDED.model,
                 prompt_version=EXCLUDED.prompt_version, status=EXCLUDED.status
               RETURNING id""",
            (change_id, idea_id, "human" if verdict in ("yes", "partial", "human") else "no", what_changed, how_now,
             f"human:{by}:{verdict}", "rejected" if verdict == "no" else "candidate"),
        ).fetchone()[0]
        _evidence(conn, kind=ch[3], url=ch[0], title=ch[1], excerpt=None, observed_at=ch[2],
                  target_type="change_match", target_id=str(mid))
        conn.commit()
    return mid


M1_VERSION = "m1-v1"
M1_SYSTEM = ("You judge whether a public change (a dataset release, law, announcement, policy or technology) removes "
             "the stated barrier of a past contest idea. Use only the given fields. Answer in Korean, JSON only.")
M1_INSTRUCTION = (
    'Return {"verdict": "yes"|"partial"|"no", "what_changed": [short Korean phrases], "how_now": "one Korean '
    'sentence on what the idea can do now"}. Never claim something did not exist before; say only what is '
    'available now. If unsure, answer "no".')


def match_judge(*, dsn: str, limit: int = 50, egress: Egress | None = None) -> dict:
    """후보 매칭을 상용 LLM이 판정(키가 있을 때만, egress 경유). 보내는 것은 아이디어 제목·문제와 바뀐 것의
    제목뿐(이벤트 URL은 보내지 않고 근거로만 남는다). 결과는 제안: status는 candidate 그대로, 사람이 승인한다."""
    prov = llm.provider()
    if prov is None:
        print("[match] judge: key_required (OPENAI_API_KEY/ANTHROPIC_API_KEY 없음) — `match set`으로 사람이 판정")
        return {"judged": 0, "key_required": True}
    own = egress is None
    eg = egress or Egress.from_dsn(dsn)
    n = {"yes": 0, "partial": 0, "no": 0, "failed": 0}
    try:
        with db.pipeline_run(dsn, "match-judge") as stats, db.connect(dsn) as conn:
            rows = conn.execute(
                """SELECT m.id, i.source_id, k.title, k.problem, c.kind, c.title, c.url, c.occurred_at
                     FROM core.change_match m
                     JOIN core.condition_change c ON c.id = m.change_id
                     JOIN core.idea i ON i.id = m.idea_id AND i.retired_at IS NULL
                     JOIN core.idea_card k ON k.idea_id = m.idea_id
                    WHERE m.llm_verdict IS NULL AND m.status = 'candidate'
                    ORDER BY m.similarity DESC NULLS LAST, m.id LIMIT %s""", (limit,)).fetchall()
            for mid, sid, title, problem, kind, ctitle, curl, cat in rows:
                fields = {"title": (sid, title), "change_title": (sid, f"[{kind}] {ctitle}")}
                if problem:
                    fields["problem"] = (sid, problem)
                try:
                    data, _ = llm.ask_json(eg, prov, system=M1_SYSTEM, instruction=M1_INSTRUCTION, fields=fields,
                                           max_tokens=400)
                    verdict = data.get("verdict")
                    if verdict not in ("yes", "partial", "no"):
                        raise ValueError(f"bad verdict {verdict!r}")
                    what = [str(w)[:200] for w in data.get("what_changed") or []][:5]
                    how = (str(data.get("how_now") or "").strip()[:500]) or None
                    try:
                        wording.check(how, *what)
                    except wording.WordingError:
                        what, how = [], None  # 금지 표현이면 문장은 버리고 판정만 남긴다
                except (EgressError, ValueError, KeyError, TypeError, AttributeError):
                    n["failed"] += 1
                    continue
                conn.execute(
                    """UPDATE core.change_match SET llm_verdict=%s, what_changed=%s, how_now=%s, model=%s,
                         prompt_version=%s, status=CASE WHEN %s='no' THEN 'rejected' ELSE status END WHERE id=%s""",
                    (verdict, what, how, f"{prov.name}:{prov.model}", M1_VERSION, verdict, mid))
                _evidence(conn, kind=kind, url=curl, title=ctitle, excerpt=None, observed_at=cat,
                          target_type="change_match", target_id=str(mid))
                conn.commit()
                n[verdict] += 1
            stats.update(n)
    finally:
        if own:
            eg.close()
    print(f"[match] judge {n}")
    return n


# ----------------------------------------------------------------------------- 4 S

def score_set(*, dsn: str, idea_id: str, scores: dict[str, int | None], evidence: dict[str, str], by: str,
              as_of: date | None = None) -> score.Score:
    """사람 채점. 점수 있는 항목마다 근거 URL 필수. 바뀐 것의 축은 승인 전 매칭(yes/partial/human)에서 가져온다."""
    missing = [k for k, v in scores.items() if v is not None and not evidence.get(k)]
    if missing:
        raise ValueError(f"scored axes need evidence URL: {missing}")
    as_of = as_of or today_kst()
    with db.connect(dsn) as conn:
        _idea(conn, idea_id)
        kinds = {r[0] for r in conn.execute(
            """SELECT c.kind FROM core.change_match m JOIN core.condition_change c ON c.id = m.change_id
                 JOIN core.diagnosis d ON d.idea_id = m.idea_id
                 JOIN core.cause_change_kind ck ON ck.cause = d."primary" AND ck.kind = c.kind
                WHERE m.idea_id=%s AND m.llm_verdict IN ('yes','partial','human') AND m.status <> 'rejected'""",
            (idea_id,))}
        sc = score.compute(scores, kinds)
        conn.execute(
            """INSERT INTO core.timeliness (idea_id, as_of, tech, data, regulation, policy, weights, n_scored, s,
                 verdict, resolve_condition, scored_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (idea_id, as_of) DO UPDATE SET tech=EXCLUDED.tech, data=EXCLUDED.data,
                 regulation=EXCLUDED.regulation, policy=EXCLUDED.policy, weights=EXCLUDED.weights,
                 n_scored=EXCLUDED.n_scored, s=EXCLUDED.s, verdict=EXCLUDED.verdict,
                 resolve_condition=EXCLUDED.resolve_condition, scored_by=EXCLUDED.scored_by,
                 created_at=now()""",
            (idea_id, as_of, scores.get("tech"), scores.get("data"), scores.get("regulation"), scores.get("policy"),
             Jsonb(score.DEFAULT_WEIGHTS), sc.n_scored, sc.s, sc.verdict, sc.resolve_condition, by),
        )
        # 다시 채점하면 그 채점의 근거를 새로 건다(이전 축·URL 근거가 남지 않게).
        tid = f"{idea_id}@{as_of.isoformat()}"
        conn.execute("DELETE FROM core.x_evidence WHERE target_type='timeliness' AND target_id=%s", (tid,))
        for axis, url in evidence.items():
            if scores.get(axis) is not None:
                _evidence(conn, kind="manual", url=url, title=f"시의성 {score.AXIS_KO[axis]} 근거",
                          excerpt=f"채점 {by}", observed_at=as_of, target_type="timeliness", target_id=tid)
        conn.commit()
    return sc


# ----------------------------------------------------------------------------- 5 검토·승인

def _live_idea(conn, idea_id: str) -> None:
    """승인 대상: 퇴역하지 않았고, 이의 수용으로 원본 공개를 멈추지(withheld) 않은 아이디어."""
    row = conn.execute("SELECT withheld_at FROM core.idea WHERE id=%s AND retired_at IS NULL", (idea_id,)).fetchone()
    if row is None:
        raise KeyError(f"no live idea {idea_id}")
    if row[0] is not None:
        raise ValueError(f"{idea_id} is withheld since {row[0]:%Y-%m-%d} (objection); it cannot be approved")


def approve(*, dsn: str, idea_id: str, by: str, note: str | None = None) -> dict:
    """최종 승인: 4단계까지 통과한 아이디어만. review(final) + publication(card·diagnosis·timeliness) +
    매칭된 바뀐 것(status=approved, publication change). 원인 근거가 없거나 S가 hold면 거부."""
    wording.check(note)
    with db.connect(dsn) as conn:
        _live_idea(conn, idea_id)
        snap = conn.execute("SELECT max(id) FROM core.catalog_snapshot").fetchone()[0]
        row = conn.execute("SELECT s0, s1, s2, s3, s4 FROM core.funnel_stage(%s) WHERE idea_id=%s",
                           (snap, idea_id)).fetchone()
        if row is None:
            raise KeyError(f"no live idea {idea_id}")
        failed = [f"s{i}" for i, ok in enumerate(row) if not ok]
        if failed:
            raise ValueError(f"{idea_id} has not passed {failed[0]} (stage flags {row})")
        mids = [r[0] for r in conn.execute(
            "SELECT m.id FROM core.change_match m WHERE m.idea_id=%s AND core.match_eligible(m.id, %s)",
            (idea_id, snap))]
        conn.execute("INSERT INTO core.review (target_type, target_id, reviewer, round, decision, note)"
                     " VALUES ('idea',%s,%s,'final','approve',%s)", (idea_id, by, note))
        for scope in ("card", "diagnosis", "timeliness"):
            conn.execute(
                """INSERT INTO core.publication (target_type, target_id, scope, approved_by) VALUES ('idea',%s,%s,%s)
                   ON CONFLICT (target_type, target_id, scope) DO UPDATE SET approved_by=EXCLUDED.approved_by,
                     approved_at=now(), revoked_at=NULL""", (idea_id, scope, by))
        for mid in mids:
            conn.execute("UPDATE core.change_match SET status='approved' WHERE id=%s", (mid,))
            conn.execute(
                """INSERT INTO core.publication (target_type, target_id, scope, approved_by)
                   VALUES ('change_match',%s,'change',%s)
                   ON CONFLICT (target_type, target_id, scope) DO UPDATE SET approved_by=EXCLUDED.approved_by,
                     approved_at=now(), revoked_at=NULL""", (str(mid), by))
        conn.commit()
    return {"idea_id": idea_id, "changes": mids}


def reject(*, dsn: str, idea_id: str, by: str, note: str) -> None:
    """반려: 아이디어·바뀐 것 공개를 모두 철회하고, 승인된 매칭은 후보로, weekly_top에서 뺀다."""
    wording.check(note)
    with db.connect(dsn) as conn:
        if conn.execute("SELECT 1 FROM core.idea WHERE id=%s AND retired_at IS NULL", (idea_id,)).fetchone() is None:
            raise KeyError(f"no live idea {idea_id}")
        conn.execute("INSERT INTO core.review (target_type, target_id, reviewer, round, decision, note)"
                     " VALUES ('idea',%s,%s,'final','reject',%s)", (idea_id, by, note))
        conn.execute("SELECT core.revoke_idea(%s)", (idea_id,))
        conn.commit()


# ----------------------------------------------------------------------------- 화면1 weekly_top

def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def compute_top(*, dsn: str, week: date) -> list[tuple]:
    """5단계(승인) + public_ok 카드 중 S 내림차순 → 승인일 최신. 소스 계열당 최대 4건, observed_new 근거 우선."""
    week = week_start(week)
    with db.connect(dsn) as conn:
        snap = conn.execute("SELECT max(id) FROM core.catalog_snapshot").fetchone()[0]
        rows = conn.execute(
            """WITH f AS (SELECT idea_id, source_id FROM core.funnel_stage(%s) WHERE s5 AND public_ok),
                    s AS (SELECT DISTINCT ON (idea_id) idea_id, s FROM core.timeliness ORDER BY idea_id, as_of DESC),
                    obs AS (SELECT DISTINCT m.idea_id FROM core.change_match m
                              JOIN core.condition_change c ON c.id = m.change_id
                             WHERE m.status = 'approved' AND c.tier = 'observed_new'
                               AND core.match_eligible(m.id, %s)),
                    ap AS (SELECT target_id, max(approved_at) AS at FROM core.publication
                            WHERE target_type = 'idea' AND revoked_at IS NULL GROUP BY 1),
                    ranked AS (
                      SELECT f.idea_id, f.source_id, s.s, obs.idea_id IS NOT NULL AS observed, ap.at,
                             row_number() OVER (PARTITION BY f.source_id
                                                ORDER BY obs.idea_id IS NOT NULL DESC, s.s DESC, ap.at DESC) AS fam_rank
                        FROM f JOIN s USING (idea_id) LEFT JOIN obs USING (idea_id)
                        JOIN ap ON ap.target_id = f.idea_id)
               SELECT idea_id, source_id, s FROM ranked WHERE fam_rank <= 4
                ORDER BY observed DESC, s DESC, at DESC LIMIT 20""", (snap, snap)).fetchall()
        conn.execute("DELETE FROM core.weekly_top WHERE week=%s", (week,))
        for rank, (idea_id, fam, s) in enumerate(rows, 1):
            conn.execute("INSERT INTO core.weekly_top (week, rank, idea_id, s, source_family) VALUES (%s,%s,%s,%s,%s)",
                         (week, rank, idea_id, s, fam))
        conn.commit()
    print(f"[top] week {week}: {len(rows)} ideas")
    return rows


# ----------------------------------------------------------------------------- funnel 리포트

STAGES = ("s0", "s1", "s2", "s3", "s4", "s5", "s6")
STAGE_NAMES = ("0 원본(카드)", "1 흔적", "2 막힌 이유", "3 바뀐 것", "4 S", "5 검토", "6 공개")


def report(*, dsn: str, as_of: int | None = None) -> dict:
    with db.connect(dsn) as conn:
        snap = as_of if as_of is not None else conn.execute("SELECT max(id) FROM core.catalog_snapshot").fetchone()[0]
        if snap is None:
            raise ValueError("no catalog snapshot loaded")
        rows = conn.execute(
            f"""SELECT source_id, card_kind, coalesce(profile_version, '-'),
                       {", ".join(f"count(*) FILTER (WHERE {s})" for s in STAGES)},
                       count(*) FILTER (WHERE trace_status = 'pending')
                  FROM core.funnel_stage(%s) GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""", (snap,)).fetchall()
    total = [sum(r[3 + i] for r in rows) for i in range(len(STAGES))]
    return {"as_of_snapshot": snap, "rows": [
        {"source_id": r[0], "card_kind": r[1], "profile": r[2], **dict(zip(STAGES, r[3:10])), "trace_pending": r[10]}
        for r in rows], "total": dict(zip(STAGES, total))}


def print_report(rep: dict) -> None:
    print(f"되살리기 깔때기 — 카탈로그 스냅샷 #{rep['as_of_snapshot']} 기준")
    head = f"{'소스':28} {'card_kind':13} {'흔적 프로필':16} " + " ".join(f"{n:>9}" for n in STAGE_NAMES) + "  흔적미확인"
    print(head)
    for r in rep["rows"]:
        print(f"{r['source_id']:28} {r['card_kind'] or '-':13} {r['profile']:16} "
              + " ".join(f"{r[s]:>9,}" for s in STAGES) + f"  {r['trace_pending']:>9,}")
    t = rep["total"]
    print(f"{'합계':58} " + " ".join(f"{t[s]:>9,}" for s in STAGES))


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, indent=1)
