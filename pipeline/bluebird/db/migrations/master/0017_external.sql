-- 최근 문제 → 과거 아이디어(docs/DEMAND_PLAN.md). 바깥 자료 = 스키마 external(표 2개). master와 api·key로만 연결
CREATE SCHEMA external;
COMMENT ON SCHEMA external IS '[원본] 바깥 공식 자료: 법령이 바뀐 기록(external.law) + 정책뉴스·보도자료·국회 법률안(external.doc). 만든 곳: docs/DEMAND_PLAN.md';

CREATE TABLE external.law (
    kind      text NOT NULL CHECK (kind IN ('law', 'ordin', 'admrul')),
    id        text NOT NULL,
    name      text NOT NULL,
    type      text,
    org       text,
    announced date,
    effective date,
    reason    text,
    summary   text,
    embedding halfvec(1536),
    url       text,
    fetched   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, id)
);
COMMENT ON TABLE external.law IS '[원본] 법령·조례·행정규칙이 바뀐 기록. 1행 = 공포 1건(같은 법령의 다음 개정 = 새 행, 추가만). 출처 = 국가법령정보 공동활용 Open API';
COMMENT ON COLUMN external.law.kind IS '[원본] 종류: law(법률·시행령·시행규칙) · ordin(자치법규·조례) · admrul(행정규칙·고시·훈령)';
COMMENT ON COLUMN external.law.id IS '[원본] 공포 단위 id(법령일련번호·자치법규일련번호·행정규칙일련번호)';
COMMENT ON COLUMN external.law.name IS '[원본] 법령명';
COMMENT ON COLUMN external.law.type IS '[원본] 제정·일부개정·전부개정·폐지 등';
COMMENT ON COLUMN external.law.org IS '[원본] 소관 기관(부처·지자체)';
COMMENT ON COLUMN external.law.announced IS '[원본] 공포일';
COMMENT ON COLUMN external.law.effective IS '[원본] 시행일. 바뀐 날짜 기준';
COMMENT ON COLUMN external.law.reason IS '[원본] 제정·개정 이유 원문';
COMMENT ON COLUMN external.law.summary IS '[LLM] 무엇이 바뀌어 무엇이 가능해졌나 한 문장(개정 이유 기준)';
COMMENT ON COLUMN external.law.embedding IS '[LLM] summary 벡터(text-embedding-3-small, 1536 halfvec)';
COMMENT ON COLUMN external.law.url IS '[원본] 국가법령정보센터 링크(인증 코드 제거)';
COMMENT ON COLUMN external.law.fetched IS '[원본] 받은 시각';

CREATE TABLE external.doc (
    source    text NOT NULL,
    id        text NOT NULL,
    title     text NOT NULL,
    date      date,
    org       text,
    domain    text,
    url       text,
    body      text,
    problem   text,
    evidence  text,
    verified  boolean,
    embedding halfvec(1536),
    ideas     jsonb,
    fetched   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, id)
);
COMMENT ON TABLE external.doc IS '[원본] 최근 공식 자료 1건 = 1행(정책뉴스·부처 보도자료·국회 법률안). 문제 한 문장을 뽑아 master 아이디어와 연결';
COMMENT ON COLUMN external.doc.source IS '[원본] 출처: policy_news(정책브리핑) · press_msit·press_mss·press_moef(부처 보도자료) · bill(국회 발의법률안)';
COMMENT ON COLUMN external.doc.id IS '[원본] 출처 안 원문 id';
COMMENT ON COLUMN external.doc.title IS '[원본] 제목';
COMMENT ON COLUMN external.doc.date IS '[원본] 게시·발의일';
COMMENT ON COLUMN external.doc.org IS '[원본] 기관(부처·발의 의원)';
COMMENT ON COLUMN external.doc.domain IS '[계산] 도메인(master.domain 목록). 기관 → 도메인 규칙';
COMMENT ON COLUMN external.doc.url IS '[원본] 원문 링크';
COMMENT ON COLUMN external.doc.body IS '[원본] 본문(법률안 = 제안 이유 및 주요 내용)';
COMMENT ON COLUMN external.doc.problem IS '[LLM] 자료가 말하는 핵심 문제 한 문장. master 목표와 같은 형식. 해결할 문제가 없는 자료 = NULL';
COMMENT ON COLUMN external.doc.evidence IS '[LLM] 문제를 뽑은 원문 구절(그대로 복사)';
COMMENT ON COLUMN external.doc.verified IS '[계산] evidence가 본문에 실제로 있음(공백 무시)';
COMMENT ON COLUMN external.doc.embedding IS '[LLM] problem 벡터(text-embedding-3-small, 1536 halfvec). master.embedding과 비교';
COMMENT ON COLUMN external.doc.ideas IS '[LLM] 관련 master 아이디어 목록: [{api, key, score(유사도), rel(LLM 판정 2 같은 문제 · 1 관련 · 0 무관), why}]';
COMMENT ON COLUMN external.doc.fetched IS '[원본] 받은 시각';
