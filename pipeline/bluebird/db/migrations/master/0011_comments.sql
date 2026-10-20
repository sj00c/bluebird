-- 모든 표·칸·조회용 뷰에 출처 설명(COMMENT). DB만 열어도 원본/정제/LLM/계산/AI판정/기록 구분.
-- 형식: [출처] 설명. 만든 곳: 명령(규칙 파일)
--   [원본] 수집 값 그대로 · [정제] 원본을 규칙으로 정리 · [LLM] 생성형 AI가 만든 값 · [계산] 규칙으로 계산한 판정·측정
--   [AI판정] AI가 판정한 값 · [기록] 작업 이력 · [기준표] 사람이 정한 코드·규칙 · [조회용 뷰] 저장된 쿼리(데이터 아님)
-- 검사: tests/test_db_integration.py (설명 없는 표·칸·뷰 = 실패)

-- ---------------------------------------------------------------- raw
COMMENT ON TABLE raw IS '[원본] 수집한 그대로. 1행 = 원본 레코드 1건. source ''<소스>.detail'' = 원본 사이트 상세 페이지 본문. 만든 곳: bluebird master files·api·detail(master.py·budget_detail.py)';
COMMENT ON COLUMN raw.source IS '[원본] 수집 소스 id(deploy/local/*-sources.toml). 끝이 .detail = 상세 페이지 본문';
COMMENT ON COLUMN raw.key IS '[원본] 소스 안 레코드 키(API 고유번호, 없으면 행 번호·내용 해시)';
COMMENT ON COLUMN raw.payload IS '[원본] 받은 레코드 전체(원본 헤더 → 값). .detail = {url, body, match}';
COMMENT ON COLUMN raw.fetched IS '[원본] 우리가 받은 시각';

-- ---------------------------------------------------------------- master
COMMENT ON TABLE master IS '[정제] 정제본. 1행 = 아이디어 1건. 칸마다 출처 다름(원본·정제·LLM·계산) → 칸 설명 참고. 쓸 행 = exclude_reasons = ''{}'' (뷰 v_usable). 만든 곳: bluebird master refine(refine.py) → fill(fill.py) → reasons(dedup.py·quality.py) → classify(programs.py)';
COMMENT ON COLUMN master.api IS '[원본] 수집 소스 id(= raw.source)';
COMMENT ON COLUMN master.key IS '[원본] 레코드 키(= raw.key). api + key = 행 고유값';
COMMENT ON COLUMN master.title IS '[정제] 제목. 원본 제목에서 글머리·접수번호·깨진 기호 정리, 연락처·지정 성명 가림. 만든 곳: bluebird master refine(refine.py)';
COMMENT ON COLUMN master.body IS '[정제] 본문. 원본 본문 칸(+상세 페이지 본문) 연결, 섹션 라벨 [..] 유지, HTML·깨진 기호 정리, 전화·이메일·성명 가림. 본문 = 제목이면 NULL. 만든 곳: bluebird master refine(refine.py)';
COMMENT ON COLUMN master.contest IS '[원본 또는 LLM] 공모전·대회·제도명. origin = O 원본 행 값, X = LLM이 채움. 만든 곳: refine(원본)·bluebird master fill(LLM)';
COMMENT ON COLUMN master.origin IS '[계산] contest 출처 표시. O = 원본 값, X = LLM 값, NULL = contest 없음. 만든 곳: refine·fill';
COMMENT ON COLUMN master.award IS '[원본] 수상 등급. 원본 수상 칸 값 그대로(표기 통일 안 함). 만든 곳: bluebird master refine(refine.AWARD)';
COMMENT ON COLUMN master.url IS '[원본] 원문 링크. 행 상세 URL, 없으면 데이터셋 출처 URL. 만든 곳: refine';
COMMENT ON COLUMN master.year IS '[원본] 제안·출품·수상 연도(수집 시점 아님). 원본 연도 칸 앞 4자리·두 자리 연도·회차 환산. 만든 곳: refine';
COMMENT ON COLUMN master.fetched IS '[원본] 원본을 받은 시각(= raw.fetched)';
COMMENT ON COLUMN master.keyword IS '[LLM] 대표 키워드 2~3개. 모델 gpt-4.1-mini, 입력 = 제목·본문 앞 2,500자·소스 정보. 만든 곳: bluebird master fill(fill.py)';
COMMENT ON COLUMN master.problem IS '[LLM] 해결하려는 문제 한 문장. 근거 없으면 NULL, 본문 없는 행 = 항상 NULL. 만든 곳: bluebird master fill(fill.py), refine이 본문 없으면 비움';
COMMENT ON COLUMN master.feature IS '[LLM] 핵심 기능·방법 한 문장. 근거 없으면 NULL, 본문 없는 행 = 항상 NULL. 만든 곳: bluebird master fill(fill.py)';
COMMENT ON COLUMN master.target IS '[LLM] 주 수혜·사용 대상. 근거 없으면 NULL, 본문 없는 행 = 항상 NULL. 만든 곳: bluebird master fill(fill.py)';
COMMENT ON COLUMN master.domain IS '[LLM] 분야. 고정 11개(행정·복지·교통·환경·경제·교육·안전·문화·보건·과학기술·기타) 중 1개 이상. 만든 곳: bluebird master fill(fill.py)';
COMMENT ON COLUMN master.exclude_reasons IS '[계산] 전처리 제외 사유 코드 목록(뜻 = exclusion_reason). 빈 배열 = 쓸 행. 행 삭제 없음. 만든 곳: bluebird master reasons(dedup.py·quality.py), AI 판정 코드 = quality.idea_label';
COMMENT ON COLUMN master.canonical_api IS '[계산] 중복(duplicate)일 때 남긴 대표 행 api. 만든 곳: bluebird master reasons(dedup.py)';
COMMENT ON COLUMN master.canonical_key IS '[계산] 중복(duplicate)일 때 남긴 대표 행 key. 만든 곳: bluebird master reasons(dedup.py)';
COMMENT ON COLUMN master.program_id IS '[계산] 대회·제도(program.id). 소스·행 대회명 규칙. 만든 곳: bluebird master classify(programs.py)';

