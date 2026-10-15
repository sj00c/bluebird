-- contest 출처: O = 원본 행 값, X = LLM이 채움(본문·소스 정보). contest 없으면 NULL.
ALTER TABLE master ADD COLUMN origin char(1) CHECK (origin IN ('O', 'X'));
-- 이 시점 원본 contest는 refine 재실행이 O로 표시. 그 전 값 = 전부 LLM 후보(X)로 두고 refine이 원본을 O로 바꾼다.
UPDATE master SET origin = 'X' WHERE contest IS NOT NULL;
ALTER TABLE master ADD CONSTRAINT master_origin CHECK ((contest IS NULL) = (origin IS NULL));
COMMENT ON COLUMN master.origin IS 'contest 출처: O 원본, X LLM';
