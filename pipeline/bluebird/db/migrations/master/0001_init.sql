-- 정제 DB(bluebird_master). 표 2개: raw(받은 그대로) → master(정제 + LLM 필드).
-- 기존 bluebird_core와 별개. 컬럼명 = 영어 한 단어.

-- 받은 그대로. 파일 = 행 하나가 payload(원본 헤더 → 값), API = 응답 레코드 전체.
CREATE TABLE raw (
    source  text NOT NULL,          -- 레지스트리 소스 id(…-sources.toml)
    key     text NOT NULL,          -- 소스 안 레코드 키(API 고유번호, 없으면 파일 행 번호)
    payload jsonb NOT NULL,
    fetched timestamptz NOT NULL,   -- 우리가 받은 시각(파일 = 내려받은 파일 시각)
    PRIMARY KEY (source, key)
);

-- 정제본. raw 1행 = master 최대 1행.
CREATE TABLE master (
    api     text NOT NULL,          -- 수집 소스 = raw.source
    key     text NOT NULL,
    title   text NOT NULL,
    body    text,
    contest text,                   -- 공모전명. 원본에 있을 때만
    url     text,
    year    smallint,               -- 원 데이터 시기(제안·출품·수상 연도)
    fetched timestamptz NOT NULL,
    keyword text[],                 -- 이하 LLM
    problem text,
    feature text,
    target  text,
    domain  text[] CHECK (domain <@ ARRAY['행정','복지','교통','환경','경제','교육','안전','문화','보건','과학기술','기타']),
    PRIMARY KEY (api, key),
    FOREIGN KEY (api, key) REFERENCES raw (source, key) ON DELETE CASCADE
);
