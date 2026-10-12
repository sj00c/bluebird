#!/usr/bin/env bash
# 파랑새 로컬 데모 실행기. 자세한 설명은 README.md.
#   ./demo.sh init            처음 한 번: .env·익명화 키·콘솔 토큰·원본 seed 준비
#   ./demo.sh cycle [ingest 인수]  빌드 → 원본 적재·소스 점검·카탈로그 → 승인분 공개 → 화면 기동
#   ./demo.sh up [서비스…]     서비스 켜기(기본 전부, 개발 때는 `up db`)
#   ./demo.sh down            끄기(데이터 유지). 데이터까지 지우려면 docker compose down -v
#   ./demo.sh check           외부 API·원본 파일 연결 점검표
#   ./demo.sh collect [인수…]   검증된 공식 공모전·제안 원본 수집 → 비공개 DB 적재
#   ./demo.sh policy          레지스트리 정책·선별 재료(기록 종류·제외 후보 이유)만 DB에 반영, 파일 재수집 없음
#   ./demo.sh export [--include-held]  공유용 xlsx + 출처 명세(docs/DATA_PROVENANCE.md) 생성 → .runtime/export/
#   ./demo.sh job <명령…>      처리 작업 1회 실행(예: job trace auto, job kpi report)
#   ./demo.sh verify          데모 동작 점검(deploy/local/verify.sh)
#   ./demo.sh publish         이의 가져오기 → 주간 재조명 계산 → 현재 승인분 공개
#   ./demo.sh status          서비스와 DB 연결 상태 확인(데이터 변경 없음)
#   ./demo.sh env             로컬 개발용 접속 정보 출력: eval "$(./demo.sh env)"
#   ./demo.sh tokens          콘솔 로그인 토큰 보기
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
cd "$root"
rt="$root/.runtime"
dc() { docker compose "$@"; }
job() { dc --profile jobs run --rm -T jobs "$@"; }
env_get() { grep "^$1=" .env | cut -d= -f2-; }

