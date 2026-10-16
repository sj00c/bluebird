-- 수상 등급: 원본 행의 수상 필드 값 그대로(refine.AWARD 매핑). 수상 필드 없는 소스 = NULL. 채움 = refine 재실행.
ALTER TABLE master ADD COLUMN award text;
COMMENT ON COLUMN master.award IS '수상 등급(원본 값 그대로). 예: 대상, 금상, 장려상, 입선';
