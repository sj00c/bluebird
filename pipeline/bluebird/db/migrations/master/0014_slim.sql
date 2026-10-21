-- 정제 DB 정리: master 하나로(docs/SLIM_PLAN.md). 행·값 유지. 표 8 + 뷰 5 → 표 3(raw·master·db_log)
DROP VIEW v_ideas, v_usable, v_excluded, v_flagged, v_reason_counts;

ALTER TABLE master RENAME TO master_old;
ALTER TABLE master_old RENAME CONSTRAINT master_pkey TO master_old_pkey;

CREATE TABLE master (
    api             text NOT NULL,
    key             text NOT NULL,
    title           text NOT NULL,
    body            text,
    kind            text NOT NULL,
    field           text NOT NULL,
    program         text NOT NULL,
    award           text,
    year            smallint,
    url             text,
    exclude_reasons text[] NOT NULL DEFAULT '{}',
    label           text,
    item_type       text,
    goal            text,
    solution        text,
    features        text[],
    domain          text[],
    evidence        text,
    verified        boolean,
    CONSTRAINT master_pkey PRIMARY KEY (api, key),
    CONSTRAINT master_raw FOREIGN KEY (api, key) REFERENCES raw (source, key) ON DELETE CASCADE,
    CONSTRAINT master_exclude_reasons CHECK (exclude_reasons <@ ARRAY['duplicate', 'no_body', 'attachment_only',
        'title_repeat', 'short_title_body', 'idea_thin', 'complaint', 'abusive', 'off_topic']),
    CONSTRAINT master_label CHECK (label IN ('idea', 'idea_thin', 'complaint', 'abusive', 'off_topic')),
    CONSTRAINT master_item_type CHECK (item_type IN ('product', 'research', 'policy')),
    CONSTRAINT master_domain CHECK (domain <@ ARRAY['행정', '복지', '교통', '환경', '경제', '교육', '안전', '문화', '보건',
        '과학기술', '생활', '기타'] AND cardinality(domain) > 0),
    -- AI 가공 칸 = 판정 idea인 행에만, 함께 채움
    CONSTRAINT master_ai CHECK (CASE WHEN label = 'idea'
        THEN item_type IS NOT NULL AND features IS NOT NULL AND domain IS NOT NULL AND verified IS NOT NULL
        ELSE item_type IS NULL AND goal IS NULL AND solution IS NULL AND features IS NULL AND domain IS NULL
             AND evidence IS NULL AND verified IS NULL END)
);

INSERT INTO master
SELECT m.api, m.key, m.title, m.body, p.kind, p.field, p.name, m.award, m.year, m.url, m.exclude_reasons,
       q.idea_label, f.item_type, f.goal, f.solution, f.features, f.domain, f.evidence, f.verified
  FROM master_old m
  JOIN program p ON p.id = m.program_id
  LEFT JOIN quality q USING (api, key)
  LEFT JOIN idea_fields f USING (api, key);

DO $$ BEGIN
    IF (SELECT count(*) FROM master) <> (SELECT count(*) FROM master_old) THEN
        RAISE EXCEPTION '0014: 행 수 불일치(대회·제도 없는 행 = master classify 먼저)';
    END IF;
END $$;

DROP TABLE idea_fields, quality, egress_call, master_old, program, exclusion_reason;

