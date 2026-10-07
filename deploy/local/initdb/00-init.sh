#!/bin/sh
# 로컬 DB 최초 기동(볼륨이 비어 있을 때 한 번): Postgres 하나에 원본 DB(bluebird_core)와 공개 DB(bluebird_publish).
# 역할은 쓰는 쪽마다 하나씩, 비밀번호는 .env의 DB_PASSWORD 하나를 같이 쓴다(로컬 데모용).
#   bluebird        : 슈퍼유저. 처리 작업(원본 DB)·관리
#   bb_api          : 콘솔 백엔드 API. 원본 DB 최소 권한(권한은 core 마이그레이션 0008이 준다)
#   bb_migrator     : 공개 DB 고정 스키마·템플릿 등록
#   bb_publisher    : 공개 DB 반영(publish_next 생성·교체)
#   bb_inbox_reader : 공개 DB의 이의 접수함 가져오기·삭제
#   bb_portal       : 포털. 공개 DB 읽기 + 이의 접수
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -v pw="$POSTGRES_PASSWORD" <<'SQL'
CREATE ROLE bb_api          LOGIN PASSWORD :'pw' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE bb_migrator     LOGIN PASSWORD :'pw' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE bb_publisher    LOGIN PASSWORD :'pw' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE bb_inbox_reader LOGIN PASSWORD :'pw' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE bb_portal       LOGIN PASSWORD :'pw' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE bluebird_publish;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname bluebird_core <<'SQL'
REVOKE ALL ON DATABASE bluebird_core FROM PUBLIC;
GRANT CONNECT ON DATABASE bluebird_core TO bb_api;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname bluebird_publish <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_trgm;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE bluebird_publish FROM PUBLIC;
GRANT CONNECT ON DATABASE bluebird_publish TO bb_migrator, bb_publisher, bb_inbox_reader, bb_portal;
GRANT CREATE ON DATABASE bluebird_publish TO bb_migrator, bb_publisher;
SQL
