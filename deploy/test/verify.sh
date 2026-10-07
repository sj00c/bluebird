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
# 콘솔(node)·backend-api(python) 컨테이너에서 접속 시도
console_tcp() { dc exec -T console node -e "
const s=require('net').connect({host:'$1',port:$2,timeout:3000},()=>{s.destroy();process.exit(0)});
s.on('error',()=>process.exit(1));s.on('timeout',()=>process.exit(1));"; }
api_tcp() { dc exec -T backend-api python -c "$py_tcp" "$1" "$2"; }
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
check "DMZ portal → 업무망 backend-api 접속 불가"      "! node_tcp backend-api 8000"
check "DMZ portal → 업무망 콘솔 접속 불가"            "! node_tcp console 3000"
check "DMZ nginx → 업무망 콘솔 접속 불가"             "! nginx_tcp console 3000"
check "콘솔 → core-db 직접 접속 불가"                 "! console_tcp core-db 5432"
check "콘솔 → 공개용 DB 접속 불가"                    "! console_tcp publish-db 5432"
check "콘솔 → backend-api 접속 가능"                  "console_tcp backend-api 8000"
check "콘솔 → 인터넷·프록시 불가"                      "! console_tcp 1.1.1.1 443 && ! console_tcp proxy 3128"
check "backend-api → 프록시·인터넷 불가"              "! api_tcp proxy 3128 && ! api_tcp 1.1.1.1 443"
check "backend-api → 공개용 DB 불가(push·pull은 jobs만)" "! api_tcp publish-db 5432"
check "콘솔 게이트웨이 포트는 127.0.0.1에만 열림, 콘솔 앱은 호스트 포트 없음" \
  "[[ \$(docker port bluebird-test-console-gw-1 8090/tcp) == 127.0.0.1:* && -z \$(docker port bluebird-test-console-1) ]]"
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
core_n="$(core_sql 'SELECT count(*) FROM core.idea WHERE retired_at IS NULL')"
pub_n="$(pub_sql 'SELECT count(*) FROM publish.idea')"
allowed="$(core_sql 'SELECT count(*) FROM core.idea i JOIN core.source s ON s.id=i.source_id WHERE s.public_ok AND i.retired_at IS NULL AND i.withheld_at IS NULL')"
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

echo "== 원본·카드·소스 점검(G1·G2·G13)"
check "core.idea 29,828행(6개 파일 소스)"                "[[ $core_n -eq 29828 ]]"
withheld_n="$(core_sql 'SELECT count(*) FROM core.idea WHERE withheld_at IS NOT NULL')"
check "공개용 DB 아이디어 + 이의로 공개 중단 3,394 이상(G2)" "[[ \$(( pub_n + withheld_n )) -ge 3394 ]]"
check "모든 아이디어에 카드 1개(G1 ≥ 10,000)" \
  "[[ \$(core_sql 'SELECT count(*) FROM core.idea_card k JOIN core.idea i ON i.id=k.idea_id WHERE i.retired_at IS NULL') -eq $core_n && $core_n -ge 10000 ]]"
check "KIPRIS 카드는 모두 local_extract(반출 보류)" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.idea_card k JOIN core.idea i ON i.id=k.idea_id WHERE i.source_id='kipris_contest_idea_bulk' AND k.card_kind<>'local_extract'\") -eq 0 ]]"
check "본문 없는 카드는 title_only, missing_data는 본문 근거만" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.idea_card k JOIN core.idea i ON i.id=k.idea_id WHERE (coalesce(btrim(i.body),'')='') <> (k.card_kind='title_only') OR (k.card_kind='title_only' AND jsonb_array_length(k.missing_data)>0)\") -eq 0 ]]"
check "card_kind=full은 LLM(P1)이 본문을 받은 카드만" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.idea_card WHERE card_kind='full' AND extractor<>'llm'\") -eq 0 ]]"
retired_ids="$(core_sql 'SELECT id FROM core.idea WHERE retired_at IS NOT NULL ORDER BY 1')"
pub_ids="$(pub_sql 'SELECT id FROM publish.idea ORDER BY 1')"
echo "      retired=$(grep -c . <<<"$retired_ids")"
check "퇴역 행은 공개용 DB에 없음" "[[ -z \"\$(comm -12 <(echo \"\$retired_ids\") <(echo \"\$pub_ids\") | grep .)\" ]]"
last_check="(SELECT DISTINCT ON (source_id) source_id, status FROM core.source_check ORDER BY source_id, checked_at DESC, id DESC)"
check "sources check: 파일 소스 6개 ok" \
  "[[ \$(core_sql \"SELECT count(*) FROM $last_check c JOIN core.source s ON s.id=c.source_id WHERE c.status='ok'\") -eq 6 ]]"
check "sources check: 키 없는 외부 소스(목록·법제처) ok" \
  "[[ \$(core_sql \"SELECT count(*) FROM $last_check c WHERE c.source_id IN ('datagokr_catalog_15062804','law_drf_eflaw') AND c.status='ok'\") -eq 2 ]]"
check "sources check: 키 필요 소스는 ok 또는 key_required(error·blocked 0)" \
  "[[ \$(core_sql \"SELECT count(*) FROM $last_check c WHERE c.source_id IN ('kstartup_announcement_15125364','acrc_public_proposal_15059115','bizinfo_announcement','naver_search_news','kipris_plus_patent','openai_api','anthropic_api') AND c.status IN ('ok','key_required')\") -eq 7 ]]"
check "sources check 외부 호출은 egress 감사 행에 연결" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.source_check c LEFT JOIN core.egress_call e ON e.id=c.egress_call_id WHERE c.http_status IS NOT NULL AND e.purpose IS DISTINCT FROM 'source_check'\") -eq 0 ]]"
if [[ -f .runtime/secrets/w0_public_ids.txt ]]; then
  while IFS='|' read -r id title; do
    check "W0 이전 공개 ID 유지: $id" "[[ \"\$(pub_sql \"SELECT title FROM publish.idea WHERE id='$id'\")\" == '$title' ]]"
  done < .runtime/secrets/w0_public_ids.txt
fi

echo "== 되살리기 깔때기(G3·G4·G5)"
funnel_pub="$(core_sql 'SELECT idea_id FROM core.revival_candidate WHERE s6 ORDER BY 1')"
revived="$(core_sql 'SELECT x FROM core.publish_snapshot ps, unnest(ps.revived_ids) x WHERE ps.id = (SELECT max(id) FROM core.publish_snapshot WHERE applied_at IS NOT NULL) ORDER BY 1')"
check "6단계 = 반영 완료된 최신 스냅샷에 든 아이디어"   "[[ \"$revived\" == \"$funnel_pub\" ]]"
check "법령 시행 바뀐 것은 국가법령정보 API로 확인된 것만 매칭 통과" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.revival_candidate r JOIN core.change_match m ON m.idea_id=r.idea_id AND m.status='approved' JOIN core.condition_change c ON c.id=m.change_id WHERE r.s6 AND c.kind='law_effective' AND c.verify_status<>'api_verified'\") -eq 0 ]]"
check "6단계(공개)까지 간 아이디어 1건 이상"           "[[ -n \"$funnel_pub\" ]]"
for t in diagnosis change timeliness weekly_top announcement_match; do
  check "공개 ${t}는 6단계 아이디어만" \
    "[[ -z \"\$(comm -23 <(pub_sql 'SELECT DISTINCT idea_id FROM publish.$t ORDER BY 1') <(echo \"$funnel_pub\"))\" ]]"
done
check "공개 진단·바뀐 것마다 근거 1개 이상, 근거 행 실재" \
  "[[ \$(pub_sql \"SELECT count(*) FROM (SELECT evidence_ids FROM publish.diagnosis UNION ALL SELECT evidence_ids FROM publish.change) x WHERE cardinality(evidence_ids)=0 OR EXISTS (SELECT 1 FROM unnest(evidence_ids) e WHERE e NOT IN (SELECT id FROM publish.evidence))\") -eq 0 ]]"
check "core 비-U 진단은 모두 근거 연결" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.diagnosis d WHERE d.\\\"primary\\\"<>'U' AND NOT EXISTS (SELECT 1 FROM core.x_evidence x WHERE x.target_type='diagnosis' AND x.target_id=d.idea_id)\") -eq 0 ]]"
check "사람이 넣은 바뀐 것은 입력자 기록" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.condition_change WHERE origin='human' AND coalesce(added_by,'')=''\") -eq 0 ]]"
check "공개 S는 now/conditional만" \
  "[[ \$(pub_sql \"SELECT count(*) FROM publish.timeliness WHERE verdict NOT IN ('now','conditional')\") -eq 0 ]]"
own_text="$(pub_sql "SELECT rationale FROM publish.diagnosis UNION ALL SELECT coalesce(how_now,'')||' '||array_to_string(what_changed,' ') FROM publish.change UNION ALL SELECT coalesce(resolve_condition,'') FROM publish.timeliness UNION ALL SELECT coalesce(problem,'')||' '||coalesce(solution,'') FROM publish.idea WHERE problem IS NOT NULL OR solution IS NOT NULL")"
check "공개 글에 금지 표현 없음(wording.FORBIDDEN 전체)" \
  "printf '%s' \"\$own_text\" | ( cd ../../pipeline && uv run --quiet python -c 'import sys; from bluebird import wording; sys.exit(1 if wording.find(sys.stdin.read()) else 0)' )"

echo "== 콘솔·이의 왕복(G11)"
cport="$(env_get BB_CONSOLE_PORT)"
check "콘솔(게이트웨이) 로그인 화면 200(127.0.0.1)" "[[ \$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$cport/login) == 200 ]]"
check "콘솔 응답에 X-Frame-Options DENY·CSP" \
  "curl -sI http://127.0.0.1:$cport/login | grep -qi '^x-frame-options: DENY' && curl -sI http://127.0.0.1:$cport/login | grep -qi 'frame-ancestors'"
check "backend-api: 토큰 없으면 401" \
  "[[ \$(dc exec -T backend-api python -c \"import urllib.request as u,urllib.error as e
try: u.urlopen('http://127.0.0.1:8000/api/me')
except e.HTTPError as x: print(x.code)\") == 401 ]]"
api_as() { dc exec -T -e PGPASSWORD="$(env_get API_DB_PASSWORD)" core-db psql -h localhost -U bb_api -d bluebird_core -v ON_ERROR_STOP=1 -tAc "$1"; }
check "backend-api DB 역할 bb_api: 읽기 가능"              "api_as 'select count(*) from core.idea'"
check "bb_api: superuser 아님·DDL·원본 수정·egress 감사 읽기 불가" \
  "[[ \$(core_sql \"SELECT rolsuper FROM pg_roles WHERE rolname='bb_api'\") == f ]] && ! api_as 'create table core.x(a int)' && ! api_as \"update core.idea set title=title where false\" && ! api_as 'select 1 from core.egress_call'"
check "backend-api 접속 계정은 bb_api" \
  "dc exec -T backend-api sh -c 'case \$BB_DSN in postgresql://bb_api:*) exit 0;; *) exit 1;; esac'"
check "토큰 원문은 어떤 컨테이너에도 마운트되지 않음" \
  "! dc --profile jobs config | grep -q console_tokens && ! docker inspect \$(dc ps -q) | grep -q console_tokens"

# 실제 왕복: 국민 → nginx → portal → DMZ inbox → pull(업무망) → core → 처리(기각, 점검용 표시) → 기록
target="$(pub_sql 'SELECT id FROM publish.idea ORDER BY id LIMIT 1')"
mark="verify.sh 점검 $(date +%s)"
hdrs="$(curl -s -D - -o /tmp/bb-verify-obj.body -X POST "http://localhost:$port/api/v1/objections" \
  --data-urlencode "idea_id=$target" --data-urlencode kind=other --data-urlencode "body=$mark")"
