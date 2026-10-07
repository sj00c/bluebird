-- 카드 무결성: full은 LLM(P1)이 본문을 받은 카드만, 그 호출의 감사 행과 연결. 본문 해시로 갱신 여부를 판단한다.
ALTER TABLE core.idea_card ADD COLUMN body_sha256 text;
ALTER TABLE core.idea_card ADD COLUMN egress_call_id bigint REFERENCES core.egress_call(id);
ALTER TABLE core.idea_card ADD CONSTRAINT idea_card_full_is_llm
    CHECK (card_kind <> 'full' OR (extractor = 'llm' AND egress_call_id IS NOT NULL));
