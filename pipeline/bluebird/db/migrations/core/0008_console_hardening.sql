-- G004 리뷰 반영(콘솔·이의):
-- 1) 원본까지 공개 중단(withheld)한 아이디어는 깔때기·큐·weekly_top에서 빠진다(funnel_stage base).
-- 2) DMZ 이의 중복 판정은 DMZ가 만든 uuid로(공개용 DB를 다시 만들어 id가 겹쳐도 새 이의를 잃지 않는다).
-- 3) 코더 슬롯: 같은 사람은 한 아이디어에 한 슬롯(동시 요청에도 유일 인덱스로 막는다).
-- 4) backend-api 전용 최소 권한 역할 bb_api(로그인 비밀번호는 배포에서 설정).

ALTER TABLE core.objection ADD COLUMN dmz_uid uuid UNIQUE;
ALTER TABLE core.objection DROP CONSTRAINT objection_dmz_id_key;

CREATE UNIQUE INDEX review_coder_person ON core.review (target_id, reviewer)
    WHERE target_type = 'idea' AND round IN ('coder_a', 'coder_b');

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

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bb_api') THEN
        CREATE ROLE bb_api NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$;
GRANT USAGE ON SCHEMA core TO bb_api;
GRANT SELECT ON ALL TABLES IN SCHEMA core TO bb_api;
REVOKE SELECT ON core.egress_call, core.export_policy FROM bb_api;
GRANT INSERT ON core.review TO bb_api;
GRANT UPDATE (code, note, created_at) ON core.review TO bb_api;   -- 코더 자기 코드 수정
GRANT UPDATE (seed) ON core.coding_sample TO bb_api;              -- 슬롯 배정 잠금(FOR UPDATE)용
GRANT INSERT, UPDATE ON core.publication TO bb_api;
GRANT UPDATE (status) ON core.change_match TO bb_api;
GRANT DELETE ON core.weekly_top TO bb_api;
GRANT UPDATE (status, resolution, resolved_at, resolved_by, withheld) ON core.objection TO bb_api;
GRANT UPDATE (withheld_at, withheld_reason) ON core.idea TO bb_api;
GRANT USAGE ON SEQUENCE core.review_id_seq TO bb_api;
