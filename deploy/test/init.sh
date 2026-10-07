#!/usr/bin/env bash
# 시험 배포 초기화: 런타임 디렉터리·구역 키·.env·시드 파일 준비.
# 사용: deploy/test/init.sh [시드 원본 디렉터리]
#   시드 원본 기본값: reference/parangsae-src (인수인계 패키지)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
rt="$here/.runtime"
ref="${1:-$root/reference/parangsae-src}"

mkdir -p "$rt"/{keys/{z1,z2,z3},state/z1,seed} \
         "$rt"/xfer/z1/out-to-z2 \
         "$rt"/xfer/z2/{in-from-z1,out-to-z3,done,quarantine} \
         "$rt"/xfer/z3/{in-from-z2,done,quarantine}

run_cli() { (cd "$root/pipeline" && uv run --quiet bluebird "$@"); }

# 구역 키: 각 구역은 자기 개인키 + 보낸 구역의 공개키만 가진다.
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
if [[ ! -f "$rt/keys/z1/z1.key" ]]; then
  run_cli keygen --zone z1 --dir "$tmp" >/dev/null
  run_cli keygen --zone z2 --dir "$tmp" >/dev/null
  cp "$tmp"/z1.key "$tmp"/z1.anon_secret "$rt/keys/z1/"
  cp "$tmp"/z2.key "$tmp"/z1.pub "$rt/keys/z2/"
  cp "$tmp"/z2.pub "$rt/keys/z3/"
  echo "[init] zone keys created"
fi

if [[ ! -f "$here/.env" ]]; then
  {
    echo "CORE_DB_PASSWORD=$(openssl rand -hex 16)"
    echo "PUBLISH_DB_PASSWORD=$(openssl rand -hex 16)"
    echo "PORTAL_DB_PASSWORD=$(openssl rand -hex 16)"
    echo "BB_HTTP_PORT=8080"
  } > "$here/.env"
  chmod 600 "$here/.env"
  echo "[init] .env created"
fi

# 시드 파일(수집존 반입 디렉터리)
awards="$ref/03_pilot/source_data/awards_master_2013_2024.csv"
[[ -f "$awards" ]] && cp "$awards" "$rt/seed/" && echo "[init] seed: awards_master_2013_2024.csv"
kipris_zip="$ref/02_kipris_bulk/kipris_contest_bulk_utf8.zip"
if [[ -f "$kipris_zip" && ! -f "$rt/seed/kipris_idea_master.csv" ]]; then
  unzip -p "$kipris_zip" out/idea_master.csv > "$rt/seed/kipris_idea_master.csv"
  echo "[init] seed: kipris_idea_master.csv (내부 분석 전용, 공개 반출 안 됨)"
fi

# 컨테이너는 uid 10001로 실행된다. 시험 환경 한정으로 런타임 디렉터리 소유권을 맞춘다.
chmod -R a+rwX "$rt/xfer" "$rt/state"
chmod -R a+rX "$rt/keys" "$rt/seed"
echo "[init] done: $rt"
