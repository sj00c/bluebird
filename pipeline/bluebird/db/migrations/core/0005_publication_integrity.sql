-- 승인 뒤 내용이 바뀌면 공개를 철회한다(검토한 내용만 공개). 반려·원인 변경도 같은 길로 정리한다.
-- s6은 "DMZ에 실제로 반영된 스냅샷에 이 아이디어가 들어 있음"으로 판정한다.

-- 누가 정했나(사람 입력 감사)
ALTER TABLE core.diagnosis ADD COLUMN decided_by text;
ALTER TABLE core.timeliness ADD COLUMN scored_by text;
ALTER TABLE core.timeliness ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();

-- 바뀐 것 확인 결과: api_verified(공식 API로 번호·시행일 대조) · fetched(화이트리스트 URL 200) · attested(사람 진술)
ALTER TABLE core.condition_change ADD COLUMN verify_status text
    CHECK (verify_status IN ('api_verified', 'fetched', 'attested'));
ALTER TABLE core.condition_change ADD COLUMN verify_detail jsonb;
ALTER TABLE core.condition_change ADD COLUMN egress_call_id bigint REFERENCES core.egress_call(id);
UPDATE core.condition_change SET verify_status = 'attested' WHERE origin = 'human';
-- 법령 시행은 국가법령정보 API로 번호·시행일을 대조한 것만 쓴다.
ALTER TABLE core.condition_change ADD CONSTRAINT condition_change_human_verified CHECK (
    origin <> 'human' OR verify_status IS NOT NULL);

-- 반영 완료 기록: DMZ 커밋 뒤에 applied_at, 공개된 아이디어(진단까지 나간 것) 목록
ALTER TABLE core.publish_snapshot ADD COLUMN applied_at timestamptz;
ALTER TABLE core.publish_snapshot ADD COLUMN revived_ids text[] NOT NULL DEFAULT '{}';

-- ------------------------------------------------------------------ 공개 철회
CREATE FUNCTION core.revoke_idea(p_idea text) RETURNS void LANGUAGE sql AS $$
    UPDATE core.publication SET revoked_at = now()
     WHERE revoked_at IS NULL
       AND ((target_type = 'idea' AND target_id = p_idea)
            OR (target_type = 'change_match'
                AND target_id IN (SELECT id::text FROM core.change_match WHERE idea_id = p_idea)));
    UPDATE core.change_match SET status = 'candidate' WHERE idea_id = p_idea AND status = 'approved';
    DELETE FROM core.weekly_top WHERE idea_id = p_idea;
$$;

CREATE FUNCTION core.revoke_on_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
    r := CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    IF TG_TABLE_NAME IN ('diagnosis', 'idea_card', 'timeliness') THEN
        PERFORM core.revoke_idea(r.idea_id);
    ELSIF TG_TABLE_NAME = 'change_match' THEN
        PERFORM core.revoke_idea(r.idea_id);
    ELSIF TG_TABLE_NAME = 'x_evidence' THEN
        IF r.target_type = 'diagnosis' THEN
            PERFORM core.revoke_idea(r.target_id);
        ELSIF r.target_type = 'timeliness' THEN
            PERFORM core.revoke_idea(split_part(r.target_id, '@', 1));
        ELSIF r.target_type = 'change_match' THEN
            PERFORM core.revoke_idea(m.idea_id) FROM core.change_match m WHERE m.id::text = r.target_id;
        END IF;
    ELSIF TG_TABLE_NAME = 'condition_change' THEN
        PERFORM core.revoke_idea(m.idea_id) FROM core.change_match m WHERE m.change_id = r.id;
    END IF;
    RETURN NULL;
END $$;

CREATE TRIGGER diagnosis_revoke AFTER UPDATE ON core.diagnosis FOR EACH ROW
    WHEN (OLD."primary" IS DISTINCT FROM NEW."primary" OR OLD.secondary IS DISTINCT FROM NEW.secondary
          OR OLD.rationale IS DISTINCT FROM NEW.rationale)
    EXECUTE FUNCTION core.revoke_on_change();
CREATE TRIGGER diagnosis_revoke_del AFTER DELETE ON core.diagnosis FOR EACH ROW
    EXECUTE FUNCTION core.revoke_on_change();
CREATE TRIGGER card_revoke AFTER UPDATE ON core.idea_card FOR EACH ROW
    WHEN (OLD.problem IS DISTINCT FROM NEW.problem OR OLD.solution IS DISTINCT FROM NEW.solution
          OR OLD.missing_data IS DISTINCT FROM NEW.missing_data OR OLD.card_kind IS DISTINCT FROM NEW.card_kind)
    EXECUTE FUNCTION core.revoke_on_change();
