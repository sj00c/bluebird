-- 콘솔(2인 독립 코딩·승인)과 이의 왕복(G11).

-- 이의 수용으로 원본까지 공개를 멈춘 아이디어(개인정보 등). publish는 이 행을 내보내지 않는다.
ALTER TABLE core.idea ADD COLUMN withheld_at timestamptz;
ALTER TABLE core.idea ADD COLUMN withheld_reason text;

-- 이의 처리 기록(누가). pull 검증에서 버린 건은 core.pipeline_run 통계로만 남긴다(본문 저장 안 함).
ALTER TABLE core.objection ADD COLUMN resolved_by text;
ALTER TABLE core.objection ADD COLUMN withheld boolean NOT NULL DEFAULT false;
ALTER TABLE core.objection ADD CONSTRAINT objection_resolved CHECK (
    (status = 'open' AND resolved_at IS NULL) OR (status <> 'open' AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL
                                                    AND coalesce(resolution, '') <> ''));

-- κ 표본: 표본 id + 아이디어. 두 코더가 같은 표본을 서로 모르게 코딩한다(review.round coder_a/coder_b).
CREATE TABLE core.coding_sample (
    sample_id  text NOT NULL,
    idea_id    text NOT NULL REFERENCES core.idea(id),
    stratum    text NOT NULL,
    seed       integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sample_id, idea_id)
);

-- 같은 아이템의 같은 슬롯은 한 번만, 같은 사람이 두 슬롯을 차지하지 않는다.
CREATE UNIQUE INDEX review_coder_slot ON core.review (target_id, round)
    WHERE target_type = 'idea' AND round IN ('coder_a', 'coder_b');
CREATE FUNCTION core.check_coder() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.round IN ('coder_a', 'coder_b') AND EXISTS (
        SELECT 1 FROM core.review r WHERE r.target_type = NEW.target_type AND r.target_id = NEW.target_id
           AND r.round IN ('coder_a', 'coder_b') AND r.round <> NEW.round AND r.reviewer = NEW.reviewer) THEN
        RAISE EXCEPTION 'reviewer % already holds the other coder slot for %', NEW.reviewer, NEW.target_id;
    END IF;
    IF NEW.round IN ('coder_a', 'coder_b') AND (NEW.decision <> 'code' OR NEW.code IS NULL) THEN
        RAISE EXCEPTION 'coder rounds record decision=code with a code';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER review_coder_check BEFORE INSERT OR UPDATE ON core.review FOR EACH ROW
    EXECUTE FUNCTION core.check_coder();
