# 업무망 backend 이미지(backend-jobs). 외부 호출은 egress 모듈 → DMZ 프록시로만.
# 업무망 반입: 빌드 → docker save → 기관 반입 절차(서명·검사) → docker load
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
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER bluebird
ENTRYPOINT ["bluebird"]
