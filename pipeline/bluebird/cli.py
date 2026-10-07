"""bluebird CLI. 경로·DSN은 인자 또는 환경변수(BB_*)로 받는다. 구역별 컨테이너/서버에서 같은 CLI를 쓴다."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from . import db, stages
from .bundle import ZONES, generate_keypair, move_bundles


def _env(name: str) -> str | None:
    return os.environ.get(name)


def _p(name: str):
    v = _env(name)
    return Path(v) if v else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bluebird")
    sub = ap.add_subparsers(dest="cmd", required=True)

    k = sub.add_parser("keygen", help="구역 서명키 생성 (+ z1 익명화 비밀키)")
    k.add_argument("--zone", choices=ZONES, required=True)
    k.add_argument("--dir", type=Path, required=True)

    m = sub.add_parser("migrate", help="SQL 마이그레이션 적용")
    m.add_argument("--target", choices=db.TARGETS, required=True)
    m.add_argument("--dsn", default=_env("BB_DSN"))

    c = sub.add_parser("collect", help="[z1] 파일 소스 수집 → collect 번들")
    c.add_argument("--config", type=Path, default=_p("BB_SOURCES"))
    c.add_argument("--seed-dir", type=Path, default=_p("BB_SEED_DIR"))
    c.add_argument("--state-dir", type=Path, default=_p("BB_STATE_DIR"))
    c.add_argument("--outbox", type=Path, default=_p("BB_OUTBOX"))
    c.add_argument("--key", type=Path, default=_p("BB_SIGN_KEY"))
    c.add_argument("--secret", type=Path, default=_p("BB_ANON_SECRET"))
    c.add_argument("--force", action="store_true")

    mv = sub.add_parser("move", help="[시험 환경] outbox → inbox 이동 (망연계 대체)")
    mv.add_argument("--src", type=Path, required=True)
    mv.add_argument("--dst", type=Path, required=True)

    for name, zone_help in (("import-core", "[z2] collect 번들 적재"), ("import-publish", "[z3] publish 번들 적재")):
        i = sub.add_parser(name, help=zone_help)
        i.add_argument("--inbox", type=Path, default=_p("BB_INBOX"))
        i.add_argument("--done-dir", type=Path, default=_p("BB_DONE_DIR"))
        i.add_argument("--quarantine-dir", type=Path, default=_p("BB_QUARANTINE_DIR"))
        i.add_argument("--peer-key", type=Path, default=_p("BB_PEER_PUBKEY"), help="보낸 구역의 공개키")
        i.add_argument("--dsn", default=_env("BB_DSN"))

    pb = sub.add_parser("publish", help="[z2] 공개 스냅샷 → publish 번들")
    pb.add_argument("--dsn", default=_env("BB_DSN"))
    pb.add_argument("--outbox", type=Path, default=_p("BB_OUTBOX"))
    pb.add_argument("--key", type=Path, default=_p("BB_SIGN_KEY"))

    a = ap.parse_args(argv)
    missing = [n for n, v in vars(a).items() if v is None]
    if missing:
        ap.error(f"missing required options/env: {', '.join(missing)}")

    if a.cmd == "keygen":
        priv, pub = generate_keypair(a.dir, a.zone)
        print(f"{priv}\n{pub}")
        if a.zone == "z1":
            secret = a.dir / "z1.anon_secret"
            if not secret.exists():
                secret.write_text(secrets.token_hex(32))
                os.chmod(secret, 0o600)
            print(secret)
    elif a.cmd == "migrate":
        print("applied:", db.migrate(a.dsn, a.target) or "nothing")
    elif a.cmd == "collect":
        stages.collect(config=a.config, seed_dir=a.seed_dir, state_dir=a.state_dir, outbox=a.outbox,
                       key_path=a.key, secret_path=a.secret, force=a.force)
    elif a.cmd == "move":
        for p in move_bundles(a.src, a.dst):
            print(f"[move] {p.name}")
    elif a.cmd in ("import-core", "import-publish"):
        fn = stages.import_core if a.cmd == "import-core" else stages.import_publish
        try:
            results = fn(inbox=a.inbox, done_dir=a.done_dir, quarantine_dir=a.quarantine_dir,
                         public_key_path=a.peer_key, dsn=a.dsn)
        except stages.QuarantinedBundlesError as e:
            print(f"[import] {e}", file=sys.stderr)
            return 2
        if any(r["status"] != "ok" for r in results):
            return 2
    elif a.cmd == "publish":
        stages.publish(dsn=a.dsn, outbox=a.outbox, key_path=a.key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
