#!/bin/sh
# 공개존 DB 최초 기동 시 포털 읽기 전용 계정 생성. 권한 부여는 publish 마이그레이션이 한다.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v pw="$PORTAL_DB_PASSWORD" <<'SQL'
CREATE ROLE bluebird_portal LOGIN PASSWORD :'pw' NOSUPERUSER NOCREATEDB NOCREATEROLE;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
