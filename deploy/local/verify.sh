#!/usr/bin/env bash
# 로컬 데모 점검: 데이터·반출 통제·깔때기·콘솔·이의 왕복·DB 역할·공개 화면·KPI. ./demo.sh verify
set -uo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
rt="$root/.runtime"
dc() { docker compose "$@" </dev/null; }
job() { dc --profile jobs run --rm -T jobs "$@"; }
env_get() { grep "^$1=" .env | cut -d= -f2-; }
portal="http://localhost:$(env_get BB_PORTAL_PORT)"
console="http://localhost:$(env_get BB_CONSOLE_PORT)"
api="http://localhost:$(env_get BB_API_PORT)"
fail=0
check() { if eval "$2" >/dev/null 2>&1; then echo "PASS  $1"; else echo "FAIL  $1"; fail=1; fi; }

echo "== 서비스"
check "DB·API·포털·콘솔 실행 중" "[[ \$(dc ps --status running --format '{{.Service}}' | sort | tr '\\n' ' ') == 'api console db portal ' ]]"
check "포트는 127.0.0.1에만 열림" "! dc ps --format '{{.Ports}}' | grep -q '0.0.0.0:'"

echo "== 반출 통제·데이터"
core_sql() { dc exec -T db psql -U bluebird -d bluebird_core -tAc "$1"; }
pub_sql()  { dc exec -T db psql -U bluebird -d bluebird_publish -tAc "$1"; }
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
if [[ -f "$rt/secrets/w0_public_ids.txt" ]]; then
  while IFS='|' read -r id title; do
    check "W0 이전 공개 ID 유지: $id" "[[ \"\$(pub_sql \"SELECT title FROM publish.idea WHERE id='$id'\")\" == '$title' ]]"
  done < "$rt/secrets/w0_public_ids.txt"
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
  "printf '%s' \"\$own_text\" | ( cd "$root/pipeline" && uv run --quiet python -c 'import sys; from bluebird import wording; sys.exit(1 if wording.find(sys.stdin.read()) else 0)' )"

echo "== 콘솔·이의 왕복(G11)"
check "콘솔 로그인 화면 200" "[[ \$(curl -s -o /dev/null -w '%{http_code}' $console/login) == 200 ]]"
check "콘솔 응답에 X-Frame-Options DENY·CSP" \
  "curl -sI $console/login | grep -qi '^x-frame-options: DENY' && curl -sI $console/login | grep -qi 'frame-ancestors'"
check "백엔드 API: 토큰 없으면 401" "[[ \$(curl -s -o /dev/null -w '%{http_code}' $api/api/me) == 401 ]]"
tok="$(awk '$1=="reviewer1"{print $2}' "$rt/console_tokens")"
check "백엔드 API: 검토자 토큰이면 200" "[[ \$(curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer $tok' $api/api/me) == 200 ]]"
check "콘솔: 로그인 쿠키(토큰)로 첫 화면에 검토자 이름" "curl -s -b bb_console_token=$tok $console/ | grep -q reviewer1"
check "토큰 원문은 어떤 컨테이너에도 마운트되지 않음" \
  "! dc --profile jobs config | grep -q console_tokens && ! docker inspect \$(dc ps -q) | grep -q console_tokens"

echo "== DB 역할(쓰는 쪽마다 최소 권한)"
as_role() { dc exec -T -e PGPASSWORD="$(env_get DB_PASSWORD)" db psql -h localhost -U "$1" -d "$2" -v ON_ERROR_STOP=1 -tAc "$3"; }
check "API(bb_api): 원본 DB 읽기 가능" "as_role bb_api bluebird_core 'select count(*) from core.idea'"
check "API(bb_api): superuser 아님·DDL·원본 수정·외부 호출 기록 읽기 불가" \
  "[[ \$(core_sql \"SELECT rolsuper FROM pg_roles WHERE rolname='bb_api'\") == f ]] && ! as_role bb_api bluebird_core 'create table core.x(a int)' && ! as_role bb_api bluebird_core \"update core.idea set title=title where false\" && ! as_role bb_api bluebird_core 'select 1 from core.egress_call'"
