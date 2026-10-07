#!/usr/bin/env bash
# 목록개방현황 주간 스냅샷(월요일). egress → 프록시로 내려받아 diff → observed_new/reappeared → condition_change.
# 같은 파일(sha256)이면 적재하지 않는다(포털 파일은 월 단위 갱신으로 보임: 2026-10-07 받은 파일 = 스냅샷 #0).
# 시험 환경 예약(호스트 crontab): 0 6 * * 1 /path/to/deploy/test/snapshot.sh >> /tmp/bb-snapshot.log 2>&1
# 운영은 업무망 systemd timer(bluebird-signals.timer)가 같은 명령을 실행한다.
set -euo pipefail
cd "$(dirname "$0")"
docker compose --env-file .env --profile jobs run --rm -T backend-jobs signals catalog-fetch "$@"
