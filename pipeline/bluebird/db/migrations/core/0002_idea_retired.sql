-- 원본 파일이 갱신돼 사라진 행은 지우지 않고 retired_at을 찍는다(공개·카드·깔때기에서 제외, 이력·근거는 유지).
ALTER TABLE core.idea ADD COLUMN retired_at timestamptz;
CREATE INDEX idea_live_idx ON core.idea (source_id) WHERE retired_at IS NULL;
