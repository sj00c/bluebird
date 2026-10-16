-- 대회·제도 분류. 계산 = bluebird master classify(매번 전체 재계산). 규칙 = pipeline/bluebird/programs.py
CREATE TABLE program (
    id    serial PRIMARY KEY,
    kind  text NOT NULL,   -- 종류: 공모전 · 시민 제안 · 직원 제안 · 미분류
    field text NOT NULL,   -- 분야: 과학·발명, 주민참여예산 등
    name  text NOT NULL,   -- 대회·제도 이름
    UNIQUE (kind, field, name)
);
ALTER TABLE master ADD COLUMN program_id int REFERENCES program (id) ON DELETE SET NULL;
CREATE INDEX master_program_idx ON master (program_id);
COMMENT ON COLUMN master.program_id IS '대회·제도(program.id)';