COMMENT ON TABLE master IS '[정제] 최종 표. 1행 = 아이디어 1건. 행 삭제 없음, 쓸 행 = exclude_reasons = ''{}'' AND verified. 만든 곳: bluebird master refine(refine.py·programs.py) → reasons(dedup.py·quality.py) → extract(extract.py) → reasons';
COMMENT ON COLUMN master.api IS '[원본] 수집 소스 id(= raw.source)';
COMMENT ON COLUMN master.key IS '[원본] 레코드 키(= raw.key). api + key = 행 고유값';
COMMENT ON COLUMN master.title IS '[정제] 제목. 글머리·접수번호·깨진 기호 정리, 연락처·지정 성명 가림. 만든 곳: bluebird master refine(refine.py)';
COMMENT ON COLUMN master.body IS '[정제] 본문. 원본 본문 칸(+상세 페이지 본문) 연결, 섹션 라벨 [..] 유지, HTML·깨진 기호 정리, 전화·이메일·성명 가림. 본문 = 제목이면 NULL. 만든 곳: bluebird master refine(refine.py)';
COMMENT ON COLUMN master.kind IS '[계산] 종류: 공모전 · 시민 제안 · 직원 제안(레지스트리 record_kind). 만든 곳: bluebird master refine(programs.py)';
COMMENT ON COLUMN master.field IS '[계산] 분야(과학·발명, 주민참여예산 등). 소스 단위 규칙. 만든 곳: bluebird master refine(programs.PROGRAM)';
COMMENT ON COLUMN master.program IS '[계산] 대회·제도명. 소스 단위, 과학·발명 4개 소스 = 원본 행 대회명(회차·연도 제거). 만든 곳: bluebird master refine(programs.py)';
COMMENT ON COLUMN master.award IS '[원본] 수상 등급. 원본 수상 칸 값 그대로(표기 통일 안 함). 만든 곳: bluebird master refine(refine.AWARD)';
COMMENT ON COLUMN master.year IS '[원본] 제안·출품·수상 연도(수집 시점 아님). 원본 연도 칸 앞 4자리·두 자리 연도·회차 환산. 만든 곳: refine';
COMMENT ON COLUMN master.url IS '[원본] 원문 링크. 행 상세 URL, 없으면 데이터셋 출처 URL. 만든 곳: refine';
COMMENT ON COLUMN master.exclude_reasons IS '[계산] 제외 사유 코드. 빈 배열 = 쓸 행. 만든 곳: bluebird master reasons(dedup.py·quality.py). 코드 뜻 —
duplicate = 중복(대표 아닌 행). 같은 글: 제목+본문 완전 일치(공백 무시, 대구 참여예산 제외) → 먼저 낸 것을 남김 / 같은 장소: 제목+지번 일치(대구) → 나중 것을 남김 / 같은 출품작: 공모전 행 중 대회·제도명+제목(6자 이상)+수상 등급 일치, 연도 차 1 이내, 출처 다름 → 본문 긴 것을 남김
no_body = 본문 내용 0자(비었거나 섹션 라벨·공백·기호뿐)
attachment_only = 본문에서 섹션 라벨·첨부/별첨/붙임 참조 문구를 빼면 0자
title_repeat = 본문에서 제목을 빼면 0자
short_title_body = 제목 내용 5자 이하이고 본문 내용 10자 이하
idea_thin · complaint · abusive · off_topic = AI 판정(label) 그대로: 빈약 · 불만·항의뿐 · 욕설·비방 중심 · 광고·무의미
(내용 글자 수 = 섹션 라벨 [..]·공백·기호 뺀 글자 수)';
COMMENT ON COLUMN master.label IS '[AI판정] idea(목표·방법 있음) · idea_thin(빈약) · complaint(불만뿐) · abusive(욕설 중심) · off_topic(광고·무의미). idea 아니면 그 값이 제외 사유. NULL = 판정 전(제외된 행은 판정 안 함). 만든 곳: bluebird master extract(extract.py)';
COMMENT ON COLUMN master.item_type IS '[LLM] 유형: product(발명·제품·디자인·서비스) · research(탐구) · policy(정책·시민 제안). label = idea인 행만. 만든 곳: extract';
COMMENT ON COLUMN master.goal IS '[LLM] 목표 한 문장. product·policy = 해결하려는 문제, research = 알아내려는 것. 만든 곳: extract';
COMMENT ON COLUMN master.solution IS '[LLM] 해결책 한 문장. product·policy = 만든 것·방법, research = 탐구 방법과 알아낸 결과. 만든 곳: extract';
COMMENT ON COLUMN master.features IS '[LLM] 핵심 기능 0~3개. research는 만든 장치·앱이 있을 때만. 만든 곳: extract';
COMMENT ON COLUMN master.domain IS '[LLM] 분야 1~2개: 행정·복지·교통·환경·경제·교육·안전·문화·보건·과학기술·생활(생활용품·가사·위생)·기타. 만든 곳: extract';
COMMENT ON COLUMN master.evidence IS '[LLM] 해결책 근거 원문 구절(제목·본문에서 그대로 복사). 만든 곳: extract';
COMMENT ON COLUMN master.verified IS '[계산] evidence가 제목·본문에 실제로 있음(공백 무시). 거짓 = 지어낸 값 의심. 만든 곳: extract';
