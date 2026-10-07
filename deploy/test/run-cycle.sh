#!/usr/bin/env bash
# 시험 배포 1회 주기: 마이그레이션 → 원본 적재 → 신호(스냅샷) → 공개용 DB 반영 → 포털.
# 운영에서는 같은 명령을 업무망 systemd timer가 실행한다(docs/DEPLOYMENT.md).
set -euo pipefail
cd "$(dirname "$0")"
dc() { docker compose --env-file .env "$@"; }
job() { dc --profile jobs run --rm backend-jobs "$@"; }

dc build -q backend-jobs portal
dc up -d --wait core-db publish-db proxy
job migrate --target core
job migrate --target publish

job ingest "$@"
# 스냅샷 #0은 한 번만 적재된다(같은 sha256이면 건너뜀).
job signals catalog-import --file /seed/catalog_snapshot0_2026-10-06.csv --taken-at 2026-10-06
job publish

dc up -d --wait portal nginx
echo "[cycle] done. http://localhost:$(grep BB_HTTP_PORT .env | cut -d= -f2)/pool"
