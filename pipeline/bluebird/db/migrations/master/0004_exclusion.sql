-- 전처리 사유: 행은 지우지 않고 표시만. 코드 뜻 = exclusion_reason. 계산 = bluebird master dedup(매번 전체 재계산).
-- 조회: 전처리 통과 = exclude_reasons = '{}', 중복만 제외 = NOT 'duplicate' = ANY(exclude_reasons).
CREATE TABLE exclusion_reason (
    code  text PRIMARY KEY,
    label text NOT NULL,
    rule  text NOT NULL
);
INSERT INTO exclusion_reason VALUES
    ('duplicate', '중복(대표 아닌 행)',
     'D1 제목+본문 완전 일치(공백 제거, 대구 참여예산 제외) → 먼저 낸 것이 대표. '
     'D2 제목+지번 완전 일치 → 나중 것이 대표. '
     'D3 대회명+제목(6자 이상) 일치·연도 차 1 이내·소스 다름 → 본문 긴 것이 대표. '
     '제목만 같음 = 중복 아님');

ALTER TABLE master
    ADD COLUMN exclude_reasons text[] NOT NULL DEFAULT '{}',
    ADD COLUMN canonical_api text,
    ADD COLUMN canonical_key text,
    ADD CONSTRAINT master_exclude_reasons CHECK (exclude_reasons <@ ARRAY['duplicate']),
    ADD CONSTRAINT master_canonical_pair CHECK ((canonical_api IS NULL) = (canonical_key IS NULL)),
    ADD CONSTRAINT master_canonical_fkey FOREIGN KEY (canonical_api, canonical_key)
        REFERENCES master (api, key) ON DELETE SET NULL;
CREATE INDEX master_canonical_idx ON master (canonical_api, canonical_key);

COMMENT ON COLUMN master.exclude_reasons IS '전처리 사유 코드(exclusion_reason.code). 빈 배열 = 해당 없음';
COMMENT ON COLUMN master.canonical_api IS '중복일 때 대표 행 api';
COMMENT ON COLUMN master.canonical_key IS '중복일 때 대표 행 key';
