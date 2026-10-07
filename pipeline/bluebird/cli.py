"""bluebird CLI. 경로·DSN은 인자 또는 환경변수(BB_*)로 받는다.

업무망 backend-jobs가 실행한다. 외부 호출은 egress 모듈을 거쳐 DMZ 프록시로만 나간다.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from . import cards, db, ingest, publish, sources_check
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
    i.add_argument("--force", action="store_true")

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

    a = ap.parse_args(argv)

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
                      force=a.force)
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


if __name__ == "__main__":
    sys.exit(main())
