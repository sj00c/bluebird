-- 단어 검색(BM25)용 형태소 토큰. 검색 방식·값 = docs/SEARCH_PLAN.md
ALTER TABLE master ADD COLUMN search_tokens text;

COMMENT ON COLUMN master.search_tokens IS '[계산] embedding_input의 Kiwi 형태소 중 명사·어근·영문·숫자(NNG NNP XR SL SN)를 공백으로 이음. BM25 단어 검색용. 사용 대상만, 나머지 NULL. 만든 곳: bluebird master embed(search.py tokens)';
