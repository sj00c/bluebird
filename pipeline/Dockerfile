# 로컬 backend 이미지: jobs와 API가 공유하며, 외부 HTTP는 egress 모듈로 제한한다.
# 잠금 파일로 설치하고 런타임에는 uv·개발 도구를 포함하지 않는다.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY bluebird ./bluebird
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --system --uid 10001 --home /app bluebird \
 && mkdir /signals && chown bluebird /signals
WORKDIR /app
COPY --from=build /app /app
# NUMBA_CACHE_DIR: umap(numba)이 읽기 전용 site-packages 대신 쓸 캐시 위치
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 NUMBA_CACHE_DIR=/tmp/numba
USER bluebird
ENTRYPOINT ["bluebird"]
