#!/usr/bin/env bash
# 파랑새 로컬 데모 실행기. 상세 = README.md
#   ./demo.sh init            처음 한 번: .env·익명화 키·콘솔 토큰·원본 seed 준비
#   ./demo.sh cycle [ingest 인수]  빌드 → 원본 적재·소스 점검·카탈로그 → 승인분 공개 → 화면 기동
#   ./demo.sh up [서비스…]     서비스 켜기(기본 전부, 개발 때는 `up db`)
#   ./demo.sh down            끄기(데이터 유지). 데이터 삭제 = docker compose down -v
#   ./demo.sh check           외부 API·원본 파일 연결 점검표
#   ./demo.sh collect [인수…]   검증된 공식 공모전·제안 원본 수집 → 비공개 DB 적재
#   ./demo.sh policy          레지스트리 정책·선별 재료(기록 종류·제외 후보 이유)만 DB에 반영, 파일 재수집 없음
#   ./demo.sh schedule [off]  국민신문고 공개제안 매일 00:30 수집(launchd). off = 해제
#   ./demo.sh export          공유용 xlsx(전체, share 열로 가능/보류 구분) + 소스 표(docs/DATA.md) → .runtime/export/
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
  # 원본 파일 위치. 기본 data/seed/ (git 밖). 인수인계 zip 사용 = ./demo.sh init <zip 풀린 디렉터리>
  local ref="${1:-}"
  mkdir -p "$rt"/{secrets,seed,console}
  # .env: 예시 복사 + 빈 DB 비밀번호만 생성. 기존 값·키 유지
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
  # 익명화 비밀키: 익명 ID(HMAC) 기준. 변경 시 전 ID 변경 → 1회 생성 후 유지
  if [[ ! -f "$rt/secrets/anon_secret" ]]; then
    openssl rand -hex 32 > "$rt/secrets/anon_secret"
    echo "[init] anon_secret created"
  fi
  # 콘솔 로그인 토큰: 원문 = .runtime/console_tokens(미마운트), API = sha256만(console_users.json)
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
  # 원본 seed. git 제외. 파일명·다운로드 위치 = deploy/local/sources.toml url
  #   data/seed/<파일명>  — 직접 다운로드(기본)
  #   <ref>/03_pilot/source_data/<파일명> — 인수인계 디렉터리 인수 지정 시. KIPRIS = API 수집(collect), 벌크 zip 미사용
  seed() { if [[ -f "$1" ]]; then cp "$1" "$rt/seed/$2" && echo "[init] seed: $2"; else echo "[init] missing (skip): $2"; fi; }
  local sd="$root/data/seed" f
  for f in awards_master_2013_2024.csv gov_opendata_startup_contest_final_awards_2019_2025.xlsx \
           national_science_museum_awards_20240909.csv mafra_agrifood_bigdata_contest_info.csv \
           public_design_idea_15138745.csv; do
    if [[ -f "$sd/$f" ]]; then seed "$sd/$f" "$f"
    elif [[ -n "$ref" && -f "$ref/03_pilot/source_data/$f" ]]; then seed "$ref/03_pilot/source_data/$f" "$f"
    else echo "[init] missing (skip): $f"; fi
  done
  # 목록개방현황 스냅샷 #0(2026-10-06 다운로드). cycle 최초 1회 적재. 없으면 건너뜀
  local snap0 sha=f63f4429e90c69992fb0853e59d46ee0853c0aee678e17b95492405858654f4c
  for snap0 in "$sd/catalog_snapshot0_2026-10-06.csv" "$root/data/opendata/catalog.csv"; do
    [[ -f "$snap0" ]] || continue
    [[ "$(shasum -a 256 "$snap0" | cut -d' ' -f1)" == "$sha" ]] || { echo "[init] $snap0 sha256 mismatch" >&2; exit 1; }
    seed "$snap0" catalog_snapshot0_2026-10-06.csv; break
  done
  # 컨테이너 uid 10001. 읽기 권한 부여
  chmod -R a+rX "$rt/seed"
  chmod 755 "$rt/secrets" "$rt/console"; chmod 644 "$rt/secrets/anon_secret" "$rt/console/console_users.json"
  echo "[init] done. 키 → .env, 다음 ./demo.sh cycle"
}

cmd_cycle() {
  dc build -q
  dc up -d --wait db
  job migrate --target core
  job migrate --target publish
  job ingest "$@"
  # 분석·분류·매칭 = 명시적 별도 job. 원본 적재 = 판정 생성 없음
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
    --config /config/design-contest-sources.toml \
    --config /config/api-sources.toml "$@"
}

# 레지스트리 4개 정책 필드(public_ok·export_grade·record_kind·exclude_reason) DB 동기화 + 선별 재료(학생 대회·중복·제외 후보 이유) 재계산. 파일 재수집 없음
# 공유용 내보내기. xlsx → .runtime/export/, 소스 표 → docs/DATA.md(레포 포함)
cmd_export() {
  mkdir -p "$rt/export"; chmod 777 "$rt/export"
  local name; name="bluebird_ideas_$(date +%Y%m%d)"
  job export xlsx --out "/export/$name.xlsx"
  job export provenance --config /config/sources.toml --config /config/contest-sources.toml \
    --config /config/science-contest-sources.toml --config /config/design-contest-sources.toml \
    --config /config/api-sources.toml --out /export/DATA.md
  cp "$rt/export/DATA.md" "$root/docs/DATA.md"
  echo "[export] $rt/export/$name.xlsx · docs/DATA.md"
}

# 국민신문고 공개제안 = 일 10,000회 한도로 매일 이어 받음. launchd 사용자 에이전트(이 Mac 로그인 중일 때만)
cmd_schedule() {
  local label=dev.bluebird.acrc-daily
  local plist="$HOME/Library/LaunchAgents/$label.plist"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  if [[ "${1:-}" == off ]]; then rm -f "$plist"; echo "[schedule] off"; return; fi
  mkdir -p "$rt/logs" "$HOME/Library/LaunchAgents"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array>
    <string>$root/demo.sh</string><string>collect</string><string>--only</string><string>acrc_open_proposals</string>
  </array>
  <key>WorkingDirectory</key><string>$root</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>$rt/logs/acrc-daily.log</string>
  <key>StandardErrorPath</key><string>$rt/logs/acrc-daily.log</string>
</dict></plist>
EOF
  launchctl bootstrap "gui/$(id -u)" "$plist"
  echo "[schedule] $label 매일 00:30 → $rt/logs/acrc-daily.log"
}

cmd_policy() {
  job ingest --policy-only \
    --config /config/sources.toml \
    --config /config/contest-sources.toml \
    --config /config/science-contest-sources.toml \
    --config /config/design-contest-sources.toml \
    --config /config/api-sources.toml
}

cmd_publish() {
  job objections pull
  job top
  job publish
  echo "[publish] 현재 승인분 반영 완료. 미승인 분석 비공개."
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
  # 호스트 uv run bluebird / npm run dev 용 접속 정보(DB = 127.0.0.1:BB_DB_PORT)
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
  schedule) shift; cmd_schedule "$@" ;;
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
