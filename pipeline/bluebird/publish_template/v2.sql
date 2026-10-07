-- 공개용 DB publish 스키마 템플릿 v2(v1 + 바뀐 것 포털 등록일, 시의성 근거). publisher가 search_path=publish_next, public 으로 실행한다.
-- 여기 있는 열만 DMZ로 나간다(열 허용목록). 바꾸면 새 버전 파일을 만들고 migrator가 등록한다.
CREATE TABLE source (
    id      text PRIMARY KEY,
    name    text NOT NULL,
    license text NOT NULL,
    url     text NOT NULL
);

CREATE TABLE idea (
    id              text PRIMARY KEY,
    source_id       text NOT NULL REFERENCES source(id),
    contest_name    text NOT NULL,
    host_org        text NOT NULL,
    year            smallint,
    award           text,
    title           text NOT NULL,
    body            text,
    used_data       text[] NOT NULL,
    category        text,
    source_url      text,
    card_kind       text,
    problem         text,
    solution        text,
    trace_status    text,
    external_search text
);
CREATE INDEX idea_year_idx ON idea (year);
CREATE INDEX idea_title_trgm_idx ON idea USING gin (title gin_trgm_ops);
CREATE INDEX idea_body_trgm_idx ON idea USING gin (body gin_trgm_ops);

CREATE TABLE evidence (
    id          bigint PRIMARY KEY,
    kind        text NOT NULL,
    url         text NOT NULL,
    title       text,
    excerpt     text,
    observed_at date
);

CREATE TABLE diagnosis (
    idea_id     text PRIMARY KEY REFERENCES idea(id),
    cause       char(1) NOT NULL,
    secondary   char(1),
    rationale   text,
    evidence_ids bigint[] NOT NULL
);

CREATE TABLE change (
    id           bigint PRIMARY KEY,
    idea_id      text NOT NULL REFERENCES idea(id),
    kind         text NOT NULL,
    tier         text,
    occurred_at  date NOT NULL,
    registered_at date,               -- dataset_opened: 포털 등록일(목록개방현황). tier 문구용
    title        text NOT NULL,
    url          text NOT NULL,
    what_changed text[] NOT NULL,
    how_now      text,
    evidence_ids bigint[] NOT NULL
);
CREATE INDEX change_idea_idx ON change (idea_id);
CREATE INDEX diagnosis_cause_idx ON diagnosis (cause);

CREATE TABLE timeliness (
    idea_id           text PRIMARY KEY REFERENCES idea(id),
    as_of             date NOT NULL,
    tech              smallint,
    data              smallint,
    regulation        smallint,
    policy            smallint,
    n_scored          smallint NOT NULL,
    s                 real,
    verdict           text NOT NULL,
    resolve_condition text,
    evidence_ids      bigint[] NOT NULL   -- 채점한 축마다 근거(G9)
);

CREATE TABLE weekly_top (
    week    date NOT NULL,
    rank    smallint NOT NULL,
    idea_id text NOT NULL REFERENCES idea(id),
    s       real,
    PRIMARY KEY (week, rank)
);

CREATE TABLE announcement (
    id         text PRIMARY KEY,
    title      text NOT NULL,
    org        text,
    apply_from date,
    apply_to   date,
    url        text NOT NULL
);
CREATE INDEX announcement_title_trgm_idx ON announcement USING gin (title gin_trgm_ops);

CREATE TABLE announcement_match (
    announcement_id text NOT NULL REFERENCES announcement(id),
    idea_id         text NOT NULL REFERENCES idea(id),
    rank            smallint NOT NULL,
    similarity      real,
    how_now         text,
    PRIMARY KEY (announcement_id, idea_id)
);
