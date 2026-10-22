-- external.law 행마다 출처를 글로 표기(기관 · 서비스 · 호출 이름). 수집기가 채움(laws.SOURCE)
ALTER TABLE external.law ADD COLUMN source text;
UPDATE external.law SET source = CASE kind
    WHEN '법령' THEN '법제처 국가법령정보 공동활용 Open API · 법령 변경이력 목록(lawSearch, target=lsHstInf, 변경일별) · 개정 이유 = 법령 본문(lawService, target=law, MST=법령일련번호)'
    WHEN '자치법규' THEN '법제처 국가법령정보 공동활용 Open API · 자치법규 목록(lawSearch, target=ordin, 시행일 범위, 현행본)'
END WHERE source IS NULL;
ALTER TABLE external.law ALTER COLUMN source SET NOT NULL;
COMMENT ON COLUMN external.law.source IS '[원본] 출처: 기관 · 서비스 · 호출 이름(목록·개정 이유 각각). 원문 확인 = url';
COMMENT ON COLUMN external.doc.source IS '[원본] 출처: 기관 · 서비스 · 데이터 번호(예: 문화체육관광부 정책브리핑 정책뉴스, 공공데이터포털 15095335)';