cmd_init() {
  # 원본 파일 위치. 기본 data/seed/ (git 밖). 인수인계 zip을 그대로 쓸 때는 ./demo.sh init <zip 풀린 디렉터리>.
  local ref="${1:-}"
  mkdir -p "$rt"/{secrets,seed,console}
  # .env: 예시에서 시작하고, 비어 있는 DB 비밀번호만 만든다(기존 값·키는 건드리지 않는다).
  [[ -f .env ]] || cp .env.example .env
  chmod 600 .env
  if [[ -z "$(env_get DB_PASSWORD)" ]]; then
    local pw; pw="$(openssl rand -hex 16)"
    python3 - "$pw" <<'PY'
import re, sys
s = open(".env").read()
s = re.sub(r"(?m)^DB_PASSWORD=.*$", "DB_PASSWORD=" + sys.argv[1], s) if re.search(r"(?m)^DB_PASSWORD=", s) else s + f"DB_PASSWORD={sys.argv[1]}\n"
open(".env", "w").write(s)
PY
    echo "[init] DB_PASSWORD created"
  fi
  # 익명화 비밀키: 익명 ID(HMAC)의 기준. 바꾸면 모든 ID가 바뀌므로 한 번 만들면 유지한다.
  if [[ ! -f "$rt/secrets/anon_secret" ]]; then
    openssl rand -hex 32 > "$rt/secrets/anon_secret"
    echo "[init] anon_secret created"
  fi
  # 콘솔 로그인 토큰: 원문은 .runtime/console_tokens(마운트하지 않음), API에는 sha256만 담은 console_users.json.
  if [[ ! -f "$rt/console/console_users.json" ]]; then
    : > "$rt/console_tokens"; chmod 600 "$rt/console_tokens"
    local json="{" spec who role tok h
    for spec in "reviewer1:reviewer" "coder_a1:coder" "coder_b1:coder" "expert1:expert" "auditor1:auditor"; do
      who="${spec%%:*}"; role="${spec#*:}"; tok="$(openssl rand -hex 24)"
      echo "$who $tok" >> "$rt/console_tokens"
      h="$(printf '%s' "$tok" | shasum -a 256 | cut -d' ' -f1)"
      json+="\"$h\":{\"user\":\"$who\",\"roles\":[\"$role\"]},"
    done
    echo "${json%,}}" > "$rt/console/console_users.json"
    echo "[init] console tokens created (./demo.sh tokens)"
  fi
  # 원본 seed. git에 없다. 파일 이름과 내려받는 곳은 docs/DATA_PROVENANCE.md 와 deploy/local/sources.toml 의 url.
  #   data/seed/<파일명>  — 직접 내려받아 둔 경우(기본)
  #   <ref>/03_pilot/source_data/<파일명>, <ref>/02_kipris_bulk/…zip — 인수인계 디렉터리를 인수로 준 경우
  seed() { if [[ -f "$1" ]]; then cp "$1" "$rt/seed/$2" && echo "[init] seed: $2"; else echo "[init] missing (skip): $2"; fi; }
  local sd="$root/data/seed" f
  for f in awards_master_2013_2024.csv gov_opendata_startup_contest_final_awards_2019_2025.xlsx \
           national_science_museum_awards_20240909.csv mafra_agrifood_bigdata_contest_info.csv \
           public_design_idea_15138745.csv kipris_idea_master.csv; do
    if [[ -f "$sd/$f" ]]; then seed "$sd/$f" "$f"
    elif [[ -n "$ref" && -f "$ref/03_pilot/source_data/$f" ]]; then seed "$ref/03_pilot/source_data/$f" "$f"
    else echo "[init] missing (skip): $f"; fi
  done
  local kipris_zip="${ref:+$ref/02_kipris_bulk/kipris_contest_bulk_utf8.zip}"
  if [[ -n "$kipris_zip" && -f "$kipris_zip" && ! -f "$rt/seed/kipris_idea_master.csv" ]]; then
    unzip -p "$kipris_zip" out/idea_master.csv > "$rt/seed/kipris_idea_master.csv"
    echo "[init] seed: kipris_idea_master.csv (공개 보류 소스)"
  fi
  # 목록개방현황 스냅샷 #0(2026-10-06 다운로드). cycle이 처음 한 번 적재한다. 없으면 건너뛴다.
  local snap0 sha=f63f4429e90c69992fb0853e59d46ee0853c0aee678e17b95492405858654f4c
  for snap0 in "$sd/catalog_snapshot0_2026-10-06.csv" "$root/data/opendata/catalog.csv"; do
    [[ -f "$snap0" ]] || continue
    [[ "$(shasum -a 256 "$snap0" | cut -d' ' -f1)" == "$sha" ]] || { echo "[init] $snap0 sha256 mismatch" >&2; exit 1; }
    seed "$snap0" catalog_snapshot0_2026-10-06.csv; break
  done
  # 컨테이너는 uid 10001로 실행된다. 읽기 권한을 맞춘다.
  chmod -R a+rX "$rt/seed"
  chmod 755 "$rt/secrets" "$rt/console"; chmod 644 "$rt/secrets/anon_secret" "$rt/console/console_users.json"
  echo "[init] done. 키는 .env에 넣고 ./demo.sh cycle"
}

cmd_cycle() {
  dc build -q
  dc up -d --wait db
  job migrate --target core
  job migrate --target publish
  job ingest "$@"
  # 분석·분류·매칭은 명시적으로 실행하는 별도 job. 원본 적재가 판정을 생성하지 않는다.
  job sources check || echo "[cycle] sources check: must 소스 일부 실패(표 참고)"
  if [[ -f "$rt/seed/catalog_snapshot0_2026-10-06.csv" ]]; then
    job signals catalog-import --file /seed/catalog_snapshot0_2026-10-06.csv --taken-at 2026-10-06
  fi
  cmd_publish
  dc up -d --wait api portal console
  echo "[cycle] done."
  urls
}

cmd_collect() {
  job collect contests \
    --config /config/contest-sources.toml \
    --config /config/science-contest-sources.toml \
    --config /config/design-contest-sources.toml "$@"
}

