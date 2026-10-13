-- 같은 아이디어의 여러 기록 묶음 + 내용 부족 표시(2026-10-13). 0014에서 폐지한 "제목만 같음" 대신 내용 기준.
-- 선별 재료일 뿐 걸러내지 않는다. 깔때기·카드·공개는 그대로 전체.
--
--   same_body  : 공백 제거 본문(50자 이상)이 같음. 참여예산 다음 해 재제출, 국민신문고 중복 등록, KIPRIS 2회 출품
--   same_entry : 정규화 대회명(회차·연도·공백 제거)이 비어 있지 않고 같음 + 연도 차 1 이내 + 정규화 제목(6자 이상) 같음 + 소스 다름.
--                과학관 출품작 목록 ↔ 수상작 목록 ↔ KIPRIS 아이디어DB. 대회명 없는 참여예산끼리는 묶지 않는다
--                (지역이 달라 "CCTV 설치" 같은 흔한 제목이 서로 다른 제안이다).
--   묶음 대표 = 공개 허용 소스 → 본문 긴 것 → 수상 정보 있는 것 → 이른 연도 → id. 대표 외 = duplicate_record.
--   thin_record : 본문 20자 미만 + 같은 정규화 제목의 서로 다른 아이디어가 3건 이상(참여예산 사업 분류명 등). 제목만으로 구분 불가.