check "API 접속 계정은 bb_api" "dc exec -T api sh -c 'case \$BB_DSN in postgresql://bb_api:*) exit 0;; *) exit 1;; esac'"
check "포털(bb_portal): 공개 DB 읽기 가능, 원본 DB 접속 불가" \
  "as_role bb_portal bluebird_publish 'select count(*) from publish.idea' && ! as_role bb_portal bluebird_core 'select 1'"
check "포털 접속 계정은 bb_portal" "dc exec -T portal sh -c 'case \$PORTAL_DATABASE_URL in postgresql://bb_portal:*) exit 0;; *) exit 1;; esac'"
check "포털: 공개 DB 쓰기·이의 접수함 읽기·템플릿 등록 불가" \
  "! as_role bb_portal bluebird_publish 'delete from publish.idea' && ! as_role bb_portal bluebird_publish 'select * from inbox.objection' && ! as_role bb_portal bluebird_publish \"insert into meta.publish_template values ('x','y')\""
check "공개 반영(bb_publisher): 이의 접수함 접근 불가" "! as_role bb_publisher bluebird_publish 'select * from inbox.objection'"
check "이의 가져오기(bb_inbox_reader): 공개 데이터 쓰기 불가" "! as_role bb_inbox_reader bluebird_publish 'delete from publish.idea'"

# 실제 왕복: 국민 → 포털 → 공개 DB 이의 접수함 → 가져오기 → 원본 DB → 처리(기각, 점검용 표시) → 기록
target="$(pub_sql 'SELECT id FROM publish.idea ORDER BY id LIMIT 1')"
mark="verify.sh 점검 $(date +%s)"
hdrs="$(curl -s -D - -o /tmp/bb-verify-obj.body -X POST "$portal/api/v1/objections" \
  --data-urlencode "idea_id=$target" --data-urlencode kind=other --data-urlencode "body=$mark")"
check "이의 POST → 303 상대 경로, 본문 되돌려주지 않음" \
  "grep -qi '^HTTP/1.1 303' <<<\"\$hdrs\" && grep -qi \"^location: /ideas/$target?objection=ok\" <<<\"\$hdrs\" && ! grep -q 'verify.sh' /tmp/bb-verify-obj.body"
check "공개 DB 이의 접수함에 1건 접수(uuid 포함)" \
  "[[ \$(pub_sql \"SELECT count(*) FROM inbox.objection WHERE body='$mark' AND uid IS NOT NULL\") -eq 1 ]]"
job objections pull >/tmp/bb-verify-pull.log 2>&1
check "가져온 뒤 공개 DB 이의 접수함 0건"                         "[[ \$(pub_sql 'SELECT count(*) FROM inbox.objection') -eq 0 ]]"
check "가져온 뒤 원본 DB에 저장(open)·실행 기록 ok" \
  "[[ \$(core_sql \"SELECT count(*) FROM core.objection WHERE body='$mark' AND status='open' AND dmz_uid IS NOT NULL\") -eq 1 && \$(core_sql \"SELECT status FROM core.pipeline_run WHERE stage='objections-pull' ORDER BY id DESC LIMIT 1\") == ok ]]"
oid="$(core_sql "SELECT id FROM core.objection WHERE body='$mark'")"
s6_before="$(core_sql 'SELECT count(*) FROM core.revival_candidate WHERE s6')"
job objections resolve --id "${oid:-0}" --decision rejected \
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
code() { curl -s -o /dev/null -w '%{http_code}' "$portal$1"; }
check "GET /pool 200" "[[ \$(code /pool) == 200 ]]"
check "화면1 GET / 이번 주 재조명 200, weekly_top 1위 표시" \
  "[[ \$(code /) == 200 ]] && curl -s $portal/ | grep -q \"\$(pub_sql 'SELECT idea_id FROM publish.weekly_top ORDER BY rank LIMIT 1')\""
