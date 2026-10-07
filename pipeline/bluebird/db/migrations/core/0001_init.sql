-- 업무망 core DB 스키마(계획 §3.2). W0에 1회 재작성. 이후 변경은 0002+ 추가만 한다(체크섬 가드).
CREATE SCHEMA IF NOT EXISTS core;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ------------------------------------------------------------------ 원천
CREATE TABLE core.source (
    id                 text PRIMARY KEY,
    name               text NOT NULL,
    license            text NOT NULL,
    url                text NOT NULL DEFAULT '',
    layer              smallint NOT NULL CHECK (layer IN (1, 2, 3)),
    public_ok          boolean NOT NULL,                       -- 공개 관문(DMZ 반영)
    export_grade       text NOT NULL CHECK (export_grade IN ('O', 'pending', 'deny')),  -- 반출 관문(외부 호출)
    body_present       boolean NOT NULL DEFAULT false,
    policy_approved_by text,
    policy_approved_at timestamptz,
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT public_ok OR policy_approved_at IS NOT NULL)
);

CREATE TABLE core.ingest_run (
    id          bigserial PRIMARY KEY,
    source_id   text NOT NULL REFERENCES core.source(id),
    file_sha256 text,
    api_cursor  text,
    rows        integer,
    status      text NOT NULL CHECK (status IN ('running', 'ok', 'failed', 'skipped')),
    error       text,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

CREATE TABLE core.contest (
    id        text PRIMARY KEY,
    source_id text NOT NULL REFERENCES core.source(id),
    name      text NOT NULL,
    host_org  text NOT NULL DEFAULT '',
    year      smallint
);

-- 팀명 원문은 저장하지 않는다(team_kind만).
CREATE TABLE core.idea (
    id              text PRIMARY KEY,
    source_id       text NOT NULL REFERENCES core.source(id),
    contest_id      text NOT NULL REFERENCES core.contest(id),
    year            smallint,
    award           text,
    title           text NOT NULL,
    body            text,
    used_data       text[] NOT NULL DEFAULT '{}',
    category        text,
    team_kind       text NOT NULL CHECK (team_kind IN ('empty', 'masked', 'person', 'brand')),
    source_url      text,
    extra           jsonb NOT NULL DEFAULT '{}',
    first_ingest_id bigint NOT NULL REFERENCES core.ingest_run(id),
    last_ingest_id  bigint NOT NULL REFERENCES core.ingest_run(id),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idea_source_idx ON core.idea (source_id);
CREATE INDEX idea_year_idx ON core.idea (year);
CREATE INDEX idea_title_trgm_idx ON core.idea USING gin (title gin_trgm_ops);

-- ------------------------------------------------------------------ 근거
CREATE TABLE core.evidence (
    id           bigserial PRIMARY KEY,
    kind         text NOT NULL,             -- body_excerpt | dataset | law | announcement | news | patent | manual
    url          text NOT NULL CHECK (url ~ '^https?://'),
    title        text,
    excerpt      text,
    observed_at  date,
    collected_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, url, excerpt)
);
CREATE TABLE core.x_evidence (
    target_type text NOT NULL CHECK (target_type IN ('diagnosis', 'change_match', 'timeliness', 'trace')),
    target_id   text NOT NULL,
    evidence_id bigint NOT NULL REFERENCES core.evidence(id),
    PRIMARY KEY (target_type, target_id, evidence_id)
);

-- ------------------------------------------------------------------ 카드
CREATE TABLE core.idea_card (
    idea_id        text PRIMARY KEY REFERENCES core.idea(id),
    card_kind      text NOT NULL CHECK (card_kind IN ('full', 'local_extract', 'title_only')),
    title          text NOT NULL,
    problem        text,
    solution       text,
    target_user    text,
    missing_data   jsonb NOT NULL DEFAULT '[]',   -- [{name, excerpt, char_span, origin: body|used_data_unopened}]
    used_data      text[] NOT NULL DEFAULT '{}',
    required_tech  text[] NOT NULL DEFAULT '{}',
    domain         text,
    year           smallint,
    source_url     text,
    extractor      text NOT NULL CHECK (extractor IN ('llm', 'rule', 'human')),
    model          text,
    prompt_version text,
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.idea_embedding (
    idea_id      text NOT NULL REFERENCES core.idea(id),
    model        text NOT NULL,
    model_sha256 text NOT NULL,
    vec          vector(1024) NOT NULL,
    PRIMARY KEY (idea_id, model)
);

-- ------------------------------------------------------------------ 흔적
CREATE TABLE core.trace_check (
    idea_id        text NOT NULL REFERENCES core.idea(id),
    item           text NOT NULL CHECK (item IN ('news_web', 'ip', 'ip_local', 'similar_local', 'manual')),
    result         text NOT NULL CHECK (result IN ('found', 'none', 'not_run')),
    query_fields   text[] NOT NULL DEFAULT '{}',
    detail         jsonb NOT NULL DEFAULT '{}',
    egress_call_id bigint,
    checked_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (idea_id, item)
);
CREATE TABLE core.trace_verdict (
    idea_id          text PRIMARY KEY REFERENCES core.idea(id),
    status           text NOT NULL CHECK (status IN ('realized', 'pivot', 'similar_unlinked', 'award_only', 'none', 'pending')),
    profile_version  text NOT NULL CHECK (profile_version IN ('full_v1', 'kipris_local_v1')),
    external_search  text NOT NULL CHECK (external_search IN ('done', 'not_done')),
    confidence       real,
    model            text,
    prompt_version   text,
    decided_at       timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ 막힌 이유
CREATE TABLE core.diagnosis (
    idea_id        text PRIMARY KEY REFERENCES core.idea(id),
    "primary"      char(1) NOT NULL CHECK ("primary" IN ('T', 'D', 'R', 'M', 'C', 'O', 'U')),
    secondary      char(1) CHECK (secondary IN ('T', 'D', 'R', 'M', 'C', 'O', 'U')),
    confidence     real,
    rationale      text,
    extractor      text NOT NULL CHECK (extractor IN ('llm', 'rule', 'human')),
    model          text,
    prompt_version text,
    decided_at     timestamptz NOT NULL DEFAULT now()
);

-- 원인 D는 카드에 본문이 밝힌 부족 데이터(missing_data)가 있을 때만 허용한다.
-- 비-U 원인은 근거(x_evidence)가 1개 이상 있어야 한다(트랜잭션 끝에 검사).
CREATE FUNCTION core.check_diagnosis() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW."primary" = 'D' AND NOT EXISTS (
        SELECT 1 FROM core.idea_card c WHERE c.idea_id = NEW.idea_id AND jsonb_array_length(c.missing_data) > 0
    ) THEN
        RAISE EXCEPTION 'diagnosis D requires idea_card.missing_data (idea %)', NEW.idea_id;
    END IF;
    IF NEW."primary" <> 'U' AND NOT EXISTS (
        SELECT 1 FROM core.x_evidence x WHERE x.target_type = 'diagnosis' AND x.target_id = NEW.idea_id
    ) THEN
        RAISE EXCEPTION 'diagnosis % requires evidence (idea %)', NEW."primary", NEW.idea_id;
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER diagnosis_evidence_check
    AFTER INSERT OR UPDATE ON core.diagnosis DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION core.check_diagnosis();

-- ------------------------------------------------------------------ 바뀐 것
CREATE TABLE core.catalog_snapshot (
    id          integer PRIMARY KEY,
    taken_at    date NOT NULL UNIQUE,
    file_name   text NOT NULL,
    file_sha256 text NOT NULL UNIQUE,
    rows        integer NOT NULL,
    weekday     smallint NOT NULL,
    loaded_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE core.signal_dataset (
    public_data_pk         text PRIMARY KEY,
    org_code               text NOT NULL,
    org                    text NOT NULL,
    title                  text NOT NULL,
    title_norm             text NOT NULL,
    category               text,
    keywords               text,
    description            text,
    registered_at          date,
    modified_at            date,
    license                text,
    url                    text,
    first_seen_snapshot_id integer NOT NULL REFERENCES core.catalog_snapshot(id),
    last_seen_snapshot_id  integer NOT NULL REFERENCES core.catalog_snapshot(id),
    first_seen_at          date NOT NULL,
    tier                   text NOT NULL CHECK (tier IN ('observed_new', 'reappeared', 'portal_registered')),
    rereg_of               text REFERENCES core.signal_dataset(public_data_pk),
    vec                    vector(1024)
);
CREATE INDEX signal_dataset_dedup_idx ON core.signal_dataset (org_code, title_norm);
CREATE INDEX signal_dataset_first_seen_idx ON core.signal_dataset (first_seen_at);
CREATE INDEX signal_dataset_title_trgm_idx ON core.signal_dataset USING gin (title gin_trgm_ops);

CREATE TABLE core.announcement (
    id         text PRIMARY KEY,
    source     text NOT NULL,                     -- kstartup | manual
    title      text NOT NULL,
    summary    text,
    org        text,
    apply_from date,
    apply_to   date,
    url        text NOT NULL CHECK (url ~ '^https?://'),
    vec        vector(1024),
    loaded_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.condition_change (
    id          text PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN ('dataset_opened', 'law_effective', 'announcement', 'policy_news', 'tech')),
    ref_id      text NOT NULL,
    occurred_at date NOT NULL,
    tier        text,
    url         text NOT NULL CHECK (url ~ '^https?://'),
    title       text NOT NULL,
    UNIQUE (kind, ref_id)
);

CREATE TABLE core.cause_change_kind (
    cause char(1) NOT NULL,
    kind  text NOT NULL,
    PRIMARY KEY (cause, kind)
);
INSERT INTO core.cause_change_kind VALUES
    ('D', 'dataset_opened'), ('R', 'law_effective'), ('C', 'announcement'), ('M', 'policy_news'), ('T', 'tech');

CREATE TABLE core.change_match (
    id             bigserial PRIMARY KEY,
    change_id      text NOT NULL REFERENCES core.condition_change(id),
    idea_id        text NOT NULL REFERENCES core.idea(id),
    similarity     real,
    llm_verdict    text CHECK (llm_verdict IN ('yes', 'partial', 'no', 'human')),
    what_changed   text[] NOT NULL DEFAULT '{}',
    how_now        text,
    model          text,
    prompt_version text,
    status         text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'approved', 'rejected')),
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (change_id, idea_id)
);

CREATE TABLE core.timeliness (
    idea_id           text NOT NULL REFERENCES core.idea(id),
    as_of             date NOT NULL,
    tech              smallint CHECK (tech BETWEEN 0 AND 5),
    data              smallint CHECK (data BETWEEN 0 AND 5),
    regulation        smallint CHECK (regulation BETWEEN 0 AND 5),
    policy            smallint CHECK (policy BETWEEN 0 AND 5),
    weights           jsonb NOT NULL,
    n_scored          smallint NOT NULL,
    s                 real,
    verdict           text NOT NULL CHECK (verdict IN ('now', 'conditional', 'hold')),
    resolve_condition text,
    PRIMARY KEY (idea_id, as_of),
    CHECK (verdict = 'hold' OR n_scored >= 2)
);

CREATE TABLE core.weekly_top (
    week          date NOT NULL,
    rank          smallint NOT NULL CHECK (rank BETWEEN 1 AND 20),
    idea_id       text NOT NULL REFERENCES core.idea(id),
    s             real,
    source_family text NOT NULL,
    computed_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (week, rank),
    UNIQUE (week, idea_id)
);

-- ------------------------------------------------------------------ 검토·승인·이의
CREATE TABLE core.review (
    id          bigserial PRIMARY KEY,
    target_type text NOT NULL CHECK (target_type IN ('idea', 'card', 'diagnosis', 'change_match', 'timeliness', 'objection')),
    target_id   text NOT NULL,
    reviewer    text NOT NULL,
    round       text NOT NULL CHECK (round IN ('coder_a', 'coder_b', 'final', 'expert', 'audit')),
    decision    text NOT NULL CHECK (decision IN ('approve', 'reject', 'code')),
    code        char(1) CHECK (code IN ('T', 'D', 'R', 'M', 'C', 'O', 'U')),
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX review_target_idx ON core.review (target_type, target_id);

CREATE TABLE core.publication (
    target_type text NOT NULL,
    target_id   text NOT NULL,
    scope       text NOT NULL CHECK (scope IN ('card', 'diagnosis', 'change', 'timeliness')),
    approved_by text NOT NULL,
    approved_at timestamptz NOT NULL DEFAULT now(),
    revoked_at  timestamptz,
    PRIMARY KEY (target_type, target_id, scope)
);

CREATE TABLE core.objection (
    id         bigserial PRIMARY KEY,
    dmz_id     bigint NOT NULL UNIQUE,
    idea_id    text NOT NULL,
    kind       text NOT NULL,
    body       text NOT NULL,
    status     text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'rejected')),
    resolution text,
    submitted_at timestamptz NOT NULL,
    pulled_at  timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

-- ------------------------------------------------------------------ 반출 통제·점검
CREATE TABLE core.export_policy (
    source_id text NOT NULL,          -- '*' = 모든 소스
    field     text NOT NULL,
    purpose   text NOT NULL CHECK (purpose IN ('collect', 'signal', 'trace', 'llm', 'source_check')),
    allowed   boolean NOT NULL,
    PRIMARY KEY (source_id, field, purpose)
);

CREATE TABLE core.egress_call (
    id             bigserial PRIMARY KEY,
    purpose        text NOT NULL CHECK (purpose IN ('collect', 'signal', 'trace', 'llm', 'source_check')),
    dest_host      text NOT NULL,
    path_template  text NOT NULL,
    source_ids     text[] NOT NULL DEFAULT '{}',
    fields_sent    text[] NOT NULL DEFAULT '{}',
    payload_sha256 text,
    bytes_out      integer,
    bytes_in       integer,
    http_status    integer,
    decision       text NOT NULL CHECK (decision IN ('allowed', 'blocked')),
    reason         text,
    tokens_in      integer,
    tokens_out     integer,
    cost_est       numeric(10, 4),
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.source_check (
    id              bigserial PRIMARY KEY,
    source_id       text NOT NULL,
    status          text NOT NULL CHECK (status IN ('ok', 'key_required', 'blocked', 'error')),
    http_status     integer,
    rows            integer,
    sample          jsonb,
    license         text,
    refresh_cadence text,
    note            text,
    checked_at      timestamptz NOT NULL DEFAULT now(),
    egress_call_id  bigint REFERENCES core.egress_call(id)
);

CREATE TABLE core.publish_snapshot (
    id                bigserial PRIMARY KEY,
    created_at        timestamptz NOT NULL DEFAULT now(),
    template_version  text NOT NULL,
    template_sha256   text NOT NULL,
    rows              jsonb NOT NULL
);

CREATE TABLE core.pipeline_run (
    id          bigserial PRIMARY KEY,
    stage       text NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text NOT NULL CHECK (status IN ('running', 'ok', 'failed')),
    stats       jsonb NOT NULL DEFAULT '{}',
    error       text
);