CREATE TRIGGER timeliness_revoke AFTER INSERT OR DELETE ON core.timeliness FOR EACH ROW
    EXECUTE FUNCTION core.revoke_on_change();
CREATE TRIGGER timeliness_revoke_upd AFTER UPDATE ON core.timeliness FOR EACH ROW
    WHEN (ROW(OLD.tech, OLD.data, OLD.regulation, OLD.policy, OLD.s, OLD.verdict, OLD.resolve_condition)
          IS DISTINCT FROM ROW(NEW.tech, NEW.data, NEW.regulation, NEW.policy, NEW.s, NEW.verdict,
                                NEW.resolve_condition))
    EXECUTE FUNCTION core.revoke_on_change();
CREATE TRIGGER match_revoke AFTER UPDATE ON core.change_match FOR EACH ROW
    WHEN (ROW(OLD.change_id, OLD.llm_verdict, OLD.what_changed, OLD.how_now)
          IS DISTINCT FROM ROW(NEW.change_id, NEW.llm_verdict, NEW.what_changed, NEW.how_now)
          OR (OLD.status = 'approved' AND NEW.status = 'rejected'))
    EXECUTE FUNCTION core.revoke_on_change();
CREATE TRIGGER match_revoke_del AFTER DELETE ON core.change_match FOR EACH ROW
    EXECUTE FUNCTION core.revoke_on_change();
CREATE TRIGGER x_evidence_revoke AFTER INSERT OR DELETE ON core.x_evidence FOR EACH ROW
    EXECUTE FUNCTION core.revoke_on_change();
CREATE TRIGGER change_revoke AFTER UPDATE ON core.condition_change FOR EACH ROW
    WHEN (ROW(OLD.url, OLD.title, OLD.occurred_at, OLD.summary, OLD.kind)
          IS DISTINCT FROM ROW(NEW.url, NEW.title, NEW.occurred_at, NEW.summary, NEW.kind))
    EXECUTE FUNCTION core.revoke_on_change();

-- 원인이 바뀌면 원인과 맞지 않는 매칭은 후보에서도 뺀다(공개 철회는 위 트리거가 한다).
CREATE FUNCTION core.drop_misfit_matches() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE core.change_match m SET status = 'rejected'
      FROM core.condition_change c
     WHERE m.idea_id = NEW.idea_id AND c.id = m.change_id AND m.status <> 'rejected'
       AND NOT EXISTS (SELECT 1 FROM core.cause_change_kind k WHERE k.cause = NEW."primary" AND k.kind = c.kind);
    RETURN NULL;
END $$;
CREATE TRIGGER diagnosis_misfit AFTER UPDATE OF "primary" ON core.diagnosis FOR EACH ROW
    WHEN (OLD."primary" IS DISTINCT FROM NEW."primary") EXECUTE FUNCTION core.drop_misfit_matches();

-- ------------------------------------------------------------------ 단계 판정(다시 정의)
-- as_of_snapshot은 "그 스냅샷 시점에 알 수 있던 신호"만 거른다: 그 뒤 스냅샷에서 처음 관측된 데이터셋, 다음 스냅샷
-- 날짜(최신이면 오늘) 이후에 일어난 바뀐 것, 그 뒤 날짜의 S. 진단·검토·공개는 현재 상태다(재현용 이력 아님).
-- 법령 시행은 api_verified만, 그 밖의 사람 입력은 확인 상태가 있어야 한다. 미래 시행일은 통과하지 않는다.
CREATE OR REPLACE FUNCTION core.funnel_stage(as_of_snapshot integer)
RETURNS TABLE (idea_id text, source_id text, public_ok boolean, card_kind text, profile_version text,
               trace_status text, cause char(1), s0 boolean, s1 boolean, s2 boolean, s3 boolean, s4 boolean,
               s5 boolean, s6 boolean)
LANGUAGE sql STABLE AS $$
WITH snap AS (SELECT LEAST(coalesce((SELECT min(taken_at) FROM core.catalog_snapshot WHERE id > as_of_snapshot),
                                    'infinity'::date),
                           (now() AT TIME ZONE 'Asia/Seoul')::date + 1) AS cutoff),
