-- 전처리 사유 no_body: 정제 후 본문 빈 행(원본·상세 페이지 모두 본문 없음). 계산 = bluebird master reasons
ALTER TABLE master DROP CONSTRAINT master_exclude_reasons;
ALTER TABLE master ADD CONSTRAINT master_exclude_reasons CHECK (exclude_reasons <@ ARRAY['duplicate', 'no_body']);
INSERT INTO exclusion_reason VALUES
    ('no_body', '본문 없음', '정제 후 body 빈 값. 원본 파일·API와 원본 사이트 상세 페이지 모두 본문 없음(제목만 있음)');
