-- 제외 후보 이유(docs/IDEA_POOL.md). 걸러내지 않는다. 아이디어마다 "뺀다면 이 이유로"를 기록해 두고,
-- 어떤 이유를 실제로 적용할지는 사람이 나중에 고른다. 깔때기·카드·공개는 이 표를 보지 않는다.
--
--   core.exclusion_reason : 이유 어휘. 근거 위치(basis)가 소스/대회/제목 중 어디인지 적는다.
--   core.source.exclude_reason : 소스 단위 편집 판단(예: 상품화 뒤 받는 인증). TOML 레지스트리에서 동기화.
--   core.idea_exclusion   : 아이디어 × 이유. 규칙 행(decided_by='rule')은 refresh 때 다시 계산하고, 사람 행은 그대로 둔다.

CREATE TABLE core.exclusion_reason (
    code  text PRIMARY KEY,
    label text NOT NULL,
    basis text NOT NULL CHECK (basis IN ('source', 'contest', 'title')),
    note  text NOT NULL
);
INSERT INTO core.exclusion_reason (code, label, basis, note) VALUES
    ('student_contest',      '초·중·고 학생 대회',        'contest', 'core.contest.audience = student. 대회 이름 규칙으로 초기화, 사람이 고친다'),
    ('public_proposal',      '참여예산·국민/주민 제안',   'source',  'core.source.record_kind = public_proposal. 공모전 수상작이 아니다'),
    ('improvement_proposal', '직원 개선제안',             'source',  'core.source.record_kind = improvement_proposal. 기관 내부 제안'),
    ('certified_product',    '상품화 뒤 받는 인증',       'source',  'core.source.exclude_reason. 이미 제품이 된 것에 주는 상(굿디자인 등)'),
    ('internal_activity',    '기관 내부 활동 사례',       'source',  'core.source.exclude_reason. 품질분임조·적극행정 등'),
    ('teaching_case',        '수업·교육 사례',            'source',  'core.source.exclude_reason'),
    ('duplicate_title',      '같은 제목이 이미 있음',     'title',   'core.idea_dup. 대표 1건은 이 이유가 붙지 않는다');

ALTER TABLE core.source
    ADD COLUMN exclude_reason text REFERENCES core.exclusion_reason(code);

CREATE TABLE core.idea_exclusion (
    idea_id    text NOT NULL REFERENCES core.idea(id),
    reason     text NOT NULL REFERENCES core.exclusion_reason(code),
    decided_by text NOT NULL DEFAULT 'rule',          -- rule | 사람 식별자
    decided_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (idea_id, reason)
);
CREATE INDEX idea_exclusion_reason_idx ON core.idea_exclusion (reason);

-- 규칙 행을 다시 계산한다. 사람이 넣은 행(decided_by <> 'rule')은 건드리지 않는다.
CREATE FUNCTION core.refresh_idea_exclusion() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE inserted integer;
BEGIN
    DELETE FROM core.idea_exclusion WHERE decided_by = 'rule';
    WITH live AS (
        SELECT i.id, c.audience, s.record_kind, s.exclude_reason
          FROM core.idea i
          JOIN core.contest c ON c.id = i.contest_id
          JOIN core.source s ON s.id = i.source_id
         WHERE i.retired_at IS NULL
    ),
    want AS (
        SELECT id, 'student_contest' AS reason FROM live WHERE audience = 'student'
        UNION ALL
        SELECT id, record_kind FROM live WHERE record_kind IN ('public_proposal', 'improvement_proposal')
        UNION ALL
        SELECT id, exclude_reason FROM live WHERE exclude_reason IS NOT NULL
        UNION ALL
        SELECT d.idea_id, 'duplicate_title' FROM core.idea_dup d JOIN live ON live.id = d.idea_id
    ),
    ins AS (
        INSERT INTO core.idea_exclusion (idea_id, reason)
        SELECT DISTINCT id, reason FROM want
        ON CONFLICT (idea_id, reason) DO NOTHING
        RETURNING 1
    )
    SELECT count(*) INTO inserted FROM ins;
    RETURN inserted;
END
$$;

GRANT SELECT ON core.exclusion_reason, core.idea_exclusion TO bb_api;
