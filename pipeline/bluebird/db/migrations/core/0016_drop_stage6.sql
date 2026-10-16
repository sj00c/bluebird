-- 공개 DB(publish) 반영 제거: 6단계(공개 반영 = core.publish_snapshot 기록)를 깔때기에서 뺀다.
-- 반환 열이 바뀌므로 뷰·함수를 다시 만든다. 단계 규칙 s0–s5는 0008과 같다.

DROP VIEW core.revival_candidate;
DROP FUNCTION core.funnel_stage(integer);

CREATE FUNCTION core.funnel_stage(as_of_snapshot integer)
RETURNS TABLE (idea_id text, source_id text, public_ok boolean, card_kind text, profile_version text,
               trace_status text, cause char(1), s0 boolean, s1 boolean, s2 boolean, s3 boolean, s4 boolean,
               s5 boolean)
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
     WHERE i.retired_at IS NULL AND i.withheld_at IS NULL
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
                          AND core.match_eligible(cm.id, as_of_snapshot)) AS ok
      FROM base b
)
SELECT b.id, b.source_id, b.public_ok, b.card_kind, b.profile_version, b.trace_status, b.cause,
       b.s0,
       b.s0 AND b.s1,
       b.s0 AND b.s1 AND b.s2,
       b.s0 AND b.s1 AND b.s2 AND m.idea_id IS NOT NULL,
       b.s0 AND b.s1 AND b.s2 AND m.idea_id IS NOT NULL AND coalesce(ts.verdict IN ('now', 'conditional'), false),
       b.s0 AND b.s1 AND b.s2 AND m.idea_id IS NOT NULL AND coalesce(ts.verdict IN ('now', 'conditional'), false)
           AND a.ok
  FROM base b
  LEFT JOIN m ON m.idea_id = b.id
  LEFT JOIN ts ON ts.idea_id = b.id
  JOIN approved a ON a.id = b.id
$$;

CREATE VIEW core.revival_candidate AS
SELECT * FROM core.funnel_stage((SELECT max(id) FROM core.catalog_snapshot));

GRANT SELECT ON core.revival_candidate TO bb_api;
