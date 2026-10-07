#!/usr/bin/env bash
# 시험 배포 1회 수집 주기 실행: Z1 수집 → 망연계 → Z2 적재 → 반출 → 망연계 → Z3 적재.
# 운영에서는 같은 명령을 구역별 systemd timer가 실행한다(docs/DEPLOYMENT.md §6).
set -euo pipefail
cd "$(dirname "$0")"
dc() { docker compose --env-file .env "$@"; }
job() { dc --profile jobs run --rm --no-deps "$@"; }

dc up -d --wait core-db publish-db
job worker migrate --target core
job importer migrate --target publish

job collector collect "$@"
job mover-12
job worker import-core
job worker publish
job mover-23
job importer import-publish

dc up -d --wait portal nginx
echo "[cycle] done. http://localhost:$(grep BB_HTTP_PORT .env | cut -d= -f2)/pool"