CREATE FUNCTION core.title_key(t text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS
$$ SELECT lower(regexp_replace(t, '[^[:alnum:]가-힣]', '', 'g')) $$;

CREATE FUNCTION core.contest_key(t text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS
$$ SELECT regexp_replace(t, '제?\s*[0-9]+\s*회|[0-9]{4}|\s', '', 'g') $$;

CREATE FUNCTION core.body_key(t text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS
$$ SELECT regexp_replace(coalesce(t, ''), '\s', '', 'g') $$;

ALTER TABLE core.exclusion_reason DROP CONSTRAINT exclusion_reason_basis_check;
ALTER TABLE core.exclusion_reason ADD CONSTRAINT exclusion_reason_basis_check
    CHECK (basis IN ('source', 'contest', 'title', 'content'));
INSERT INTO core.exclusion_reason (code, label, basis, note) VALUES
    ('duplicate_record', '같은 아이디어의 다른 기록', 'content',
     'core.idea_duplicate. 본문 같음(재제출·중복 등록) 또는 같은 대회·연도(±1)·제목(출품작 목록·수상작 목록·KIPRIS). 묶음 대표 1건은 이 이유가 붙지 않는다'),
    ('thin_record', '내용 부족', 'content',
     '본문 20자 미만 + 같은 제목의 다른 아이디어 3건 이상(참여예산 사업 분류명 등). 제목만으로 아이디어 구분 불가');

CREATE TABLE core.idea_duplicate (
    idea_id      text PRIMARY KEY REFERENCES core.idea(id),
    canonical_id text NOT NULL REFERENCES core.idea(id),
    rules        text[] NOT NULL CHECK (rules <@ ARRAY['same_body', 'same_entry'] AND cardinality(rules) > 0),
    CHECK (idea_id <> canonical_id)
);
CREATE INDEX idea_duplicate_canonical_idx ON core.idea_duplicate (canonical_id);

CREATE FUNCTION core.refresh_idea_duplicate() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE changed integer;
BEGIN
    DELETE FROM core.idea_duplicate;
    DROP TABLE IF EXISTS pg_temp.dup_edge, pg_temp.dup_label;

    -- 비교 키 = md5(짧은 고정 길이). 한글 원문을 정렬·조인 키로 쓰면 로케일 비교로 14만 건에 수십 초 걸린다
    CREATE TEMP TABLE dup_edge ON COMMIT DROP AS
    WITH body_group AS (
        SELECT id, min(id) OVER (PARTITION BY k) AS root
          FROM (SELECT id, md5(core.body_key(body)) AS k FROM core.idea
                 WHERE retired_at IS NULL AND length(core.body_key(body)) >= 50) b
    ),
    entry AS (
        SELECT i.id, i.source_id, i.year, md5(core.contest_key(c.name)) || md5(core.title_key(i.title)) AS k
          FROM core.idea i JOIN core.contest c ON c.id = i.contest_id
         WHERE i.retired_at IS NULL AND i.year IS NOT NULL
           AND core.contest_key(c.name) <> '' AND length(core.title_key(i.title)) >= 6
    )
    SELECT root AS a, id AS b, 'same_body' AS rule FROM body_group WHERE id <> root
    UNION ALL
    SELECT x.id, y.id, 'same_entry'
      FROM entry x JOIN entry y ON y.k = x.k AND y.id > x.id
     WHERE x.source_id <> y.source_id AND abs(x.year - y.year) <= 1;
    ANALYZE dup_edge;

    CREATE TEMP TABLE dup_label ON COMMIT DROP AS
    SELECT id, id AS label FROM (SELECT a AS id FROM dup_edge UNION SELECT b FROM dup_edge) n;
    ALTER TABLE dup_label ADD PRIMARY KEY (id);

    LOOP   -- 연결 요소: 이웃 중 가장 작은 label로 수렴할 때까지
        WITH m AS (
            SELECT e.x AS id, min(l.label) AS label
              FROM (SELECT a AS x, b AS y FROM dup_edge UNION ALL SELECT b, a FROM dup_edge) e
              JOIN dup_label l ON l.id = e.y
             GROUP BY e.x
        )
        UPDATE dup_label d SET label = m.label FROM m WHERE m.id = d.id AND m.label < d.label;
        GET DIAGNOSTICS changed = ROW_COUNT;
        EXIT WHEN changed = 0;
    END LOOP;

    WITH ranked AS (
        SELECT l.id, l.label,
               first_value(l.id) OVER (PARTITION BY l.label
                   ORDER BY s.public_ok DESC, length(core.body_key(i.body)) DESC, (nullif(i.award, '') IS NOT NULL) DESC,
                            i.year NULLS LAST, l.id) AS canonical_id
          FROM dup_label l JOIN core.idea i ON i.id = l.id JOIN core.source s ON s.id = i.source_id
    ),
    rules AS (
        SELECT id, array_agg(DISTINCT rule ORDER BY rule) AS rules
          FROM (SELECT a AS id, rule FROM dup_edge UNION ALL SELECT b, rule FROM dup_edge) e
         GROUP BY id
    ),
    ins AS (
        INSERT INTO core.idea_duplicate (idea_id, canonical_id, rules)
        SELECT r.id, r.canonical_id, rules.rules FROM ranked r JOIN rules USING (id) WHERE r.id <> r.canonical_id
        RETURNING 1
    )
    SELECT count(*) INTO changed FROM ins;
    RETURN changed;
END
$$;

CREATE OR REPLACE FUNCTION core.refresh_idea_exclusion() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE inserted integer;
BEGIN
    PERFORM core.refresh_idea_duplicate();
    DELETE FROM core.idea_exclusion WHERE decided_by = 'rule';
    WITH
    live AS (
        SELECT i.id, c.audience, s.record_kind, s.exclude_reason, md5(core.title_key(i.title)) AS title,
               length(core.body_key(i.body)) AS body_len
          FROM core.idea i
          JOIN core.contest c ON c.id = i.contest_id
          JOIN core.source s ON s.id = i.source_id
         WHERE i.retired_at IS NULL
    ),
    common_title AS (   -- 같은 아이디어의 여러 기록(idea_duplicate)은 1건으로 센다
        SELECT title FROM live LEFT JOIN core.idea_duplicate d ON d.idea_id = live.id
         GROUP BY title HAVING count(DISTINCT coalesce(d.canonical_id, live.id)) >= 3
    ),
    want AS (
        SELECT id, 'student_contest' AS reason FROM live WHERE audience = 'student'
        UNION ALL
        SELECT id, record_kind FROM live WHERE record_kind IN ('public_proposal', 'improvement_proposal')
        UNION ALL
        SELECT id, exclude_reason FROM live WHERE exclude_reason IS NOT NULL
        UNION ALL
        SELECT d.idea_id, 'duplicate_record' FROM core.idea_duplicate d JOIN live ON live.id = d.idea_id
        UNION ALL
        SELECT live.id, 'thin_record' FROM live JOIN common_title USING (title) WHERE live.body_len < 20
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

GRANT SELECT ON core.idea_duplicate TO bb_api;
