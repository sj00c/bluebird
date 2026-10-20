-- 행 품질: master 1행 = quality 1행. 측정값 = bluebird master reasons가 매번 전체 재계산, idea_* = AI 판정(재계산 때 유지).
-- 규칙 = pipeline/bluebird/quality.py. 걸린 확실한 조건·AI 판정 → master.exclude_reasons 사유 코드.
CREATE TABLE quality (
    api             text NOT NULL,
    key             text NOT NULL,
    title_len       integer NOT NULL,   -- 제목 내용 글자 수(공백·기호 제외)
    body_len        integer NOT NULL,   -- 본문 내용 글자 수(섹션 라벨 [..]·공백·기호 제외)
    hangul_ratio    real,               -- 본문 내용 중 한글 비율. 본문 없음 = NULL
    attachment_only boolean NOT NULL,   -- 본문 = 첨부·별첨·붙임 참조 문구뿐
    title_repeat    boolean NOT NULL,   -- 본문 = 제목 반복뿐
    has_profanity   boolean NOT NULL,   -- 욕설 단어 있음(표시만, 제외 조건 아님)
    has_repeat      boolean NOT NULL,   -- ㅋㅋㅋㅋ·!!!! 같은 반복(표시만)
    idea_label      text CHECK (idea_label IN ('idea', 'idea_thin', 'complaint', 'abusive', 'off_topic')),
    idea_reason     text,               -- 판정 근거 한 줄
    idea_model      text,               -- 판정 모델
    idea_at         timestamptz,
    PRIMARY KEY (api, key),
    FOREIGN KEY (api, key) REFERENCES master (api, key) ON DELETE CASCADE
);
COMMENT ON TABLE quality IS '행 품질 측정값(매번 재계산) + AI 아이디어 판정(idea_*, 유지). 사유 = master.exclude_reasons';

ALTER TABLE master DROP CONSTRAINT master_exclude_reasons;
ALTER TABLE master ADD CONSTRAINT master_exclude_reasons CHECK (exclude_reasons <@ ARRAY[
    'duplicate', 'no_body', 'attachment_only', 'title_repeat', 'short_title_body',
    'idea_thin', 'complaint', 'abusive', 'off_topic']);
UPDATE exclusion_reason SET rule = '본문 내용 0자: 비었거나 섹션 라벨·공백·기호뿐(quality.body_len = 0)' WHERE code = 'no_body';
INSERT INTO exclusion_reason VALUES
    ('attachment_only', '첨부 참조뿐', '본문에서 섹션 라벨과 첨부·별첨·붙임 참조 문구를 빼면 내용 0자(quality.attachment_only)'),
    ('title_repeat', '제목 반복뿐', '본문에서 섹션 라벨·공백·기호와 제목을 빼면 내용 0자(quality.title_repeat)'),
    ('short_title_body', '제목·본문 모두 짧음', '제목 내용 5자 이하이고 본문 내용 10자 이하(quality.title_len·body_len)'),
    ('idea_thin', '아이디어 빈약(AI)', 'AI 판정: 아이디어는 있으나 목표·방법을 뽑기에 너무 짧음(quality.idea_label)'),
    ('complaint', '불만·항의뿐(AI)', 'AI 판정: 제안 없이 불만·항의만(quality.idea_label)'),
    ('abusive', '욕설·비방 중심(AI)', 'AI 판정: 욕설·비방이 중심(quality.idea_label)'),
    ('off_topic', '광고·무의미(AI)', 'AI 판정: 광고·홍보·의미 없는 글(quality.idea_label)');
