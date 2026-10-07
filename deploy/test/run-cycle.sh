#!/usr/bin/env bash
# 시험 배포 1회 주기: 마이그레이션 → 원본 적재 → 신호(스냅샷) → 공개용 DB 반영 → 포털.
# 운영에서는 같은 명령을 업무망 systemd timer가 실행한다(docs/DEPLOYMENT.md).
set -euo pipefail
cd "$(dirname "$0")"
dc() { docker compose --env-file .env "$@"; }
job() { dc --profile jobs run --rm backend-jobs "$@"; }

dc build -q backend-jobs portal console
dc up -d --wait core-db publish-db proxy
job migrate --target core
# backend-api 전용 역할(0008)에 로그인 비밀번호를 준다(.env API_DB_PASSWORD).
# 비밀번호는 명령줄(ps에 보임)이 아니라 stdin으로 넘긴다.
printf "\\set pw '%s'\nALTER ROLE bb_api LOGIN PASSWORD :'pw';\n" "$(grep ^API_DB_PASSWORD= .env | cut -d= -f2)" \
  | dc exec -T core-db psql -U bluebird -d bluebird_core -v ON_ERROR_STOP=1 -q
job migrate --target publish

job ingest "$@"
job cards
# 어떤 소스가 실제로 불러와지는지 점검(must 실패 시 종료코드 2 — 판정은 verify.sh)
job sources check || echo "[cycle] sources check: must source failing (see table)"
# 스냅샷 #0은 한 번만 적재된다(같은 sha256이면 건너뜀).
job signals catalog-import --file /seed/catalog_snapshot0_2026-10-06.csv --taken-at 2026-10-06
# 국민 이의: DMZ inbox → 업무망 core(검증·상한), 가져온 행은 DMZ에서 삭제. 처리 결과는 이번 publish에 반영.
job objections pull
job publish

dc up -d --wait portal nginx
dc up -d --wait --force-recreate backend-api console console-gw
echo "[cycle] done. http://localhost:$(grep BB_HTTP_PORT .env | cut -d= -f2)/pool  console: http://127.0.0.1:$(grep BB_CONSOLE_PORT .env | cut -d= -f2)"
