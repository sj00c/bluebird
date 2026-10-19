-- 아이디어 임베딩·비지도 계층 군집(2026-10-13 사용자 결정).
--
--   대상       : 비퇴역 + length(core.body_key(body)) >= 50. 제목만 있는 기록은 이번 범위 밖.
--   모델 키    : provider:model:dims (예: openai:text-embedding-3-large:3072). 평가 캐시 변형은
--                접미사 :notitle(본문에서 제목을 지운 입력)·:title(제목만). `embed run`은 정확히 같은 키의
--                대상 밖 행만 지우므로 평가 캐시 행은 남는다.
--   벡터       : 차원을 고정하지 않은 halfvec + dims(3072차원까지 저장). HNSW 인덱스는 모델을 정한 뒤 따로 만든다.
--   input_sha256: 모델에 보낸 입력 문자열의 sha256. 같으면 다시 호출하지 않는다(증분).
--   군집       : run 단위로 쌓는다(이전 run은 덮어쓰지 않음). level 1 = 대분류, level 2 = 세부(parent = 대분류).
--                idea_cluster는 세부 군집만 가리킨다(대분류 = 세부의 parent). duplicate_record는 학습에서 빠지고
--                대표(canonical) 기록의 세부 군집을 상속한다(inherited_from = 대표 id).
--   egress 용도 analysis: 임베딩·군집 이름 호출. 반출 등급 검사만 면제(egress.Policy.check).

ALTER TABLE core.idea_embedding
    ALTER COLUMN vec TYPE halfvec USING vec::halfvec,
    ADD COLUMN dims smallint NOT NULL,
    ADD COLUMN input_sha256 text NOT NULL,
    ADD COLUMN egress_call_id bigint REFERENCES core.egress_call(id),
    ADD COLUMN embedded_at timestamptz NOT NULL DEFAULT now(),
    ADD CONSTRAINT idea_embedding_dims_check CHECK (vector_dims(vec) = dims);
CREATE INDEX idea_embedding_model_idx ON core.idea_embedding (model);

ALTER TABLE core.egress_call DROP CONSTRAINT egress_call_purpose_check;
ALTER TABLE core.egress_call ADD CONSTRAINT egress_call_purpose_check
    CHECK (purpose IN ('collect', 'signal', 'trace', 'llm', 'source_check', 'analysis'));

CREATE TABLE core.cluster_run (
    id          bigserial PRIMARY KEY,
    method      text NOT NULL CHECK (method IN ('kmeans_ward', 'umap_hdbscan')),
    embed_model text NOT NULL,
    params      jsonb NOT NULL,
    metrics     jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.cluster (
    id        bigserial PRIMARY KEY,
    run_id    bigint NOT NULL REFERENCES core.cluster_run(id) ON DELETE CASCADE,
    level     smallint NOT NULL CHECK (level IN (1, 2)),
    label     integer NOT NULL,
    parent_id bigint REFERENCES core.cluster(id) ON DELETE CASCADE,
    name      text,
    summary   text,
    metrics   jsonb NOT NULL DEFAULT '{}',
    UNIQUE (run_id, level, label),
    CHECK ((level = 1) = (parent_id IS NULL))
);
CREATE INDEX cluster_parent_idx ON core.cluster (parent_id);

CREATE TABLE core.idea_cluster (
    run_id         bigint NOT NULL REFERENCES core.cluster_run(id) ON DELETE CASCADE,
    idea_id        text NOT NULL REFERENCES core.idea(id),
    sub_id         bigint NOT NULL REFERENCES core.cluster(id) ON DELETE CASCADE,
    distance       real,
    inherited_from text REFERENCES core.idea(id),
    PRIMARY KEY (run_id, idea_id)
);
CREATE INDEX idea_cluster_sub_idx ON core.idea_cluster (sub_id);

GRANT SELECT ON core.cluster_run, core.cluster, core.idea_cluster TO bb_api;