base AS (
    SELECT i.id, i.source_id, s.public_ok, k.card_kind, t.profile_version, t.status AS trace_status,
           d."primary" AS cause,
           k.idea_id IS NOT NULL AS s0,
           coalesce(t.status IN ('none', 'award_only'), false) AS s1,
           coalesce(d."primary" <> 'U'
               AND EXISTS (SELECT 1 FROM core.x_evidence x WHERE x.target_type = 'diagnosis' AND x.target_id = i.id)
               AND (d."primary" <> 'D' OR jsonb_array_length(k.missing_data) > 0), false) AS s2
      FROM core.idea i
      JOIN core.source s ON s.id = i.source_id
      LEFT JOIN core.idea_card k ON k.idea_id = i.id
      LEFT JOIN core.trace_verdict t ON t.idea_id = i.id
      LEFT JOIN core.diagnosis d ON d.idea_id = i.id
     WHERE i.retired_at IS NULL
),
m AS (
    SELECT DISTINCT ON (cm.idea_id) cm.idea_id, cm.id, c.kind
      FROM core.change_match cm
      JOIN core.condition_change c ON c.id = cm.change_id
      JOIN core.diagnosis d ON d.idea_id = cm.idea_id
      JOIN core.cause_change_kind ck ON ck.cause = d."primary" AND ck.kind = c.kind
      LEFT JOIN core.signal_dataset sd ON c.kind = 'dataset_opened' AND sd.public_data_pk = c.ref_id
     WHERE cm.llm_verdict IN ('yes', 'partial', 'human') AND cm.status <> 'rejected'
       AND (sd.public_data_pk IS NULL OR sd.first_seen_snapshot_id <= as_of_snapshot)
       AND (c.kind = 'dataset_opened' OR c.occurred_at < (SELECT cutoff FROM snap))
       AND (c.kind <> 'law_effective' OR c.verify_status = 'api_verified')
       AND (c.origin <> 'human' OR c.verify_status IS NOT NULL)
     ORDER BY cm.idea_id, (cm.status = 'approved') DESC, cm.id
),
ts AS (
    SELECT DISTINCT ON (t.idea_id) t.idea_id, t.verdict
      FROM core.timeliness t WHERE t.as_of < (SELECT cutoff FROM snap)
     ORDER BY t.idea_id, t.as_of DESC
),
approved AS (
    SELECT b.id,
           EXISTS (SELECT 1 FROM core.review r WHERE r.target_type = 'idea' AND r.target_id = b.id
                     AND r.round = 'final' AND r.decision = 'approve')
           AND (SELECT count(DISTINCT p.scope) FROM core.publication p
                 WHERE p.target_type = 'idea' AND p.target_id = b.id AND p.revoked_at IS NULL
                   AND p.scope IN ('card', 'diagnosis', 'timeliness')) = 3
           AND EXISTS (SELECT 1 FROM core.change_match cm
                         JOIN core.condition_change c ON c.id = cm.change_id
                         JOIN core.diagnosis d ON d.idea_id = cm.idea_id
                         JOIN core.cause_change_kind ck ON ck.cause = d."primary" AND ck.kind = c.kind
                         JOIN core.publication p ON p.target_type = 'change_match' AND p.target_id = cm.id::text
                                                AND p.scope = 'change' AND p.revoked_at IS NULL
                        WHERE cm.idea_id = b.id AND cm.status = 'approved') AS ok,
           (SELECT max(p.approved_at) FROM core.publication p
             WHERE p.target_type = 'idea' AND p.target_id = b.id AND p.revoked_at IS NULL) AS approved_at
      FROM base b
),
applied AS (
    SELECT created_at, revived_ids FROM core.publish_snapshot WHERE applied_at IS NOT NULL
     ORDER BY id DESC LIMIT 1
)
SELECT b.id, b.source_id, b.public_ok, b.card_kind, b.profile_version, b.trace_status, b.cause,
       b.s0,
       b.s0 AND b.s1,
       b.s0 AND b.s1 AND b.s2,
       b.s0 AND b.s1 AND b.s2 AND m.idea_id IS NOT NULL,
       b.s0 AND b.s1 AND b.s2 AND m.idea_id IS NOT NULL AND coalesce(ts.verdict IN ('now', 'conditional'), false),
       b.s0 AND b.s1 AND b.s2 AND m.idea_id IS NOT NULL AND coalesce(ts.verdict IN ('now', 'conditional'), false)
           AND a.ok,
       b.s0 AND b.s1 AND b.s2 AND m.idea_id IS NOT NULL AND coalesce(ts.verdict IN ('now', 'conditional'), false)
           AND a.ok AND b.public_ok
           AND EXISTS (SELECT 1 FROM applied ap WHERE ap.created_at > a.approved_at AND b.id = ANY(ap.revived_ids))
  FROM base b
  LEFT JOIN m ON m.idea_id = b.id
  LEFT JOIN ts ON ts.idea_id = b.id
  JOIN approved a ON a.id = b.id
$$;
