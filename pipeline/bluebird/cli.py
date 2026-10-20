"""bluebird CLI.

- 경로·DSN: 인자 또는 환경변수(BB_*)
- 실행 주체: 처리 작업(./demo.sh job …)
- 외부 호출: egress 모듈만(허용 호스트·기록)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from . import announce, cards, coding, db, enrichment, export, funnel, ingest, kpi, sources_check
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


def _log_note(a: argparse.Namespace, results: dict | list[dict]) -> str:
    """db_log 한 줄: 넣은 옵션 + 소스별 상태·숫자 결과."""
    opts = " ".join(f"--{k} {getattr(a, k)}" for k in ("only", "skip", "sample") if getattr(a, k, None))
    parts = []
    for r in results if isinstance(results, list) else [results]:
        nums = " ".join(f"{k}={v}" for k, v in r.items() if isinstance(v, int) and not isinstance(v, bool))
        head = "".join(f"{r[k]} " for k in ("source", "status") if r.get(k))
        parts.append((head + nums).strip())
    return " ".join(x for x in (opts, "; ".join(p for p in parts if p)) if x)[:4000]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bluebird")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("migrate", help="SQL 마이그레이션 적용")
    m.add_argument("--target", choices=db.TARGETS, required=True)
    m.add_argument("--dsn", default=None, help="기본: core=BB_DSN, master=BB_MASTER_DSN")

    ms = sub.add_parser("master", help="정제 DB(parangsae): raw = 받은 그대로")
    mss = ms.add_subparsers(dest="master_cmd", required=True)
    for name, text in (("files", "수집해 둔 CSV·xlsx → raw(소스 단위 교체)"),
                       ("api", "API 응답 레코드 전체 → raw(국민신문고 = 일 한도 안에서 이어 받음)")):
        x = mss.add_parser(name, help=text)
        x.add_argument("--dsn", default=_env("BB_MASTER_DSN"))
        x.add_argument("--config", type=Path, action="append", required=True, help="레지스트리 TOML, 반복")
        x.add_argument("--only")
    x = mss.add_parser("detail", help="목록에 본문 없는 소스 → 공식 상세 페이지 본문(raw '<소스>.detail', 이어 받음)")
    x.add_argument("--dsn", default=_env("BB_MASTER_DSN"))
    x.add_argument("--core-dsn", default=_env("BB_DSN"), help="egress 정책·감사 기록")
    x.add_argument("--only")
    x.add_argument("--workers", type=int, default=4)
    x = mss.add_parser("fill", help="master LLM 컨럼(keyword·problem·feature·target·domain, 빈 contest)")
    x.add_argument("--dsn", default=_env("BB_MASTER_DSN"))
    x.add_argument("--core-dsn", default=_env("BB_DSN"), help="egress 정책·감사 기록")
    x.add_argument("--config", type=Path, action="append", required=True, help="레지스트리 TOML, 반복")
    x.add_argument("--only")
    x.add_argument("--skip", action="append", default=[], help="제외 소스, 반복")
    x.add_argument("--sample", type=int, help="소스별 N행만(시험)")
    x.add_argument("--workers", type=int, default=8)
    x = mss.add_parser("extract", help="AI 판정(quality.idea_label) + 가공 아이디어(idea_fields). 쓸 행 중 판정 전만. 다음 = reasons")
    x.add_argument("--dsn", default=_env("BB_MASTER_DSN"))
    x.add_argument("--core-dsn", default=_env("BB_DSN"), help="egress 정책·감사 기록")
    x.add_argument("--config", type=Path, action="append", required=True, help="레지스트리 TOML, 반복")
    x.add_argument("--only")
    x.add_argument("--sample", type=int, help="소스별 N행만(시험)")
    x.add_argument("--workers", type=int, default=8)
    x = mss.add_parser("refine", help="raw → master 정제(글머리 정리·마스킹, LLM 컨럼 유지)")
    x.add_argument("--dsn", default=_env("BB_MASTER_DSN"))
    x.add_argument("--config", type=Path, action="append", required=True, help="레지스트리 TOML, 반복")
    x.add_argument("--only")
    x = mss.add_parser("xlsx", help="master 표 전체 → 엑셀 1파일(시트 master, 필드 = docs/MASTER.md)")
    x.add_argument("--dsn", default=_env("BB_MASTER_DSN"))
    x.add_argument("--out", type=Path, required=True)
    x = mss.add_parser("reasons", help="전처리 사유(중복·품질)·대표 행·quality 측정값, 행 삭제 없음. refine 다음, 매번 전체 재계산")
    x.add_argument("--dsn", default=_env("BB_MASTER_DSN"))
    x = mss.add_parser("classify", help="대회·제도 분류(program, master.program_id). 매번 전체 재계산")
    x.add_argument("--dsn", default=_env("BB_MASTER_DSN"))
    x.add_argument("--config", type=Path, action="append", required=True, help="레지스트리 TOML, 반복")
    x = mss.add_parser("log", help="DB 작업 기록(db_log). --note 없으면 최근 기록 보기. master 명령·migrate는 자동 기록. "
                                     "적는 방식 = docs/MASTER.md 6장(= DB 주석 COMMENT ON TABLE db_log)")
    x.add_argument("--dsn", default=_env("BB_MASTER_DSN"))
    x.add_argument("--action", default="note", choices=("dump", "restore", "drop", "note"),
                   help="직접 적는 작업. 나머지(migrate·refine 등) = 자동")
    x.add_argument("--note", help="작업별 형식(MASTER.md 6장)")
    x.add_argument("--file", type=Path, help="덤프 파일. 있으면 sha256 계산. dump·restore 필수")
    x.add_argument("--sha256", help="파일이 여기 없을 때 sha256 직접")
    x.add_argument("--at", help="지난 일을 나중에 적을 때만. 예: '2026-10-19 12:16+09'. note에 (시각 추정: 근거)")
    x.add_argument("--place", help="기본 BB_LOG_PLACE, 없으면 호스트 이름")
    x.add_argument("--merge-from", metavar="DSN", help="복원 전 기존 DB의 기록 중 없는 행 옮기기")
    x.add_argument("--limit", type=int, default=20)
    mss.choices["files"].add_argument("--dir", type=Path, action="append", help="파일 찾을 디렉터리, 반복. 기본: BB_SIGNAL_DIR/contests, BB_SEED_DIR")
    mss.choices["api"].add_argument("--core-dsn", default=_env("BB_DSN"), help="egress 정책·감사 기록")
    mss.choices["api"].add_argument("--acrc-budget", type=int, default=int(_env("BB_ACRC_CALL_BUDGET") or 9000))

    i = sub.add_parser("ingest", help="seed 파일 → core 적재(마스킹·익명 ID)")
    i.add_argument("--dsn", default=_env("BB_DSN"))
    i.add_argument("--config", type=Path, action="append", help="기본 BB_SOURCES; --policy-only에서만 반복 가능")
    i.add_argument("--seed-dir", type=Path, default=_p("BB_SEED_DIR"))
    i.add_argument("--secret", type=Path, default=_p("BB_ANON_SECRET"))
    i.add_argument("--only")
    i.add_argument("--force", action="store_true", help="같은 파일도 다시 적재")
    i.add_argument("--allow-retire", action="store_true", help="절반 넘게 사라지는 퇴역 허용")
    i.add_argument("--policy-only", action="store_true",
                   help="파일 없이 레지스트리 정책(공개·반출·record_kind·exclude_reason)만 동기화 + 선별 재료 재계산. --config 반복 가능")
    i.add_argument("--retire", metavar="SOURCE_ID",
                   help="레지스트리에서 뺀 소스의 유효 아이디어 전부 퇴역(행·사람 판단 유지, 공개·내보내기·마커에서 제외)")

    co = sub.add_parser("collect", help="공식 공모·제안 원천 수집(분석·공개 승인 없음)")
    cos = co.add_subparsers(dest="collection", required=True)
    cc = cos.add_parser("contests", help="공식 파일 검증·원자적 저장 후 기존 적재 실행")
    cc.add_argument("--config", type=Path, action="append", help="반복 가능; 기본 BB_CONTEST_SOURCES")
    cc.add_argument("--out-dir", type=Path,
                    default=(_p("BB_SIGNAL_DIR") / "contests") if _p("BB_SIGNAL_DIR") else None)
    cc.add_argument("--dsn", default=_env("BB_DSN"))
    cc.add_argument("--secret", type=Path, default=_p("BB_ANON_SECRET"))
    cc.add_argument("--only")
    cc.add_argument("--download-only", action="store_true", help="검증·egress 감사는 수행하고 DB 적재만 생략")

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

    ex = sub.add_parser("export", help="공유용 내보내기(읽기 전용)")
    exs = ex.add_subparsers(dest="export_cmd", required=True)
    ex1 = exs.add_parser("xlsx", help="아이디어 전체 + 선별 재료를 엑셀 한 파일로")
    ex1.add_argument("--dsn", default=_env("BB_DSN"))
    ex1.add_argument("--out", type=Path, required=True)
    ex2 = exs.add_parser("provenance", help="docs/DATA.md: 소스별 원본·정제·중복 제외 건수(master·raw)")
    ex2.add_argument("--dsn", default=_env("BB_MASTER_DSN"))
    ex2.add_argument("--config", type=Path, action="append", help="레지스트리 TOML, 반복 가능; 기본 BB_SOURCES+BB_CONTEST_SOURCES")
    ex2.add_argument("--out", type=Path, required=True)

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

    cd = sub.add_parser("coding", help="κ 표본(2인 독립 코딩)")
    cds = cd.add_subparsers(dest="sub", required=True)
    x = cds.add_parser("sample", help="모집단에서 층화 표본 생성(seed 기록)")
    x.add_argument("--dsn", default=_env("BB_DSN"))
    x.add_argument("--size", type=int, default=100)
    x.add_argument("--seed", type=int, required=True)
    x.add_argument("--sample-id")

    x = sub.add_parser("kappa", help="G3 κ: 표본 2인 코딩 일치도. 표본 없으면 --sample·--seed로 생성")
    x.add_argument("--dsn", default=_env("BB_DSN"))
    x.add_argument("--sample", type=int, default=100, help="표본 크기")
    x.add_argument("--seed", type=int, required=True)
    x.add_argument("--sample-id")
    x.add_argument("--json", action="store_true")

    ev = sub.add_parser("eval", help="평가").add_subparsers(dest="sub", required=True)
    x = ev.add_parser("goldset", help="G4 흔적 골드셋(파일럿 50건) 혼동행렬·macro-F1. 파일은 읽기만(팀명 저장 안 함)")
    x.add_argument("--dsn", default=_env("BB_DSN"))
    x.add_argument("--gold", required=True, help="CSV 경로, '-'면 표준입력")
    x.add_argument("--baseline", action="store_true", help="이번 결과를 기준선으로 기록")

    kp = sub.add_parser("kpi", help="KPI").add_subparsers(dest="sub", required=True)
    x = kp.add_parser("report", help="G1–G13 현황표(사람 입력 대기 = human_blocked)")
    x.add_argument("--dsn", default=_env("BB_DSN"))
    x.add_argument("--kappa-sample", help="G3 기준 표본 id(없으면 100건 이상 중 최근)")
    # G10 성명 대조: 원본 파일·익명화 키 필요(처리 작업 전용). 없으면 G10 진행 중
    x.add_argument("--config", type=Path, default=_p("BB_SOURCES"))
    x.add_argument("--seed-dir", type=Path, default=_p("BB_SEED_DIR"))
    x.add_argument("--secret", type=Path, default=_p("BB_ANON_SECRET"))
    x.add_argument("--json", action="store_true")

    _funnel_parsers(sub)
    a = ap.parse_args(argv)
    if a.cmd in FUNNEL_CMDS:
        _require(ap, a, "dsn")
        if a.cmd == "score":
            if a.mode is None:
                _require(ap, a, "idea", "by")
            elif a.by or any(getattr(a, axis) is not None or getattr(a, f"{axis}_url")
                             for axis in ("tech", "data", "regulation", "policy")):
                ap.error("score auto cannot be combined with manual scores, URLs or --by")
        return _run_funnel(a)

    if a.cmd == "migrate":
        dsn = a.dsn or _env({"core": "BB_DSN", "master": "BB_MASTER_DSN"}[a.target])
        if not dsn:
            ap.error("missing --dsn")
        applied = db.migrate(dsn, a.target)
        print("applied:", applied or "nothing")
        if applied and a.target == "master":
            from . import dblog

            dblog.write(dsn=dsn, action="migrate", note="master " + ", ".join(applied))
    elif a.cmd == "master":
        from . import dblog, master
        from .egress import Egress

        _require(ap, a, "dsn")
        if a.master_cmd == "log":
            if a.merge_from:
                print(funnel.dumps(dblog.merge(dsn=a.dsn, src_dsn=a.merge_from)))
            elif a.note:
                if a.action in ("dump", "restore") and not a.file:
                    ap.error(f"--action {a.action}: --file 필수")
                print(funnel.dumps(dblog.write(dsn=a.dsn, action=a.action, note=a.note, file=a.file, digest=a.sha256,
                                               where=a.place, at=a.at)))
            else:
                for row in dblog.recent(dsn=a.dsn, limit=a.limit):
                    print(" | ".join("" if v is None else str(v) for v in row))
            return 0
        if a.master_cmd == "detail":
            _require(ap, a, "core_dsn")
            with Egress.from_dsn(a.core_dsn, cookies=False) as eg:
                results = master.load_detail(dsn=a.dsn, egress=eg, only=a.only, workers=a.workers)
            for result in results:
                print(funnel.dumps(result))
            dblog.write(dsn=a.dsn, action="detail", note=_log_note(a, results))
            return 0
        if a.master_cmd == "xlsx":
            print("[export]", export.master_xlsx(dsn=a.dsn, out=a.out))
            return 0
        if a.master_cmd == "reasons":
            from . import dedup

            result = dedup.mark(dsn=a.dsn)
            print(funnel.dumps(result))
            dblog.write(dsn=a.dsn, action="reasons", note=_log_note(a, result))
            return 0
        if a.master_cmd == "classify":
            from . import programs

            result = programs.classify(dsn=a.dsn, sources=master.registry(a.config))
            print(funnel.dumps(result))
            dblog.write(dsn=a.dsn, action="classify", note=_log_note(a, result))
            return 0
        sources = master.registry(a.config)
        if a.master_cmd == "files":
            dirs = a.dir or [p for p in ((_p("BB_SIGNAL_DIR") / "contests") if _p("BB_SIGNAL_DIR") else None,
                                         _p("BB_SEED_DIR")) if p]
            if not dirs:
                ap.error("missing --dir")
            results = master.load_files(dsn=a.dsn, sources=sources, dirs=dirs, only=a.only)
        elif a.master_cmd == "fill":
            from . import fill

            _require(ap, a, "core_dsn")
            with Egress.from_dsn(a.core_dsn, timeout=180.0) as eg:
                results = fill.fill(dsn=a.dsn, egress=eg, sources=sources, only=a.only, skip=a.skip,
                                    sample=a.sample, workers=a.workers)
        elif a.master_cmd == "extract":
            from . import extract

            _require(ap, a, "core_dsn")
            with Egress.from_dsn(a.core_dsn, timeout=180.0) as eg:
                results = extract.extract(dsn=a.dsn, egress=eg, sources=sources, only=a.only, sample=a.sample,
                                          workers=a.workers)
        elif a.master_cmd == "refine":
            from . import refine

            results = refine.refine(dsn=a.dsn, sources=sources, only=a.only)
        else:
            _require(ap, a, "core_dsn")
            with Egress.from_dsn(a.core_dsn) as eg:
                results = master.load_api(dsn=a.dsn, egress=eg, sources=sources, only=a.only,
                                          acrc_budget=a.acrc_budget)
        for result in results:
            print(funnel.dumps(result))
        # db_log 작업 목록(0009)에 extract 없음 → LLM 단계 = fill로 기록, 내용 앞에 명령 이름
        action = "fill" if a.master_cmd == "extract" else a.master_cmd
        note = ("extract " if a.master_cmd == "extract" else "") + _log_note(a, results)
        dblog.write(dsn=a.dsn, action=action, note=note)
        return 1 if any(r["status"] != "ok" for r in results) else 0
    elif a.cmd == "ingest":
        if a.config is None and _p("BB_SOURCES"):
            a.config = [_p("BB_SOURCES")]
        if a.retire:
            _require(ap, a, "dsn")
            ingest.retire_source(dsn=a.dsn, source_id=a.retire)
        elif a.policy_only:
            _require(ap, a, "dsn", "config")
            ingest.sync_policy(dsn=a.dsn, configs=a.config)
        else:
            _require(ap, a, "dsn", "config", "seed_dir", "secret")
            if len(a.config) != 1:
                ap.error("ingest takes one --config unless --policy-only")
            ingest.ingest(dsn=a.dsn, config=a.config[0], seed_dir=a.seed_dir, secret_path=a.secret, only=a.only,
                          force=a.force, allow_retire=a.allow_retire)
    elif a.cmd == "collect":
        from .collection import MAX_DOWNLOAD_BYTES, collect_contests
        from .egress import Egress

        if a.config is None and _p("BB_CONTEST_SOURCES"):
            a.config = [_p("BB_CONTEST_SOURCES")]
        _require(ap, a, "dsn", "config", "out_dir", "secret")
        with Egress.from_dsn(a.dsn, max_bytes=MAX_DOWNLOAD_BYTES) as eg:
            results = collect_contests(configs=a.config, out_dir=a.out_dir, secret_path=a.secret,
                                       dsn=a.dsn, egress=eg, only=a.only, download_only=a.download_only)
        for result in results:
            print(funnel.dumps(result))
        return 1 if any(r["status"] == "error" for r in results) else 0
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
    elif a.cmd == "coding":
        _require(ap, a, "dsn")
        coding.make_sample(dsn=a.dsn, size=a.size, seed=a.seed, sample_id=a.sample_id)
    elif a.cmd == "kappa":
        _require(ap, a, "dsn")
        sid = a.sample_id or f"k{a.sample}-s{a.seed}"
        with db.connect(a.dsn) as conn:
            exists = conn.execute("SELECT 1 FROM core.coding_sample WHERE sample_id=%s LIMIT 1", (sid,)).fetchone()
        if not exists:
            coding.make_sample(dsn=a.dsn, size=a.sample, seed=a.seed, sample_id=sid)
        r = kpi.kappa(dsn=a.dsn, sample_id=sid)
        print(funnel.dumps(r) if a.json else
              f"[kappa] {sid}: κ={r['kappa']} 코딩 {r['coded_pairs']}/{r['size']} "
              f"(A {r['coded_a']}, B {r['coded_b']}) 코드별 {r['per_code_agreement']} U {r['u_share']} → {r['status']}")
        return 1 if r["status"] == kpi.FAIL else 0
    elif a.cmd == "eval":
        _require(ap, a, "dsn")
        text = sys.stdin.read() if a.gold == "-" else Path(a.gold).read_text(encoding="utf-8-sig")
        r = kpi.goldset(dsn=a.dsn, gold_csv=text, baseline=a.baseline)
        print(funnel.dumps(r))
        return 1 if r["status"] == kpi.FAIL else 0
    elif a.cmd == "kpi":
        _require(ap, a, "dsn")
        names = None
        if a.config and a.seed_dir and a.secret and a.secret.exists():
            with db.connect(a.dsn) as conn:
                names = kpi.name_leaks(conn, config=a.config, seed_dir=a.seed_dir, secret=ingest.load_secret(a.secret))
        rows = kpi.report(dsn=a.dsn, kappa_sample=a.kappa_sample, names=names)
        if a.json:
            print(funnel.dumps(rows))
        else:
            kpi.print_report(rows)
        return 1 if any(r["status"] == kpi.FAIL for r in rows) else 0
    elif a.cmd == "export":
        _require(ap, a, "dsn")
        if a.export_cmd == "xlsx":
            print("[export]", export.xlsx(dsn=a.dsn, out=a.out))
        else:
            cfgs = a.config or [p for p in (_p("BB_SOURCES"), _p("BB_CONTEST_SOURCES")) if p]
            print("[export]", export.provenance(dsn=a.dsn, configs=cfgs, out=a.out))
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


FUNNEL_CMDS = ("trace", "diagnose", "changes", "match", "score", "review", "funnel", "announce")


def _ev(s: str) -> tuple[str, str | None]:
    url, _, excerpt = s.partition("|")
    return url.strip(), excerpt.strip() or None


def _funnel_parsers(sub) -> None:
    def p(parent, name, help_):
        x = parent.add_parser(name, help=help_)
        x.add_argument("--dsn", default=_env("BB_DSN"))
        return x

    by = {"required": True, "help": "입력한 사람(감사 기록)"}
    def auto(parent):
        x = p(parent, "auto", "키가 있을 때만 근거 기반 자동 제안(승인 없음)")
        x.add_argument("--idea", help="단일 아이디어 선택")
        x.add_argument("--limit", type=int, choices=range(1, enrichment.MAX_LIMIT + 1), default=1)
        return x

    t = sub.add_parser("trace", help="1 흔적").add_subparsers(dest="sub", required=True)
    p(t, "local", "kipris_local_v1: ip_local + similar_local(외부 호출 없음)")
    p(t, "refresh", "full_v1 판정 재계산(필수 항목 미실행이면 pending)")
    auto(t)
    x = p(t, "manual", "사람이 외부 검색한 결과 입력")
    x.add_argument("--idea", required=True)
    x.add_argument("--item", choices=("manual", "news_web", "ip"), default="manual",
                   help="직접 수행한 검색 항목; 최종 해석은 manual")
    x.add_argument("--result", choices=("found", "none"), required=True)
    x.add_argument("--status", choices=("realized", "pivot", "similar_unlinked", "award_only", "none"))
    x.add_argument("--url")
    x.add_argument("--note", required=True)
    x.add_argument("--by", **by)

    d = sub.add_parser("diagnose", help="2 막힌 이유").add_subparsers(dest="sub", required=True)
    p(d, "rule", "본문 missing_data → 원인 D 제안(근거 = 본문 문장)")
    auto(d)
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
    x.add_argument("--law-mst", help="law_effective: 국가법령정보 법령일련번호(MST). 시행일자 API 대조")
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
    x.add_argument("mode", nargs="?", choices=("auto",))
    x.add_argument("--idea")
    x.add_argument("--limit", type=int, choices=range(1, enrichment.MAX_LIMIT + 1), default=1)
    for axis in ("tech", "data", "regulation", "policy"):
        x.add_argument(f"--{axis}", type=int)
        x.add_argument(f"--{axis}-url")
    x.add_argument("--as-of", type=date.fromisoformat)
    x.add_argument("--by", help="사람 채점 시 필수(감사 기록)")

    r = sub.add_parser("review", help="5 검토·승인").add_subparsers(dest="sub", required=True)
    x = p(r, "approve", "최종 승인 → 공개 대상")
    x.add_argument("--idea", required=True)
    x.add_argument("--note")
    x.add_argument("--by", **by)
    x = p(r, "reject", "반려(공개 철회)")
    x.add_argument("--idea", required=True)
    x.add_argument("--note", required=True)
    x.add_argument("--by", **by)

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
    if (a.cmd in ("trace", "diagnose") and a.sub == "auto") or (a.cmd == "score" and a.mode == "auto"):
        fn = {"trace": enrichment.trace_auto, "diagnose": enrichment.diagnose_auto,
              "score": enrichment.score_auto}[a.cmd]
        options = {"as_of": a.as_of} if a.cmd == "score" else {}
        result = fn(dsn=dsn, idea_id=a.idea, limit=a.limit, **options)
        print(funnel.dumps(result))
        return 1 if result.get("key_required") or result.get("failed") else 0
    if a.cmd == "trace":
        if a.sub == "local":
            funnel.trace_local(dsn=dsn)
        elif a.sub == "refresh":
            funnel.trace_pending(dsn=dsn)
        else:
            print(funnel.trace_manual(dsn=dsn, idea_id=a.idea, result=a.result, status=a.status, url=a.url,
                                      note=a.note, by=a.by, item=a.item))
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
