#!/bin/sh
# DMZ 공개용 DB 최초 기동: 역할 4개 + 확장 + 접속 규칙(pg_hba).
#   bb_migrator     : 고정 스키마(meta, inbox) 마이그레이션·템플릿 등록      (업무망에서만)
#   bb_publisher    : publish_next 생성·적재·RENAME 교체                   (업무망에서만)
#   bb_inbox_reader : inbox 이의 pull(SELECT·DELETE)                      (업무망에서만)
#   bb_portal       : publish 읽기 + inbox INSERT                         (DMZ portal)
# superuser(bluebird)는 컨테이너 안 로컬 소켓으로만 접속한다. 원격은 거부.
# 운영은 역할별 원격 IP를 고정한다(deploy/prod/postgres/pg_hba.publish.conf).
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v migrator="$MIGRATOR_DB_PASSWORD" -v publisher="$PUBLISHER_DB_PASSWORD" \
  -v inbox="$INBOX_DB_PASSWORD" -v portal="$PORTAL_DB_PASSWORD" <<'SQL'
CREATE ROLE bb_migrator     LOGIN PASSWORD :'migrator'  NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE bb_publisher    LOGIN PASSWORD :'publisher' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE bb_inbox_reader LOGIN PASSWORD :'inbox'     NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE bb_portal       LOGIN PASSWORD :'portal'    NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE bluebird_publish FROM PUBLIC;
GRANT CONNECT ON DATABASE bluebird_publish TO bb_migrator, bb_publisher, bb_inbox_reader, bb_portal;
GRANT CREATE ON DATABASE bluebird_publish TO bb_migrator, bb_publisher;
SQL

cat > "$PGDATA/pg_hba.conf" <<'HBA'
# TYPE  DATABASE          USER                                              ADDRESS  METHOD
local   all               all                                                        trust
host    all               bluebird                                          all      reject
host    bluebird_publish  bb_migrator,bb_publisher,bb_inbox_reader,bb_portal all      scram-sha-256
host    all               all                                               all      reject
HBA
