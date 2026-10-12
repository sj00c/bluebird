-- 아이디어 선별 재료(docs/IDEA_POOL.md). 걸러내지 않는다 — 깔때기·카드·공개는 그대로 전체를 본다.
-- 어떤 아이디어를 사업화 추적 대상으로 삼을지는 사람이 나중에 이 필드들로 고른다.
--
--   core.source.record_kind : 기록 종류. 수상작 / 출품작 / 국민·주민 제안 / 직원 개선제안. TOML 레지스트리에서 동기화.
--   core.contest.audience   : 대회 대상자. student = 초·중·고 학생 대회. 이름 규칙으로 초기화하고 사람이 고친다.
--   core.idea.norm_title    : 공백 제거·소문자 제목. 같은 제목 묶음(core.idea_dup)을 만드는 키.
--   core.idea_dup           : 같은 제목이 여러 번 들어간 것. 정보용. 깔때기는 이것을 보지 않는다.

ALTER TABLE core.source
    ADD COLUMN record_kind text
        CHECK (record_kind IN ('contest_award', 'contest_submission', 'public_proposal', 'improvement_proposal'));

ALTER TABLE core.contest
    ADD COLUMN audience text NOT NULL DEFAULT 'unknown' CHECK (audience IN ('student', 'general', 'unknown'));

-- 대회 이름으로 초·중·고 학생 대회를 표시한다. '대학생'은 학생으로 보지 않는다.
CREATE FUNCTION core.contest_audience(name text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN name ~ '(^|[^대])학생|청소년|초등|중학|고등학|어린이|유아|과학전람회|과학발명품|발명전시회|탐구발표'
                THEN 'student' ELSE 'unknown' END
$$;

UPDATE core.contest SET audience = core.contest_audience(name) WHERE audience = 'unknown';

ALTER TABLE core.idea
    ADD COLUMN norm_title text GENERATED ALWAYS AS (lower(regexp_replace(title, '\s', '', 'g'))) STORED;
CREATE INDEX idea_norm_title_idx ON core.idea (norm_title);

CREATE TABLE core.idea_dup (
    idea_id      text PRIMARY KEY REFERENCES core.idea(id),
    canonical_id text NOT NULL REFERENCES core.idea(id),
    method       text NOT NULL CHECK (method IN ('norm_title', 'human')),
    decided_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (idea_id <> canonical_id)
);
CREATE INDEX idea_dup_canonical_idx ON core.idea_dup (canonical_id);

-- 제목(공백 제거·소문자) 6자 이상이 같은 묶음. 대표 = 본문 있음 > 연도 빠른 것 > id. 사람이 정한 묶음(human)은 그대로 둔다.
CREATE FUNCTION core.refresh_idea_dup() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE inserted integer;
BEGIN
    DELETE FROM core.idea_dup WHERE method = 'norm_title';
    WITH live AS (
        SELECT id, norm_title, year, body IS NOT NULL AS has_body
          FROM core.idea WHERE retired_at IS NULL AND length(norm_title) >= 6
    ),
    g AS (
        SELECT id,
               first_value(id) OVER (PARTITION BY norm_title ORDER BY has_body DESC, year NULLS LAST, id) AS canon,
               count(*) OVER (PARTITION BY norm_title) AS members
          FROM live
    ),
    ins AS (
        INSERT INTO core.idea_dup (idea_id, canonical_id, method)
        SELECT id, canon, 'norm_title' FROM g WHERE members > 1 AND id <> canon
        ON CONFLICT (idea_id) DO NOTHING
        RETURNING 1
    )
    SELECT count(*) INTO inserted FROM ins;
    RETURN inserted;
END
$$;

GRANT SELECT ON core.idea_dup TO bb_api;
