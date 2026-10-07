# 수집존(collector)·처리존(worker)·공개존(importer) 공용 파이프라인 이미지.
# 내부망 반입: 인터넷망 CI에서 빌드 → docker save → 망연계 반입 → docker load (서명 검증 후)
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY bluebird ./bluebird
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --system --uid 10001 --home /app bluebird
WORKDIR /app
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER bluebird
ENTRYPOINT ["bluebird"]
