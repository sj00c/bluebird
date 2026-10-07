#!/usr/bin/env bash
# 시험 배포 현황: 컨테이너 상태 + 구역별 적재 건수 + 도식·포털 열기
set -euo pipefail
cd "$(dirname "$0")"
dc() { docker compose --env-file .env "$@"; }
clear
echo "=== 파랑새 시험 배포 상태 ==="
dc ps --format 'table {{.Service}}\t{{.State}}\t{{.Ports}}'
echo
echo "업무망 core.idea   : $(dc exec -T core-db psql -U bluebird -d bluebird_core -tAc 'select count(*) from core.idea')"
echo "DMZ   publish.idea : $(dc exec -T publish-db psql -U bluebird -d bluebird_publish -tAc 'select count(*) from publish.idea')"
echo
open ../../docs/diagrams/architecture.html "http://localhost:$(grep BB_HTTP_PORT .env | cut -d= -f2)/pool"