-- ---------------------------------------------------------------- quality
COMMENT ON TABLE quality IS '[계산] 행 품질. master 1행 = 1행. 측정 칸 = 매번 재계산, idea_* = AI 판정(재계산 때 유지). 제외 사유는 master.exclude_reasons에 반영. 만든 곳: bluebird master reasons(quality.py)';
COMMENT ON COLUMN quality.api IS '[계산] master.api';
COMMENT ON COLUMN quality.key IS '[계산] master.key';
COMMENT ON COLUMN quality.title_len IS '[계산] 제목 내용 글자 수(공백·기호 제외). 제목 5자 이하 + 본문 10자 이하 = short_title_body';
COMMENT ON COLUMN quality.body_len IS '[계산] 본문 내용 글자 수(섹션 라벨 [..]·공백·기호 제외). 0 = no_body';
COMMENT ON COLUMN quality.hangul_ratio IS '[계산] 본문 내용 중 한글 비율. 표시만(제외 조건 아님). 본문 없음 = NULL';
COMMENT ON COLUMN quality.attachment_only IS '[계산] 본문 = 첨부·별첨·붙임 참조 문구뿐. 참 = attachment_only 사유';
COMMENT ON COLUMN quality.title_repeat IS '[계산] 본문 = 제목 반복뿐. 참 = title_repeat 사유';
COMMENT ON COLUMN quality.has_profanity IS '[계산] 욕설 단어 있음. 표시만(단어 규칙 오탐 → 제외 조건 아님)';
COMMENT ON COLUMN quality.has_repeat IS '[계산] ㅋㅋㅋㅋ·!!!! 같은 반복 있음. 표시만';
COMMENT ON COLUMN quality.idea_label IS '[AI판정] 아이디어 판정: idea · idea_thin · complaint · abusive · off_topic. idea 아니면 그 값이 제외 사유. NULL = 판정 전';
COMMENT ON COLUMN quality.idea_reason IS '[AI판정] 판정 근거 한 줄';
COMMENT ON COLUMN quality.idea_model IS '[AI판정] 판정한 모델 이름';
COMMENT ON COLUMN quality.idea_at IS '[AI판정] 판정 시각';

