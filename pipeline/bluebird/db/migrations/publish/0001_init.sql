-- 공개존(Z3) publish DB 초기 스키마. core의 공개 허용 컬럼 부분집합만 둔다.
CREATE SCHEMA IF NOT EXISTS publish;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE publish.snapshot_log (
    bundle_id  text PRIMARY KEY,
    created_at timestamptz NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now(),
    stats      jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE publish.source (
    id      text PRIMARY KEY,
    name    text NOT NULL,
    license text NOT NULL,
    url     text NOT NULL
);

CREATE TABLE publish.idea (
    id            text PRIMARY KEY,
    source_id     text NOT NULL REFERENCES publish.source(id),
    contest_name  text NOT NULL,
    host_org      text NOT NULL,
    year          smallint,
    award         text,
    title         text NOT NULL,
    body          text,
    used_data     text[] NOT NULL,
    category      text,
    source_url    text
);
CREATE INDEX idea_year_idx ON publish.idea (year);
CREATE INDEX idea_title_trgm_idx ON publish.idea USING gin (title gin_trgm_ops);

-- 포털 계정(bluebird_portal)은 init 스크립트가 만든다. 읽기 전용.
GRANT USAGE ON SCHEMA publish TO bluebird_portal;
GRANT SELECT ON ALL TABLES IN SCHEMA publish TO bluebird_portal;
ALTER DEFAULT PRIVILEGES IN SCHEMA publish GRANT SELECT ON TABLES TO bluebird_portal;
