#!/usr/bin/env bash
# 시험 배포 초기화: 런타임 디렉터리·익명화 비밀키·.env·seed 파일 준비.
# 사용: deploy/test/init.sh [인수인계 패키지 디렉터리]
#   기본값: reference/parangsae-src. 공공데이터 파일은 data/ 에서 가져온다.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
rt="$here/.runtime"
ref="${1:-$root/reference/parangsae-src}"

mkdir -p "$rt"/{secrets,seed}

# 익명화 비밀키: 익명 ID(HMAC)의 기준. 바꾸면 모든 ID가 바뀌므로 한 번 만들면 유지한다(백업 대상).
if [[ ! -f "$rt/secrets/anon_secret" ]]; then
  openssl rand -hex 32 > "$rt/secrets/anon_secret"
  echo "[init] anon_secret created"
fi
chmod 600 "$rt/secrets/anon_secret"

# 콘솔 접근 토큰(시험용): 사람별 토큰 원문은 .runtime/secrets/console_tokens(관리자에게 전달),
# backend-api에는 sha256만 담은 console_users.json을 준다.
if [[ ! -f "$rt/secrets/console_users.json" ]]; then
  : > "$rt/secrets/console_tokens"; chmod 600 "$rt/secrets/console_tokens"
  json="{"
  for spec in "reviewer1:reviewer" "coder_a1:coder" "coder_b1:coder" "expert1:expert" "auditor1:auditor"; do
    who="${spec%%:*}"; role="${spec#*:}"; tok="$(openssl rand -hex 24)"
    echo "$who $tok" >> "$rt/secrets/console_tokens"
    h="$(printf '%s' "$tok" | shasum -a 256 | cut -d' ' -f1)"
    json+="\"$h\":{\"user\":\"$who\",\"roles\":[\"$role\"]},"
  done
  echo "${json%,}}" > "$rt/secrets/console_users.json"
  echo "[init] console tokens created (.runtime/secrets/console_tokens)"
fi

# .env: 없는 값만 추가한다(기존 비밀번호 유지).
touch "$here/.env"; chmod 600 "$here/.env"
add_env() { grep -q "^$1=" "$here/.env" || echo "$1=$2" >> "$here/.env"; }
for v in CORE_DB_PASSWORD PUBLISH_DB_PASSWORD MIGRATOR_DB_PASSWORD PUBLISHER_DB_PASSWORD INBOX_DB_PASSWORD \
         PORTAL_DB_PASSWORD; do
  add_env "$v" "$(openssl rand -hex 16)"
done
add_env BB_HTTP_PORT 8080
add_env BB_CONSOLE_PORT 8090

# seed 파일
seed() { [[ -f "$1" ]] && cp "$1" "$rt/seed/$2" && echo "[init] seed: $2"; return 0; }
src="$ref/03_pilot/source_data"
seed "$src/awards_master_2013_2024.csv" awards_master_2013_2024.csv
seed "$src/gov_opendata_startup_contest_final_awards_2019_2025.xlsx" gov_opendata_startup_contest_final_awards_2019_2025.xlsx
seed "$src/national_science_museum_awards_20240909.csv" national_science_museum_awards_20240909.csv
seed "$src/mafra_agrifood_bigdata_contest_info.csv" mafra_agrifood_bigdata_contest_info.csv
seed "$root/data/opendata/design_idea.csv" public_design_idea_15138745.csv
kipris_zip="$ref/02_kipris_bulk/kipris_contest_bulk_utf8.zip"
if [[ -f "$kipris_zip" && ! -f "$rt/seed/kipris_idea_master.csv" ]]; then
  unzip -p "$kipris_zip" out/idea_master.csv > "$rt/seed/kipris_idea_master.csv"
  echo "[init] seed: kipris_idea_master.csv (export_grade=pending, 공개 보류)"
fi
# 목록개방현황 스냅샷 #0(2026-10-06 다운로드, sha256 f63f4429…). run-cycle이 처음 한 번 적재한다.
snap0="$root/data/opendata/catalog.csv"
snap0_sha=f63f4429e90c69992fb0853e59d46ee0853c0aee678e17b95492405858654f4c
if [[ -f "$snap0" ]]; then
  [[ "$(shasum -a 256 "$snap0" | cut -d' ' -f1)" == "$snap0_sha" ]] \
    || { echo "[init] catalog.csv sha256 does not match snapshot #0" >&2; exit 1; }
  seed "$snap0" catalog_snapshot0_2026-10-06.csv
fi

# 컨테이너는 uid 10001로 실행된다. 시험 환경 한정으로 읽기 권한을 맞춘다.
chmod -R a+rX "$rt/seed"
chmod 755 "$rt/secrets"; chmod 644 "$rt/secrets/anon_secret" "$rt/secrets/console_users.json"
echo "[init] done: $rt"