check "화면2 GET /explore?q= 200, API 결과 있음·짧은 질의 400" \
  "[[ \$(code '/explore?q=%EB%8C%80%EC%B2%B4%EC%A1%B0%EC%A0%9C') == 200 && \$(code '/api/v1/explore?q=a') == 400 ]] && curl -s '$portal/api/v1/explore?q=%EB%8C%80%EC%B2%B4%EC%A1%B0%EC%A0%9C' | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)[\"ideas\"] else 1)'"
top1="$(pub_sql 'SELECT idea_id FROM publish.weekly_top ORDER BY rank LIMIT 1')"
check "화면3 카드: 4단계·흔적 범위 문구·S 근거·이의 폼" \
  "curl -s $portal/ideas/$top1 | grep -q '지금 하려면' && curl -s $portal/ideas/$top1 | grep -qE '외부 검색 (미실시|\(뉴스·특허\) 실시)' && curl -s $portal/ideas/$top1 | grep -q '채점 근거' && curl -s $portal/ideas/$top1 | grep -q 'name=\"body\"'"
check "공개 S마다 채점 축 수만큼 근거(v2), 근거 행 실재" \
  "[[ \$(pub_sql \"SELECT count(*) FROM publish.timeliness t WHERE cardinality(t.evidence_ids) < t.n_scored OR EXISTS (SELECT 1 FROM unnest(t.evidence_ids) e WHERE e NOT IN (SELECT id FROM publish.evidence))\") -eq 0 ]]"
check "화면2 검색어 제어문자(NUL)도 500 아님" "[[ \$(code '/api/v1/explore?q=ab%00') != 500 && \$(code '/explore?q=ab%00') != 500 ]]"
check "공개 근거에 채점자 이름 없음(S 근거 excerpt는 축 이름)" \
  "[[ \$(pub_sql \"SELECT count(*) FROM publish.evidence e JOIN publish.timeliness t ON e.id = ANY(t.evidence_ids) WHERE e.excerpt NOT LIKE '시의성 축: %'\") -eq 0 ]]"
check "공개용 DB 템플릿 v2" "[[ \$(pub_sql 'SELECT template_version FROM meta.snapshot_log ORDER BY snapshot_id DESC LIMIT 1') == v2 ]]"
first="$(curl -s "$portal/api/v1/ideas" | python3 -c 'import json,sys; print(json.load(sys.stdin)["items"][0]["id"])')"
check "GET /ideas/$first 200" "[[ \$(code /ideas/$first) == 200 ]]"
check "GET /api/v1/ideas/없는ID 404" "[[ \$(code /api/v1/ideas/ID-0000-none) == 404 ]]"
check "DELETE 메서드 405" "[[ \$(curl -s -o /dev/null -w '%{http_code}' -X DELETE $portal/pool) == 405 ]]"
check "보안 헤더(CSP)" "curl -sI $portal/pool | grep -qi content-security-policy"

echo "== KPI 현황표(G1–G13, bluebird kpi report)"
# p95는 오늘 측정했고 요청 오류가 0인 최신 결과만 쓴다(오래됐거나 오류가 있으면 G8 진행 중으로 남는다).
p95f="$(ls -t "$rt"/p95-"$(date +%Y%m%d)"-*.txt 2>/dev/null | head -1)"
p95="$( [[ -n $p95f ]] && python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['p95_ms'] if d['errors'] == 0 else '')" "$p95f")"
kpi_out="$rt/kpi-$(date +%Y%m%d-%H%M%S).txt"
job kpi report ${p95:+--p95-ms "$p95"} > "$kpi_out" 2> "$kpi_out.err"; kpi_rc=$?
sed 's/^/      /' "$kpi_out"
if [[ $kpi_rc -ne 0 ]]; then grep -v 'Container' "$kpi_out.err" | tail -20 | sed 's/^/      ! /'; fi
check "kpi report 실행, fail 0(사람 대기·키 대기는 human_blocked·key_required로 표시)" "[[ $kpi_rc -eq 0 ]] && grep -q '^G13' $kpi_out"
check "kpi: 자동 검증 항목 G1·G2·G9·G10·G11·G13 pass" \
  "[[ \$(grep -E '^(G1|G2|G9|G10|G11|G13) ' $kpi_out | grep -c ' pass ') -eq 6 ]]"
exit $fail
