#!/usr/bin/env bash
# 시험 배포 검증: 망구성(인바운드 0·단일 출구)·DB 역할·반출 통제·공개 화면.
set -uo pipefail
cd "$(dirname "$0")"
dc() { docker compose --env-file .env "$@" </dev/null; }
env_get() { grep "^$1=" .env | cut -d= -f2; }
port="$(env_get BB_HTTP_PORT)"
fail=0
check() { if eval "$2" >/dev/null 2>&1; then echo "PASS  $1"; else echo "FAIL  $1"; fail=1; fi; }

# ---------------------------------------------------------------- 망: 접속 시도 도구
# DMZ 컨테이너(portal: node)에서 TCP 접속 시도. 성공하면 0.
node_tcp() { dc exec -T portal node -e "
const s=require('net').connect({host:'$1',port:$2,timeout:3000},()=>{s.destroy();process.exit(0)});
s.on('error',()=>process.exit(1));s.on('timeout',()=>process.exit(1));"; }
nginx_tcp() { dc exec -T nginx sh -c "nc -z -w 3 $1 $2"; }
jobs_py() { dc --profile jobs run --rm --no-deps -T --entrypoint python backend-jobs -c "$1"; }
py_tcp='import socket,sys
try: socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=3); sys.exit(0)
except OSError: sys.exit(1)'
jobs_tcp() { dc --profile jobs run --rm --no-deps -T --entrypoint python backend-jobs -c "$py_tcp" "$1" "$2"; }
proxy_get() { dc --profile jobs run --rm --no-deps -T --entrypoint python backend-jobs -c "
import httpx,sys
try:
    r=httpx.get('$1',proxy='http://proxy:3128',timeout=10,trust_env=False); sys.exit(0 if r.status_code<500 else 1)
except Exception: sys.exit(1)"; }

echo "== 망구성"
check "DMZ portal → 업무망 core-db 접속 불가"         "! node_tcp core-db 5432"
check "DMZ nginx → 업무망 core-db 접속 불가"          "! nginx_tcp core-db 5432"
check "DMZ portal → 프록시 접속 불가"                  "! node_tcp proxy 3128"
check "DMZ portal → 인터넷 직접 불가"                  "! node_tcp 1.1.1.1 443"
check "DMZ portal → 공개용 DB 접속 가능"               "node_tcp publish-db 5432"
check "업무망 backend-jobs → 인터넷 직접 불가"         "! jobs_tcp 1.1.1.1 443"
check "업무망 backend-jobs → 공개용 DB 가능(push)"     "jobs_tcp publish-db 5432"
check "프록시 경유 허용 도메인(data.go.kr) 가능"      "proxy_get https://www.data.go.kr/"
check "프록시 경유 비허용 도메인(example.com) 거부"   "! proxy_get https://example.com/"
check "프록시 접근 로그에 허용·거부 기록" \
  "dc exec -T proxy grep -q 'www.data.go.kr' /var/log/squid/access.log && dc exec -T proxy grep -q 'TCP_DENIED' /var/log/squid/access.log"
squid_hosts="$(grep -E '^acl bb_whitelist' proxy/squid.conf | sed 's/acl bb_whitelist dstdomain//' | tr ' ' '\n' | sed 's/^\.//' | grep . | sort | tr '\n' ' ')"
app_hosts="$(cd ../../pipeline && uv run --quiet python -c 'from bluebird.egress import ALLOWED_HOSTS; print(" ".join(sorted(ALLOWED_HOSTS)))')"
echo "      proxy=[$squid_hosts] app=[$app_hosts ]"
check "프록시 화이트리스트 = egress ALLOWED_HOSTS"     "[[ '$squid_hosts' == '$app_hosts ' ]]"

echo "== 공개용 DB 역할"
pub_as() { dc exec -T -e PGPASSWORD="$(env_get "$2")" publish-db psql -h localhost -U "$1" -d bluebird_publish -v ON_ERROR_STOP=1 -tAc "$3"; }
check "superuser 원격 로그인 거부"                     "! pub_as bluebird PUBLISH_DB_PASSWORD 'select 1'"
check "portal: publish 읽기 가능"                      "pub_as bb_portal PORTAL_DB_PASSWORD 'select count(*) from publish.idea'"
check "portal: publish 쓰기 불가"                      "! pub_as bb_portal PORTAL_DB_PASSWORD 'delete from publish.idea'"
check "portal: inbox 읽기 불가"                        "! pub_as bb_portal PORTAL_DB_PASSWORD 'select * from inbox.objection'"
check "publisher: inbox 접근 불가"                     "! pub_as bb_publisher PUBLISHER_DB_PASSWORD 'select * from inbox.objection'"
check "inbox_reader: publish 쓰기 불가"                "! pub_as bb_inbox_reader INBOX_DB_PASSWORD 'delete from publish.idea'"
check "portal: meta 템플릿 등록 불가"                  "! pub_as bb_portal PORTAL_DB_PASSWORD \"insert into meta.publish_template values ('x','y')\""

echo "== 반출 통제·데이터"
core_sql() { dc exec -T core-db psql -U bluebird -d bluebird_core -tAc "$1"; }
pub_sql()  { dc exec -T publish-db psql -U bluebird -d bluebird_publish -tAc "$1"; }
core_n="$(core_sql 'SELECT count(*) FROM core.idea')"
pub_n="$(pub_sql 'SELECT count(*) FROM publish.idea')"
allowed="$(core_sql 'SELECT count(*) FROM core.idea i JOIN core.source s ON s.id=i.source_id WHERE s.public_ok')"
echo "      core.idea=$core_n publish.idea=$pub_n (public_ok=$allowed)"
check "공개용 DB = core 공개 허용분"                   "[[ $pub_n -eq $allowed && $pub_n -gt 0 ]]"
check "비공개 소스(KIPRIS) 미반영" \
  "[[ \$(pub_sql \"SELECT count(*) FROM publish.idea WHERE source_id='kipris_contest_idea_bulk'\") -eq 0 ]]"
check "공개용 DB에 내부 열 없음(team_kind·extra·ingest·export_grade)" \
  "[[ \$(pub_sql \"SELECT count(*) FROM information_schema.columns WHERE table_schema='publish' AND column_name IN ('team_kind','extra','first_ingest_id','last_ingest_id','export_grade','policy_approved_by')\") -eq 0 ]]"
check "공개 소스는 모두 정책 승인 기록 있음" \
  "[[ \$(core_sql 'SELECT count(*) FROM core.source WHERE public_ok AND policy_approved_at IS NULL') -eq 0 ]]"
check "publish_prev·publish_next 잔존 없음" \
  "[[ \$(pub_sql \"SELECT count(*) FROM pg_namespace WHERE nspname IN ('publish_prev','publish_next')\") -eq 0 ]]"
check "snapshot_log ↔ core.publish_snapshot 최신 id 일치" \
  "[[ \$(pub_sql 'SELECT max(snapshot_id) FROM meta.snapshot_log') -eq \$(core_sql 'SELECT max(id) FROM core.publish_snapshot') ]]"
check "카탈로그 스냅샷 #0 적재(sha256 f63f4429)" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.catalog_snapshot WHERE id=0 AND file_sha256 LIKE 'f63f4429%'\") -eq 1 ]]"
check "egress 차단 기록 외 허용 호출은 모두 화이트리스트" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.egress_call WHERE decision='allowed' AND dest_host !~ '(data\\.go\\.kr|law\\.go\\.kr|kipris\\.or\\.kr|k-startup\\.go\\.kr|bizinfo\\.go\\.kr|openapi\\.naver\\.com|api\\.openai\\.com|api\\.anthropic\\.com)\$'\") -eq 0 ]]"
if [[ -f .runtime/secrets/w0_public_ids.txt ]]; then
  while IFS='|' read -r id title; do
    check "W0 이전 공개 ID 유지: $id" "[[ \"\$(pub_sql \"SELECT title FROM publish.idea WHERE id='$id'\")\" == '$title' ]]"
  done < .runtime/secrets/w0_public_ids.txt
fi

echo "== 공개 화면"
code() { curl -s -o /dev/null -w '%{http_code}' "http://localhost:$port$1"; }
check "GET /pool 200" "[[ \$(code /pool) == 200 ]]"
first="$(curl -s "http://localhost:$port/api/v1/ideas" | python3 -c 'import json,sys; print(json.load(sys.stdin)["items"][0]["id"])')"
check "GET /ideas/$first 200" "[[ \$(code /ideas/$first) == 200 ]]"
check "GET /api/v1/ideas/없는ID 404" "[[ \$(code /api/v1/ideas/ID-0000-none) == 404 ]]"
check "DELETE 메서드 405" "[[ \$(curl -s -o /dev/null -w '%{http_code}' -X DELETE http://localhost:$port/pool) == 405 ]]"
check "보안 헤더(CSP)" "curl -sI http://localhost:$port/pool | grep -qi content-security-policy"
check "서버 버전 미노출" "! curl -sI http://localhost:$port/pool | grep -qiE '^server: nginx/[0-9]'"
exit $fail
