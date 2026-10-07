-- 되살리기 깔때기(계획 §3.3). core.funnel_stage(as_of)가 단계 규칙을 SQL 하나로 구현하고,
-- core.revival_candidate는 최신 스냅샷 기준 뷰다. `bluebird funnel --as-of`도 같은 함수를 쓴다.

-- 바뀐 것이 어떻게 들어왔나: 카탈로그 diff(signal) · K-Startup API(api) · 사람이 근거 URL로 입력(human)
ALTER TABLE core.condition_change ADD COLUMN origin text NOT NULL DEFAULT 'signal'
    CHECK (origin IN ('signal', 'api', 'human'));
ALTER TABLE core.condition_change ADD COLUMN added_by text;
ALTER TABLE core.condition_change ADD COLUMN summary text;
-- 자동 신호는 카탈로그(D)와 공고(C)만. 법령·정책·기술은 사람이 근거 URL로만 넣는다(§3.4).
ALTER TABLE core.condition_change ADD CONSTRAINT condition_change_origin_kind CHECK (
    (kind = 'dataset_opened' AND origin = 'signal')
    OR (kind = 'announcement' AND origin IN ('api', 'human'))
    OR (kind IN ('law_effective', 'policy_news', 'tech') AND origin = 'human'));

-- 바뀐 것 매칭은 원인과 종류가 맞을 때만 생긴다(종류 불일치 매칭은 만들지 않는다).
CREATE FUNCTION core.check_change_match() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE k text; idea_cause char(1);
BEGIN
    SELECT kind INTO k FROM core.condition_change WHERE id = NEW.change_id;
    SELECT "primary" INTO idea_cause FROM core.diagnosis WHERE idea_id = NEW.idea_id;
    IF idea_cause IS NULL OR NOT EXISTS (SELECT 1 FROM core.cause_change_kind c WHERE c.cause = idea_cause AND c.kind = k) THEN
        RAISE EXCEPTION 'change_match kind % does not fit diagnosis % (idea %)', k, coalesce(idea_cause, '-'), NEW.idea_id;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER change_match_kind_check BEFORE INSERT OR UPDATE OF change_id, idea_id ON core.change_match
    FOR EACH ROW EXECUTE FUNCTION core.check_change_match();

-- 단계별 통과 여부. as_of_snapshot 기준: 그 뒤 스냅샷에서 처음 관측된 데이터셋, 다음 스냅샷 날짜 이후의
-- 사람 입력(바뀐 것·S)은 넣지 않는다. 최신 스냅샷이면 지금까지 전부.
CREATE FUNCTION core.funnel_stage(as_of_snapshot integer)
RETURNS TABLE (idea_id text, source_id text, public_ok boolean, card_kind text, profile_version text,
               trace_status text, cause char(1), s0 boolean, s1 boolean, s2 boolean, s3 boolean, s4 boolean,
               s5 boolean, s6 boolean)
LANGUAGE sql STABLE AS $$
WITH snap AS (SELECT coalesce((SELECT min(taken_at) FROM core.catalog_snapshot WHERE id > as_of_snapshot),
                              'infinity'::date) AS cutoff),
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
           AND EXISTS (SELECT 1 FROM core.change_match cm JOIN core.publication p
                         ON p.target_type = 'change_match' AND p.target_id = cm.id::text AND p.scope = 'change'
                        AND p.revoked_at IS NULL
                        WHERE cm.idea_id = b.id AND cm.status = 'approved') AS ok,
           (SELECT max(p.approved_at) FROM core.publication p
             WHERE p.target_type = 'idea' AND p.target_id = b.id AND p.revoked_at IS NULL) AS approved_at
      FROM base b
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
           AND EXISTS (SELECT 1 FROM core.publish_snapshot ps WHERE ps.created_at > a.approved_at)
  FROM base b
  LEFT JOIN m ON m.idea_id = b.id
  LEFT JOIN ts ON ts.idea_id = b.id
  JOIN approved a ON a.id = b.id
$$;

CREATE VIEW core.revival_candidate AS
SELECT * FROM core.funnel_stage((SELECT max(id) FROM core.catalog_snapshot));
