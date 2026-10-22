-- 아이디어 벡터(사용 대상만). 확장 pgvector(0.7 이상, halfvec) 필요 = 서버 이미지 pgvector/pgvector:pg16
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE master ADD COLUMN embedding_input text, ADD COLUMN embedding halfvec(1536);
CREATE INDEX master_embedding ON master USING hnsw (embedding halfvec_cosine_ops);

COMMENT ON COLUMN master.embedding_input IS '[계산] 벡터에 넣은 글 = 목표(끝 상투어 제거) + 해결책 + 핵심 기능, ". "로 이음. 분야·유형·근거·제목·본문 안 넣음. 사용 대상만, 나머지 NULL. 만든 곳: bluebird master embed(embed.py)';
COMMENT ON COLUMN master.embedding IS '[LLM] embedding_input의 벡터. OpenAI text-embedding-3-small 1536차원, 반정밀도(halfvec). 코사인 거리 색인 master_embedding. 만든 곳: bluebird master embed(embed.py)';
