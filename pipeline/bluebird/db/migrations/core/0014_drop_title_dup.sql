-- 제목만 같다고 중복 표시하던 규칙 폐지(2026-10-13). 같은 제목·다른 내용(참여예산 "가로등 설치" 등)이 44% 섞여 쓸 수 없음.
-- idea_dup·duplicate_title·norm_title 제거. 중복 판단은 본문 기준으로 다시 설계할 때까지 없음.

CREATE OR REPLACE FUNCTION core.refresh_idea_exclusion() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE inserted integer;
BEGIN
    DELETE FROM core.idea_exclusion WHERE decided_by = 'rule';
    WITH
    live AS (
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

DELETE FROM core.idea_exclusion WHERE reason = 'duplicate_title';
DELETE FROM core.exclusion_reason WHERE code = 'duplicate_title';
DROP FUNCTION core.refresh_idea_dup();
DROP TABLE core.idea_dup;
ALTER TABLE core.idea DROP COLUMN norm_title;