-- ---------------------------------------------------------------- program · exclusion_reason
COMMENT ON TABLE program IS '[계산] 대회·제도 분류 목록(종류 > 분야 > 이름). master.program_id가 가리킴. 만든 곳: bluebird master classify(programs.py PROGRAM)';
COMMENT ON COLUMN program.id IS '[계산] 일련번호';
COMMENT ON COLUMN program.kind IS '[계산] 종류: 공모전 · 시민 제안 · 직원 제안 (레지스트리 record_kind)';
COMMENT ON COLUMN program.field IS '[계산] 분야: 과학·발명, 주민참여예산 등 (programs.py PROGRAM)';
COMMENT ON COLUMN program.name IS '[계산] 대회·제도 이름. 과학·발명 소스 = 행 대회명(회차·연도 제거)';
COMMENT ON TABLE exclusion_reason IS '[기준표] 제외 사유 코드와 규칙(사람이 정함). master.exclude_reasons의 뜻';
COMMENT ON COLUMN exclusion_reason.code IS '[기준표] 사유 코드';
COMMENT ON COLUMN exclusion_reason.label IS '[기준표] 사유 이름';
COMMENT ON COLUMN exclusion_reason.rule IS '[기준표] 판정 조건';

-- ---------------------------------------------------------------- db_log · migrations (기존 설명 앞에 [기록]만 붙임)
COMMENT ON COLUMN db_log.id IS '일련번호';
DO $$
DECLARE c record;
BEGIN
    FOR c IN SELECT a.attname, col_description(a.attrelid, a.attnum) d FROM pg_attribute a
              WHERE a.attrelid = 'db_log'::regclass AND a.attnum > 0 AND NOT a.attisdropped LOOP
        EXECUTE format('COMMENT ON COLUMN db_log.%I IS %L', c.attname, '[기록] ' || c.d);
    END LOOP;
    EXECUTE format('COMMENT ON TABLE db_log IS %L', '[기록] ' || obj_description('db_log'::regclass));
END $$;
COMMENT ON TABLE migrations.applied IS '[기록] 구조 변경(마이그레이션) 적용 이력. 데이터 아님. 만든 곳: bluebird migrate(db/__init__.py)';
COMMENT ON COLUMN migrations.applied.target IS '[기록] 대상(master)';
COMMENT ON COLUMN migrations.applied.version IS '[기록] 마이그레이션 파일 이름(pipeline/bluebird/db/migrations/master/)';
COMMENT ON COLUMN migrations.applied.sha256 IS '[기록] 적용 당시 파일 sha256(이후 파일 수정 = migrate 실패)';
COMMENT ON COLUMN migrations.applied.applied_at IS '[기록] 적용 시각';

-- ---------------------------------------------------------------- 조회용 뷰
CREATE VIEW v_usable AS
SELECT m.api, m.key, m.title, m.body, m.contest, m.award, m.year, m.url,
       m.keyword, m.problem, m.feature, m.target, m.domain, p.kind, p.field, p.name AS program
  FROM master m LEFT JOIN program p ON p.id = m.program_id
 WHERE m.exclude_reasons = '{}';
COMMENT ON VIEW v_usable IS '[조회용 뷰] 쓸 수 있는 행(제외 사유 없음) + 대회·제도. 데이터 아님(master 저장 쿼리)';

CREATE VIEW v_reason_counts AS
SELECT r.code, r.label, r.rule, count(m.key) AS rows,
       count(m.key) FILTER (WHERE NOT 'duplicate' = ANY(m.exclude_reasons)) AS rows_not_duplicate
  FROM exclusion_reason r LEFT JOIN master m ON r.code = ANY(m.exclude_reasons)
 GROUP BY r.code, r.label, r.rule;
COMMENT ON VIEW v_reason_counts IS '[조회용 뷰] 제외 사유별 행 수(전체 · 중복 아닌 행). 데이터 아님';

CREATE VIEW v_excluded AS
SELECT m.api, m.key, m.title, m.body, m.exclude_reasons, p.kind, p.name AS program,
       q.title_len, q.body_len, q.attachment_only, q.title_repeat, q.idea_label, q.idea_reason
  FROM master m LEFT JOIN program p ON p.id = m.program_id LEFT JOIN quality q USING (api, key)
 WHERE m.exclude_reasons <> '{}';
COMMENT ON VIEW v_excluded IS '[조회용 뷰] 제외된 행 + 사유 + 판정 근거 칸(글자 수·첨부·제목 반복·AI 판정). 데이터 아님';

CREATE VIEW v_flagged AS
SELECT m.api, m.key, m.title, m.body, q.body_len, q.has_profanity, q.has_repeat, q.hangul_ratio
  FROM master m JOIN quality q USING (api, key)
 WHERE m.exclude_reasons = '{}' AND (q.has_profanity OR q.has_repeat OR q.hangul_ratio < 0.3);
COMMENT ON VIEW v_flagged IS '[조회용 뷰] 쓸 행 중 의심 표시(욕설·반복·한글 30% 미만)가 붙은 행. 제외 아님, 확인용. 데이터 아님';