check "이의 POST → 303 상대 경로, 본문 되돌려주지 않음" \
  "grep -qi '^HTTP/1.1 303' <<<\"\$hdrs\" && grep -qi \"^location: /ideas/$target?objection=ok\" <<<\"\$hdrs\" && ! grep -q 'verify.sh' /tmp/bb-verify-obj.body"
check "DMZ inbox에 1건 접수(uuid 포함)" \
  "[[ \$(pub_sql \"SELECT count(*) FROM inbox.objection WHERE body='$mark' AND uid IS NOT NULL\") -eq 1 ]]"
dc --profile jobs run --rm -T backend-jobs objections pull >/tmp/bb-verify-pull.log 2>&1
check "pull 뒤 DMZ inbox 0건"                         "[[ \$(pub_sql 'SELECT count(*) FROM inbox.objection') -eq 0 ]]"
check "pull 뒤 core에 저장(open)·실행 기록 ok" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.objection WHERE body='$mark' AND status='open' AND dmz_uid IS NOT NULL\") -eq 1 && \$(core_sql \"SELECT status FROM core.pipeline_run WHERE stage='objections-pull' ORDER BY id DESC LIMIT 1\") == ok ]]"
oid="$(core_sql "SELECT id FROM core.objection WHERE body='$mark'")"
s6_before="$(core_sql 'SELECT count(*) FROM core.revival_candidate WHERE s6')"
dc --profile jobs run --rm -T backend-jobs objections resolve --id "${oid:-0}" --decision rejected \
  --resolution "verify.sh 자동 점검 이의(시험)" --by verify.sh >/dev/null 2>&1
