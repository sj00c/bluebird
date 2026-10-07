-- G005: external_search는 체계적 외부 검색(news_web·ip)을 실제로 돌렸을 때만 'done'이다(funnel.decide_trace).
-- 그 전에는 사람 manual 확인도 'done'으로 셌다. 이미 저장된 판정을 같은 규칙으로 바로잡는다.
UPDATE core.trace_verdict t
   SET external_search = 'not_done'
 WHERE t.external_search = 'done'
   AND NOT EXISTS (
         SELECT 1 FROM core.trace_check c
          WHERE c.idea_id = t.idea_id AND c.item IN ('news_web', 'ip') AND c.result IN ('found', 'none'));
