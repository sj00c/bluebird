-- 매칭 하나가 3단계(바뀐 것)를 채우는지: 한 곳에서 정의하고 단계 판정·승인·공개가 모두 이것만 쓴다.
-- 판정 yes/partial/human, 반려 아님, 원인과 종류가 맞음, 스냅샷 시점에 관측된 데이터셋, 기준일(다음 스냅샷·오늘) 전에
-- 일어난 바뀐 것, 법령 시행은 api_verified, 사람 입력은 확인 상태가 있음.
CREATE FUNCTION core.match_eligible(p_match bigint, as_of_snapshot integer) RETURNS boolean
LANGUAGE sql STABLE AS $$
SELECT EXISTS (
    SELECT 1
      FROM core.change_match cm
      JOIN core.condition_change c ON c.id = cm.change_id
      JOIN core.diagnosis d ON d.idea_id = cm.idea_id
      JOIN core.cause_change_kind ck ON ck.cause = d."primary" AND ck.kind = c.kind
      LEFT JOIN core.signal_dataset sd ON c.kind = 'dataset_opened' AND sd.public_data_pk = c.ref_id
     WHERE cm.id = p_match
       AND cm.llm_verdict IN ('yes', 'partial', 'human') AND cm.status <> 'rejected'
       AND (sd.public_data_pk IS NULL OR sd.first_seen_snapshot_id <= as_of_snapshot)
       AND (c.kind = 'dataset_opened'
            OR c.occurred_at < LEAST(coalesce((SELECT min(taken_at) FROM core.catalog_snapshot WHERE id > as_of_snapshot),
                                              'infinity'::date),
                                     (now() AT TIME ZONE 'Asia/Seoul')::date + 1))
       AND (c.kind <> 'law_effective' OR c.verify_status = 'api_verified')
       AND (c.origin <> 'human' OR c.verify_status IS NOT NULL))
$$;

-- 바뀐 것 원문이 바뀌면 그것을 쓴 승인 매칭만 철회(후보·반려 매칭의 아이디어는 건드리지 않는다). 공개되는 tier도 본다.
DROP TRIGGER change_revoke ON core.condition_change;
CREATE OR REPLACE FUNCTION core.revoke_on_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
    r := CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    IF TG_TABLE_NAME IN ('diagnosis', 'idea_card', 'timeliness', 'change_match') THEN
        PERFORM core.revoke_idea(r.idea_id);
    ELSIF TG_TABLE_NAME = 'x_evidence' THEN
        IF r.target_type = 'diagnosis' THEN
            PERFORM core.revoke_idea(r.target_id);
        ELSIF r.target_type = 'timeliness' THEN
            PERFORM core.revoke_idea(split_part(r.target_id, '@', 1));
        ELSIF r.target_type = 'change_match' THEN
            PERFORM core.revoke_idea(m.idea_id) FROM core.change_match m
             WHERE m.id::text = r.target_id AND m.status = 'approved';
        END IF;
    ELSIF TG_TABLE_NAME = 'condition_change' THEN
        PERFORM core.revoke_idea(m.idea_id) FROM core.change_match m WHERE m.change_id = r.id AND m.status = 'approved';
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER change_revoke AFTER UPDATE ON core.condition_change FOR EACH ROW
    WHEN (ROW(OLD.url, OLD.title, OLD.occurred_at, OLD.summary, OLD.kind, OLD.tier, OLD.verify_status)
          IS DISTINCT FROM ROW(NEW.url, NEW.title, NEW.occurred_at, NEW.summary, NEW.kind, NEW.tier, NEW.verify_status))
    EXECUTE FUNCTION core.revoke_on_change();

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
    SELECT DISTINCT cm.idea_id FROM core.change_match cm
     WHERE cm.status <> 'rejected' AND core.match_eligible(cm.id, as_of_snapshot)
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
                         JOIN core.publication p ON p.target_type = 'change_match' AND p.target_id = cm.id::text
                                                AND p.scope = 'change' AND p.revoked_at IS NULL
                        WHERE cm.idea_id = b.id AND cm.status = 'approved'
                          AND core.match_eligible(cm.id, as_of_snapshot)) AS ok,
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