check "처리(기각) 기록: 처리자·내용·검토 행" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.objection o JOIN core.review r ON r.target_type='objection' AND r.target_id=o.id::text WHERE o.id=${oid:-0} AND o.status='rejected' AND o.resolved_by='verify.sh'\") -eq 1 ]]"
check "기각은 공개를 바꾸지 않음(6단계 수 그대로)" "[[ \$(core_sql 'SELECT count(*) FROM core.revival_candidate WHERE s6') -eq $s6_before ]]"
check "공개 중단(withheld) 아이디어는 공개용 DB·깔때기에 없음" \
  "[[ -z \"\$(comm -12 <(core_sql 'SELECT id FROM core.idea WHERE withheld_at IS NOT NULL ORDER BY 1') <(echo \"\$pub_ids\") | grep .)\" && \$(core_sql 'SELECT count(*) FROM core.funnel_stage(0) f JOIN core.idea i ON i.id=f.idea_id WHERE i.withheld_at IS NOT NULL') -eq 0 ]]"
check "수용된 이의의 아이디어는 그 뒤 재승인 없이는 6단계 아님" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.objection o JOIN core.revival_candidate r ON r.idea_id=o.idea_id AND r.s6 WHERE o.status='accepted' AND NOT EXISTS (SELECT 1 FROM core.review v WHERE v.target_type='idea' AND v.target_id=o.idea_id AND v.round='final' AND v.decision='approve' AND v.created_at>o.resolved_at)\") -eq 0 ]]"
check "수용된 이의 1건 이상 실제 처리됨(콘솔 E2E 기록)" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.objection WHERE status='accepted' AND resolved_by<>'verify.sh'\") -ge 1 ]]"

