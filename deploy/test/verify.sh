#!/usr/bin/env bash
# 시험 배포 검증: 망분리(egress 차단)·반출 통제·공개 화면.
set -euo pipefail
cd "$(dirname "$0")"
dc() { docker compose --env-file .env "$@"; }
port="$(grep BB_HTTP_PORT .env | cut -d= -f2)"
fail=0
check() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; fail=1; fi; }

probe='import socket,sys
try:
    socket.create_connection(("1.1.1.1",443),timeout=3); print("reachable"); sys.exit(0)
except OSError: print("blocked"); sys.exit(1)'
egress() { dc --profile jobs run --rm --no-deps --entrypoint python "$1" -c "$probe" >/dev/null 2>&1; }

check "Z1 collector 외부 통신 가능"   "egress collector"
check "Z2 worker 외부 통신 차단"      "! egress worker"
check "Z3 importer 외부 통신 차단"    "! egress importer"
check "망연계 mover 네트워크 없음"     "! egress mover-12"

core_sql() { dc exec -T core-db psql -U bluebird -d bluebird_core -tAc "$1"; }
pub_sql()  { dc exec -T publish-db psql -U bluebird -d bluebird_publish -tAc "$1"; }

core_n="$(core_sql 'SELECT count(*) FROM core.idea')"
pub_n="$(pub_sql 'SELECT count(*) FROM publish.idea')"
allowed="$(core_sql 'SELECT count(*) FROM core.idea i JOIN core.source s ON s.id=i.source_id WHERE s.public_ok')"
echo "      core.idea=$core_n publish.idea=$pub_n (public_ok=$allowed)"
check "공개존 = 처리존의 공개 허용분" "[[ $pub_n -eq $allowed && $pub_n -gt 0 ]]"
check "비공개 소스 미반출" "[[ \$(pub_sql \"SELECT count(*) FROM publish.idea WHERE source_id='kipris_contest_idea_bulk'\") -eq 0 ]]"
check "공개존 컬럼에 team_kind·extra 없음" \
  "[[ \$(pub_sql \"SELECT count(*) FROM information_schema.columns WHERE table_schema='publish' AND column_name IN ('team_kind','extra','first_bundle_id')\") -eq 0 ]]"
check "포털 계정 쓰기 불가" \
  "! dc exec -T -e PGPASSWORD=\$(grep PORTAL_DB_PASSWORD .env | cut -d= -f2) publish-db psql -h localhost -U bluebird_portal -d bluebird_publish -c \"DELETE FROM publish.idea\" >/dev/null 2>&1"

code() { curl -s -o /dev/null -w '%{http_code}' "http://localhost:$port$1"; }
check "GET /pool 200" "[[ \$(code /pool) == 200 ]]"
first="$(curl -s "http://localhost:$port/api/v1/ideas" | python3 -c 'import json,sys; print(json.load(sys.stdin)["items"][0]["id"])')"
check "GET /ideas/$first 200" "[[ \$(code /ideas/$first) == 200 ]]"
check "GET /api/v1/ideas/없는ID 404" "[[ \$(code /api/v1/ideas/ID-0000-none) == 404 ]]"
check "DELETE 메서드 405" "[[ \$(curl -s -o /dev/null -w '%{http_code}' -X DELETE http://localhost:$port/pool) == 405 ]]"
check "보안 헤더(CSP)" "curl -sI http://localhost:$port/pool | grep -qi content-security-policy"
check "서버 버전 미노출" "! curl -sI http://localhost:$port/pool | grep -qiE '^server: nginx/[0-9]'"
exit $fail
