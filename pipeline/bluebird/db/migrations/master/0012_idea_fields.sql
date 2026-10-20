-- 가공된 아이디어(목표·해결책·핵심기능·도메인). LLM 1회 호출로 판정(quality.idea_label) + 추출. 규칙 = pipeline/bluebird/extract.py
-- 옛 LLM 칸(master.problem·feature·domain 등)은 그대로 둠(비교용)
CREATE TABLE idea_fields (
    api            text NOT NULL,
    key            text NOT NULL,
    item_type      text NOT NULL CHECK (item_type IN ('product', 'research', 'policy')),
    goal           text,
    solution       text,
    features       text[] NOT NULL DEFAULT '{}',
    domain         text[] NOT NULL CHECK (domain <@ ARRAY['행정','복지','교통','환경','경제','교육','안전','문화','보건',
                                                          '과학기술','생활','기타'] AND cardinality(domain) > 0),
    evidence       text,
    verified       boolean NOT NULL,
    model          text NOT NULL,
    prompt_version text NOT NULL,
    at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (api, key),
    FOREIGN KEY (api, key) REFERENCES master (api, key) ON DELETE CASCADE
);
COMMENT ON TABLE idea_fields IS '[LLM] 가공된 아이디어. quality.idea_label = idea인 행만. 만든 곳: bluebird master extract(extract.py)';
COMMENT ON COLUMN idea_fields.api IS '[LLM] master.api';
COMMENT ON COLUMN idea_fields.key IS '[LLM] master.key';
COMMENT ON COLUMN idea_fields.item_type IS '[LLM] 유형: product(발명·제품·디자인·서비스) · research(탐구) · policy(정책·시민 제안)';
COMMENT ON COLUMN idea_fields.goal IS '[LLM] 목표 한 문장. product·policy = 해결하려는 문제, research = 알아내려는 것';
COMMENT ON COLUMN idea_fields.solution IS '[LLM] 해결책 한 문장. product·policy = 만든 것·방법, research = 탐구 방법과 알아낸 결과';
COMMENT ON COLUMN idea_fields.features IS '[LLM] 핵심 기능 0~3개. research는 만든 장치·앱이 있을 때만';
COMMENT ON COLUMN idea_fields.domain IS '[LLM] 분야 1~2개: 행정·복지·교통·환경·경제·교육·안전·문화·보건·과학기술·생활(생활용품·가사·위생)·기타';
COMMENT ON COLUMN idea_fields.evidence IS '[LLM] 해결책 근거 원문 구절(제목·본문에서 그대로 복사)';
COMMENT ON COLUMN idea_fields.verified IS '[계산] evidence가 제목·본문에 실제로 있음(공백 무시). 거짓 = 지어낸 값 의심';
COMMENT ON COLUMN idea_fields.model IS '[LLM] 모델 이름';
COMMENT ON COLUMN idea_fields.prompt_version IS '[LLM] 지시문 버전(extract.PROMPT_VERSION)';
COMMENT ON COLUMN idea_fields.at IS '[LLM] 생성 시각';

CREATE VIEW v_ideas AS
SELECT m.api, m.key, m.title, p.kind, p.field, p.name AS program, m.award, m.year, m.url,
       f.item_type, f.goal, f.solution, f.features, f.domain
  FROM master m JOIN idea_fields f USING (api, key) LEFT JOIN program p ON p.id = m.program_id
 WHERE m.exclude_reasons = '{}' AND f.verified;
COMMENT ON VIEW v_ideas IS '[조회용 뷰] 최종 사용: 쓸 행 + AI 판정 idea + 근거 확인된 가공 아이디어(목표·해결책·기능·도메인). 데이터 아님';