# 레지스트리 4개의 정책 필드(public_ok·export_grade·record_kind·exclude_reason)만 DB에 맞추고 선별 재료(학생 대회·중복·제외 후보 이유) 재계산. 파일 재수집 없음.
# 공유용 내보내기. xlsx는 .runtime/export/, 출처 명세는 docs/DATA_PROVENANCE.md 로(레포에 둔다).
cmd_export() {
  mkdir -p "$rt/export"; chmod 777 "$rt/export"
  local stamp name; stamp="$(date +%Y%m%d)"; name="bluebird_ideas_$stamp"
  [[ " $* " == *" --include-held "* ]] && name="${name}_internal"   # 보류 소스 포함본은 이름으로 구분
  job export xlsx --out "/export/$name.xlsx" "$@"
  job export provenance --config /config/sources.toml --config /config/contest-sources.toml \
    --config /config/science-contest-sources.toml --config /config/design-contest-sources.toml \
    --out /export/DATA_PROVENANCE.md
  cp "$rt/export/DATA_PROVENANCE.md" "$root/docs/DATA_PROVENANCE.md"
  echo "[export] $rt/export/$name.xlsx · docs/DATA_PROVENANCE.md"
}

cmd_policy() {
  job ingest --policy-only \
    --config /config/sources.toml \
    --config /config/contest-sources.toml \
    --config /config/science-contest-sources.toml \
    --config /config/design-contest-sources.toml
}

cmd_publish() {
  job objections pull
  job top
  job publish
  echo "[publish] 현재 승인분을 반영했습니다. 미승인 분석은 공개하지 않습니다."
}

cmd_status() {
  dc ps
  local service port path failed=0
  for service in api portal console; do
    case "$service" in
      api) port="$(env_get BB_API_PORT)"; path=/healthz ;;
      portal) port="$(env_get BB_PORTAL_PORT)"; path=/healthz ;;
      console) port="$(env_get BB_CONSOLE_PORT)"; path=/login ;;
    esac
    if curl --fail --silent --show-error --max-time 10 -o /dev/null "http://127.0.0.1:$port$path"; then
      echo "[status] $service ready"
    else
      echo "[status] $service unavailable" >&2
      failed=1
    fi
  done
  return "$failed"
}

urls() {
  echo "  포털 : http://localhost:$(env_get BB_PORTAL_PORT)/"
  echo "  콘솔 : http://localhost:$(env_get BB_CONSOLE_PORT)/  (토큰: ./demo.sh tokens)"
  echo "  API  : http://localhost:$(env_get BB_API_PORT)/healthz"
}

cmd_env() {
  # 호스트에서 uv run bluebird / npm run dev 할 때 쓰는 접속 정보(DB는 127.0.0.1:BB_DB_PORT).
  local pw port; pw="$(env_get DB_PASSWORD)"; port="$(env_get BB_DB_PORT)"
  local h="127.0.0.1:${port:-54329}"
  cat <<EOF
set -a; . "$root/.env"; set +a
export BB_DSN=postgresql://bluebird:$pw@$h/bluebird_core
export BB_PUBLISH_DSN=postgresql://bb_publisher:$pw@$h/bluebird_publish
export BB_PUBLISH_MIGRATOR_DSN=postgresql://bb_migrator:$pw@$h/bluebird_publish
export BB_INBOX_DSN=postgresql://bb_inbox_reader:$pw@$h/bluebird_publish
export BB_SOURCES=$root/deploy/local/sources.toml BB_SEED_DIR=$rt/seed BB_SIGNAL_DIR=$rt/signals BB_ANON_SECRET=$rt/secrets/anon_secret
export BB_CONTEST_SOURCES=$root/deploy/local/contest-sources.toml
export PORTAL_DATABASE_URL=postgresql://bb_portal:$pw@$h/bluebird_publish
export BB_API_URL=http://127.0.0.1:$(env_get BB_API_PORT) BB_API_USERS=$rt/console/console_users.json
EOF
}

case "${1:-}" in
  init)   shift; cmd_init "$@" ;;
  cycle)  shift; cmd_cycle "$@" ;;
  up)     shift; dc up -d --build --wait "$@"; urls ;;
  down)   dc down ;;
  check)  job sources check ;;
  collect) shift; cmd_collect "$@" ;;
  policy) cmd_policy ;;
  export) shift; cmd_export "$@" ;;
  job)    shift; job "$@" ;;
  verify) exec "$root/deploy/local/verify.sh" ;;
  publish) cmd_publish ;;
  status) cmd_status ;;
  env)    cmd_env ;;
  tokens) cat "$rt/console_tokens" ;;
  logs)   shift; dc logs -f "$@" ;;
  *)      sed -n '2,14p' "$0"; exit 1 ;;
esac