echo "== 공개 화면"
code() { curl -s -o /dev/null -w '%{http_code}' "http://localhost:$port$1"; }
check "GET /pool 200" "[[ \$(code /pool) == 200 ]]"
check "화면1 GET / 이번 주 재조명 200, weekly_top 1위 표시" \
  "[[ \$(code /) == 200 ]] && curl -s http://localhost:$port/ | grep -q \"\$(pub_sql 'SELECT idea_id FROM publish.weekly_top ORDER BY rank LIMIT 1')\""
check "화면2 GET /explore?q= 200, API 결과 있음·짧은 질의 400" \
  "[[ \$(code '/explore?q=%EB%8C%80%EC%B2%B4%EC%A1%B0%EC%A0%9C') == 200 && \$(code '/api/v1/explore?q=a') == 400 ]] && curl -s 'http://localhost:$port/api/v1/explore?q=%EB%8C%80%EC%B2%B4%EC%A1%B0%EC%A0%9C' | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)[\"ideas\"] else 1)'"
top1="$(pub_sql 'SELECT idea_id FROM publish.weekly_top ORDER BY rank LIMIT 1')"
check "화면3 카드: 4단계·흔적 범위 문구·S 근거·이의 폼" \
  "curl -s http://localhost:$port/ideas/$top1 | grep -q '지금 하려면' && curl -s http://localhost:$port/ideas/$top1 | grep -qE '외부 검색 (미실시|\(뉴스·특허\) 실시)' && curl -s http://localhost:$port/ideas/$top1 | grep -q '채점 근거' && curl -s http://localhost:$port/ideas/$top1 | grep -q 'name=\"body\"'"
check "공개 S마다 채점 축 수만큼 근거(v2), 근거 행 실재" \
  "[[ \$(pub_sql \"SELECT count(*) FROM publish.timeliness t WHERE cardinality(t.evidence_ids) < t.n_scored OR EXISTS (SELECT 1 FROM unnest(t.evidence_ids) e WHERE e NOT IN (SELECT id FROM publish.evidence))\") -eq 0 ]]"
check "공개용 DB 템플릿 v2" "[[ \$(pub_sql 'SELECT template_version FROM meta.snapshot_log ORDER BY snapshot_id DESC LIMIT 1') == v2 ]]"
first="$(curl -s "http://localhost:$port/api/v1/ideas" | python3 -c 'import json,sys; print(json.load(sys.stdin)["items"][0]["id"])')"
check "GET /ideas/$first 200" "[[ \$(code /ideas/$first) == 200 ]]"
check "GET /api/v1/ideas/없는ID 404" "[[ \$(code /api/v1/ideas/ID-0000-none) == 404 ]]"
check "DELETE 메서드 405" "[[ \$(curl -s -o /dev/null -w '%{http_code}' -X DELETE http://localhost:$port/pool) == 405 ]]"
check "보안 헤더(CSP)" "curl -sI http://localhost:$port/pool | grep -qi content-security-policy"
check "서버 버전 미노출" "! curl -sI http://localhost:$port/pool | grep -qiE '^server: nginx/[0-9]'"
exit $fail
