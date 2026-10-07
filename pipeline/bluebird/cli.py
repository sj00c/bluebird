"""bluebird CLI. 경로·DSN은 인자 또는 환경변수(BB_*)로 받는다.

업무망 backend-jobs가 실행한다. 외부 호출은 egress 모듈을 거쳐 DMZ 프록시로만 나간다.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from . import announce, cards, db, funnel, ingest, objections, publish, sources_check
from .signals import catalog


def _env(name: str) -> str | None:
    return os.environ.get(name)


def _p(name: str):
    v = _env(name)
    return Path(v) if v else None


def _require(ap: argparse.ArgumentParser, a: argparse.Namespace, *names: str) -> None:
    missing = [n for n in names if getattr(a, n) is None]
    if missing:
        ap.error(f"missing required options/env: {', '.join(missing)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bluebird")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("migrate", help="SQL 마이그레이션 적용 (publish는 템플릿 등록 포함)")
    m.add_argument("--target", choices=db.TARGETS, required=True)
    m.add_argument("--dsn", default=None, help="기본: core=BB_DSN, publish=BB_PUBLISH_MIGRATOR_DSN")

    i = sub.add_parser("ingest", help="seed 파일 → core 적재(마스킹·익명 ID)")
    i.add_argument("--dsn", default=_env("BB_DSN"))
    i.add_argument("--config", type=Path, default=_p("BB_SOURCES"))
    i.add_argument("--seed-dir", type=Path, default=_p("BB_SEED_DIR"))
    i.add_argument("--secret", type=Path, default=_p("BB_ANON_SECRET"))
    i.add_argument("--only")
    i.add_argument("--force", action="store_true", help="같은 파일도 다시 적재")
    i.add_argument("--allow-retire", action="store_true", help="절반 넘게 사라지는 퇴역 허용")

    cb = sub.add_parser("cards", help="아이디어 카드(P1) 생성 + G1 card_kind별 보고")
    cb.add_argument("--dsn", default=_env("BB_DSN"))
    cb.add_argument("--rebuild", action="store_true")

    sc = sub.add_parser("sources", help="소스 점검")
    scs = sc.add_subparsers(dest="sources_cmd", required=True)
    chk = scs.add_parser("check", help="파일·외부 소스 실제 호출 점검 → core.source_check")
    chk.add_argument("--dsn", default=_env("BB_DSN"))
    chk.add_argument("--config", type=Path, default=_p("BB_SOURCES"))
    chk.add_argument("--seed-dir", type=Path, default=_p("BB_SEED_DIR"))
    chk.add_argument("--secret", type=Path, default=_p("BB_ANON_SECRET"))

    pb = sub.add_parser("publish", help="승인분 → DMZ 공개용 DB 교체(push)")
    pb.add_argument("--dsn", default=_env("BB_DSN"))
    pb.add_argument("--publish-dsn", default=_env("BB_PUBLISH_DSN"))

    sg = sub.add_parser("signals", help="바뀐 것 신호")
    sgs = sg.add_subparsers(dest="signal", required=True)
    ci = sgs.add_parser("catalog-import", help="목록개방현황 파일 → 스냅샷")
    ci.add_argument("--file", type=Path, required=True)
    ci.add_argument("--taken-at", type=date.fromisoformat, required=True)
    ci.add_argument("--dsn", default=_env("BB_DSN"))
    cf = sgs.add_parser("catalog-fetch", help="egress로 목록개방현황 내려받아 스냅샷")
    cf.add_argument("--out-dir", type=Path, default=_p("BB_SIGNAL_DIR"))
    cf.add_argument("--dsn", default=_env("BB_DSN"))
    cf.add_argument("--no-import", action="store_true")
    cf.add_argument("--taken-at", type=date.fromisoformat, default=None, help="기본: 오늘(KST)")

    ob = sub.add_parser("objections", help="이의 제기(G11): DMZ inbox pull, 처리")
    obs = ob.add_subparsers(dest="sub", required=True)
    x = obs.add_parser("pull", help="inbox → core.objection(검증·상한) 후 DMZ에서 삭제")
    x.add_argument("--dsn", default=_env("BB_DSN"))
    x.add_argument("--inbox-dsn", default=_env("BB_INBOX_DSN"))
    x.add_argument("--limit", type=int, default=objections.PULL_LIMIT)
    x = obs.add_parser("resolve", help="사람 처리(콘솔과 같은 동작)")
    x.add_argument("--dsn", default=_env("BB_DSN"))
    x.add_argument("--id", type=int, required=True)
    x.add_argument("--decision", choices=("accepted", "rejected"), required=True)
    x.add_argument("--resolution", required=True)
    x.add_argument("--withhold", action="store_true")
    x.add_argument("--by", required=True)

    cd = sub.add_parser("coding", help="κ 표본(2인 독립 코딩)")
    cds = cd.add_subparsers(dest="sub", required=True)
    x = cds.add_parser("sample", help="모집단에서 층화 표본 생성(seed 기록)")
    x.add_argument("--dsn", default=_env("BB_DSN"))
    x.add_argument("--size", type=int, default=100)
    x.add_argument("--seed", type=int, required=True)
    x.add_argument("--sample-id")

    _funnel_parsers(sub)
    a = ap.parse_args(argv)
    if a.cmd in FUNNEL_CMDS:
        _require(ap, a, "dsn")
        return _run_funnel(a)

    if a.cmd == "migrate":
        dsn = a.dsn or _env("BB_DSN" if a.target == "core" else "BB_PUBLISH_MIGRATOR_DSN")
        if not dsn:
            ap.error("missing --dsn")
        print("applied:", db.migrate(dsn, a.target) or "nothing")
        if a.target == "publish":
            print(f"template {publish.TEMPLATE_VERSION}:", publish.register_template(dsn)[:12])
    elif a.cmd == "ingest":
        _require(ap, a, "dsn", "config", "seed_dir", "secret")
        ingest.ingest(dsn=a.dsn, config=a.config, seed_dir=a.seed_dir, secret_path=a.secret, only=a.only,
                      force=a.force, allow_retire=a.allow_retire)
    elif a.cmd == "cards":
        _require(ap, a, "dsn")
        cards.build(dsn=a.dsn, rebuild=a.rebuild)
    elif a.cmd == "sources":
        _require(ap, a, "dsn", "config", "seed_dir", "secret")
        res = sources_check.run(dsn=a.dsn, config=a.config, seed_dir=a.seed_dir, secret_path=a.secret)
        sources_check.print_table(res)
        bad = [r["source_id"] for r in res if r["tier"] == "must" and r["status"] in ("error", "blocked")]
        if bad:
            print(f"must sources failing: {', '.join(bad)}", file=sys.stderr)
            return 2
    elif a.cmd == "objections":
        _require(ap, a, "dsn")
        if a.sub == "pull":
            _require(ap, a, "inbox_dsn")
            objections.pull(dsn=a.dsn, inbox_dsn=a.inbox_dsn, limit=a.limit)
        else:
            print(objections.resolve(dsn=a.dsn, objection_id=a.id, decision=a.decision, resolution=a.resolution,
                                     by=a.by, withhold=a.withhold))
    elif a.cmd == "coding":
        _require(ap, a, "dsn")
        objections.make_sample(dsn=a.dsn, size=a.size, seed=a.seed, sample_id=a.sample_id)
    elif a.cmd == "publish":
        _require(ap, a, "dsn", "publish_dsn")
        publish.push(core_dsn=a.dsn, publish_dsn=a.publish_dsn)
    elif a.cmd == "signals":
        _require(ap, a, "dsn")
        if a.signal == "catalog-import":
            catalog.import_snapshot(dsn=a.dsn, path=a.file, taken_at=a.taken_at)
        elif a.signal == "catalog-fetch":
            _require(ap, a, "out_dir")
            from .egress import Egress
            with Egress.from_dsn(a.dsn) as eg:
                path = catalog.fetch(egress=eg, out_dir=a.out_dir)
            if not a.no_import:
                catalog.import_snapshot(dsn=a.dsn, path=path, taken_at=a.taken_at or catalog.today_kst())
    return 0


FUNNEL_CMDS = ("trace", "diagnose", "changes", "match", "score", "review", "top", "funnel", "announce")


def _ev(s: str) -> tuple[str, str | None]:
    url, _, excerpt = s.partition("|")
    return url.strip(), excerpt.strip() or None


def _funnel_parsers(sub) -> None:
    def p(parent, name, help_):
        x = parent.add_parser(name, help=help_)
        x.add_argument("--dsn", default=_env("BB_DSN"))
        return x

    by = {"required": True, "help": "입력한 사람(감사 기록)"}
    t = sub.add_parser("trace", help="1 흔적").add_subparsers(dest="sub", required=True)
    p(t, "local", "kipris_local_v1: ip_local + similar_local(외부 호출 없음)")
    p(t, "refresh", "full_v1 판정 재계산(필수 항목 미실행이면 pending)")
    x = p(t, "manual", "사람이 외부 검색한 결과 입력")
    x.add_argument("--idea", required=True)
    x.add_argument("--result", choices=("found", "none"), required=True)
    x.add_argument("--status", choices=("realized", "pivot", "similar_unlinked", "award_only", "none"))
    x.add_argument("--url")
    x.add_argument("--note", required=True)
    x.add_argument("--by", **by)

    d = sub.add_parser("diagnose", help="2 막힌 이유").add_subparsers(dest="sub", required=True)
    p(d, "rule", "본문 missing_data → 원인 D 제안(근거 = 본문 문장)")
    x = p(d, "set", "사람 진단(비-U는 --evidence 'URL|발췌' ≥1)")
    x.add_argument("--idea", required=True)
    x.add_argument("--cause", choices=funnel.CAUSES, required=True)
    x.add_argument("--secondary", choices=funnel.CAUSES)
    x.add_argument("--rationale", required=True)
    x.add_argument("--evidence", action="append", type=_ev, default=[])
    x.add_argument("--by", **by)

    c = sub.add_parser("changes", help="3 바뀐 것(사람 입력)").add_subparsers(dest="sub", required=True)
    x = p(c, "add", "법령 시행·정책·기술 변화를 근거 URL로 입력")
    x.add_argument("--kind", choices=("law_effective", "policy_news", "tech"), required=True)
    x.add_argument("--url", required=True)
    x.add_argument("--title", required=True)
    x.add_argument("--occurred-at", type=date.fromisoformat, required=True)
    x.add_argument("--summary")
    x.add_argument("--law-mst", help="law_effective: 국가법령정보 법령일련번호(MST). 시행일자를 API로 대조한다")
    x.add_argument("--by", **by)

    mt = sub.add_parser("match", help="3 바뀐 것 매칭").add_subparsers(dest="sub", required=True)
    p(mt, "candidates", "원인·종류가 맞는 후보 생성(D: 카탈로그, C: 공고)")
    x = p(mt, "judge", "후보를 상용 LLM이 판정(키 있을 때, egress 경유; 승인은 사람)")
    x.add_argument("--limit", type=int, default=50)
    x = p(mt, "set", "사람 판정")
    x.add_argument("--change", required=True)
    x.add_argument("--idea", required=True)
    x.add_argument("--verdict", choices=("yes", "partial", "no", "human"), required=True)
    x.add_argument("--what-changed", action="append", default=[])
    x.add_argument("--how-now", required=True)
    x.add_argument("--by", **by)

    x = p(sub, "score", "4 시의성 S(사람 채점, 항목마다 근거 URL)")
    x.add_argument("--idea", required=True)
    for axis in ("tech", "data", "regulation", "policy"):
        x.add_argument(f"--{axis}", type=int)
        x.add_argument(f"--{axis}-url")
    x.add_argument("--as-of", type=date.fromisoformat)
    x.add_argument("--by", **by)

    r = sub.add_parser("review", help="5 검토·승인").add_subparsers(dest="sub", required=True)
    x = p(r, "approve", "최종 승인 → 공개 대상")
    x.add_argument("--idea", required=True)
    x.add_argument("--note")
    x.add_argument("--by", **by)
    x = p(r, "reject", "반려(공개 철회)")
    x.add_argument("--idea", required=True)
    x.add_argument("--note", required=True)
    x.add_argument("--by", **by)

    x = p(sub, "top", "화면1 weekly_top 1–20 산정")
    x.add_argument("--week", type=date.fromisoformat, default=None, help="기본: 이번 주(KST 월요일)")

    x = p(sub, "funnel", "단계별 통과 건수")
    x.add_argument("--as-of", type=int, default=None, help="카탈로그 snapshot_id(기본: 최신)")
    x.add_argument("--json", action="store_true")

    an = sub.add_parser("announce", help="공고(K-Startup)").add_subparsers(dest="sub", required=True)
    x = p(an, "fetch", "API 적재(DATA_GO_KR_KEY 필요)")
    x.add_argument("--pages", type=int, default=3)
    x = p(an, "add", "사람이 실제 공고 URL 입력(키 없을 때)")
    x.add_argument("--url", required=True)
    x.add_argument("--title", required=True)
    x.add_argument("--org")
    x.add_argument("--apply-from", type=date.fromisoformat)
    x.add_argument("--apply-to", type=date.fromisoformat)
    x.add_argument("--summary")
    x.add_argument("--by", **by)


def _run_funnel(a) -> int:
    from .egress import Egress
    dsn = a.dsn
    if a.cmd == "trace":
        if a.sub == "local":
            funnel.trace_local(dsn=dsn)
        elif a.sub == "refresh":
            funnel.trace_pending(dsn=dsn)
        else:
            print(funnel.trace_manual(dsn=dsn, idea_id=a.idea, result=a.result, status=a.status, url=a.url,
                                      note=a.note, by=a.by))
    elif a.cmd == "diagnose":
        if a.sub == "rule":
            funnel.diagnose_rule(dsn=dsn)
        else:
            funnel.diagnose_set(dsn=dsn, idea_id=a.idea, cause=a.cause, secondary=a.secondary,
                                rationale=a.rationale, evidence=a.evidence, by=a.by)
    elif a.cmd == "changes":
        with Egress.from_dsn(dsn) as eg:
            print(funnel.change_add(dsn=dsn, kind=a.kind, url=a.url, title=a.title, occurred_at=a.occurred_at,
                                    summary=a.summary, by=a.by, egress=eg, law_mst=a.law_mst))
    elif a.cmd == "match":
        if a.sub == "candidates":
            funnel.match_candidates(dsn=dsn)
        elif a.sub == "judge":
            funnel.match_judge(dsn=dsn, limit=a.limit)
        else:
            print(funnel.match_set(dsn=dsn, change_id=a.change, idea_id=a.idea, verdict=a.verdict,
                                   what_changed=a.what_changed, how_now=a.how_now, by=a.by))
    elif a.cmd == "score":
        axes = ("tech", "data", "regulation", "policy")
        sc = funnel.score_set(dsn=dsn, idea_id=a.idea, scores={k: getattr(a, k) for k in axes},
                              evidence={k: getattr(a, f"{k}_url") for k in axes if getattr(a, f"{k}_url")},
                              by=a.by, as_of=a.as_of)
        print(sc)
    elif a.cmd == "review":
        if a.sub == "approve":
            print(funnel.approve(dsn=dsn, idea_id=a.idea, by=a.by, note=a.note))
        else:
            funnel.reject(dsn=dsn, idea_id=a.idea, by=a.by, note=a.note)
    elif a.cmd == "top":
        funnel.compute_top(dsn=dsn, week=a.week or catalog.today_kst())
    elif a.cmd == "funnel":
        rep = funnel.report(dsn=dsn, as_of=a.as_of)
        print(funnel.dumps(rep)) if a.json else funnel.print_report(rep)
    elif a.cmd == "announce":
        if a.sub == "fetch":
            announce.fetch(dsn=dsn, pages=a.pages)
        else:
            with Egress.from_dsn(dsn) as eg:
                print(announce.add(dsn=dsn, url=a.url, title=a.title, org=a.org, apply_from=a.apply_from,
                                   apply_to=a.apply_to, summary=a.summary, by=a.by, egress=eg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
