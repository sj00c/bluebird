-- 처리존(Z2) core DB 초기 스키마
CREATE SCHEMA IF NOT EXISTS core;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE core.bundle_log (
    bundle_id    text PRIMARY KEY,
    zone         text NOT NULL,
    kind         text NOT NULL,
    source       text NOT NULL,
    created_at   timestamptz NOT NULL,
    applied_at   timestamptz NOT NULL DEFAULT now(),
    stats        jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE core.source (
    id         text PRIMARY KEY,
    name       text NOT NULL,
    license    text NOT NULL,
    url        text NOT NULL DEFAULT '',
    layer      smallint NOT NULL CHECK (layer IN (1, 2, 3)),
    public_ok  boolean NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.contest (
    id        text PRIMARY KEY,
    source_id text NOT NULL REFERENCES core.source(id),
    name      text NOT NULL,
    host_org  text NOT NULL DEFAULT '',
    year      smallint
);

CREATE TABLE core.idea (
    id               text PRIMARY KEY,
    source_id        text NOT NULL REFERENCES core.source(id),
    contest_id       text NOT NULL REFERENCES core.contest(id),
    year             smallint,
    award            text,
    title            text NOT NULL,
    body             text,
    used_data        text[] NOT NULL DEFAULT '{}',
    category         text,
    team_kind        text NOT NULL CHECK (team_kind IN ('empty', 'masked', 'person', 'brand')),
    source_url       text,
    extra            jsonb NOT NULL DEFAULT '{}',
    first_bundle_id  text NOT NULL REFERENCES core.bundle_log(bundle_id) DEFERRABLE INITIALLY DEFERRED,
    last_bundle_id   text NOT NULL REFERENCES core.bundle_log(bundle_id) DEFERRABLE INITIALLY DEFERRED,
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idea_source_idx ON core.idea (source_id);
CREATE INDEX idea_year_idx ON core.idea (year);

CREATE TABLE core.pipeline_run (
    id          bigserial PRIMARY KEY,
    stage       text NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text NOT NULL CHECK (status IN ('running', 'ok', 'failed')),
    stats       jsonb NOT NULL DEFAULT '{}',
    error       text
);
