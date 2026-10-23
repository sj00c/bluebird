"""검색 HTTP API(읽기 전용): GET /search, GET /healthz. 실행 = bluebird master serve.

- 검색 방식 = search.py(docs/SEARCH_PLAN.md). 질문 글 = egress로만 나감(벡터·재정렬), 기록 = .runtime/egress-*.jsonl
- BM25 색인 = 범위(Filter)별로 처음 쓸 때 한 번 만들고 프로세스 안에 둠. DB 글이 바뀌면 서버 재시작
- 콘솔 백엔드(api.py, 외부 호출 금지)와 별개 프로세스
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from . import db, search
from .egress import Egress, EgressError

logger = logging.getLogger(__name__)
METHOD = {True: "형태소 단어 검색(BM25)과 의미 검색(벡터)을 섞은 뒤 AI가 관련 있는 것만 골라 순서를 정함",
          False: "형태소 단어 검색(BM25)과 의미 검색(벡터)을 섞은 순위(AI 재정렬 없음)"}


def create_app(*, dsn: str, sources: list[dict]) -> FastAPI:
    egress = Egress.for_master([*sources, search.QUERY_SOURCE], timeout=60.0)
    indexes: dict[search.Filter, search.Index] = {}
    lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        egress.close()

    app = FastAPI(title="bluebird 아이디어 검색", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def index_for(conn, flt: search.Filter) -> search.Index:
        with lock:
            if flt not in indexes:
                indexes[flt] = search.Index.load(conn, flt)
            return indexes[flt]

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/search")
    def find(q: Annotated[str, Query(min_length=2, max_length=300)],
             top: Annotated[int, Query(ge=1, le=20)] = search.TOP,
             rerank: bool = True,
             year_min: int | None = None, year_max: int | None = None,
             kind: Annotated[list[str] | None, Query()] = None,
             domain: Annotated[list[str] | None, Query()] = None,
             item_type: Annotated[list[str] | None, Query()] = None,
             awarded: bool = False) -> dict:
        query = q.strip()
        if len(query) < 2:
            raise HTTPException(422, "두 글자 이상 입력해 주세요.")
        flt = search.Filter(year_min, year_max, tuple(kind or ()), tuple(domain or ()), tuple(item_type or ()), awarded)
        try:
            with db.connect(dsn) as conn:
                items = search.search(conn, egress, index_for(conn, flt), query, flt=flt, top=top, use_rerank=rerank)
        except EgressError as exc:
            logger.error("search egress failed: %s", type(exc).__name__)
            raise HTTPException(503, "AI 호출에 실패했습니다(키·네트워크 확인).") from None
        except Exception:
            logger.exception("search failed")
            raise HTTPException(503, "검색에 실패했습니다. 서버 로그를 확인해 주세요.") from None
        return {"query": query, "method": METHOD[rerank], "items": items}

    return app
