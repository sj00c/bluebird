"""Console backend composition and stable ASGI/module entrypoints.

HTTP authentication, request schemas, routes and read projections live in
bluebird.http. Domain writes use funnel and coding, never HTTP-specific SQL.
The backend makes no external calls and does not use the egress client.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from .http import routes

app = FastAPI(title="bluebird backend-api", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(routes.router)


def main() -> None:
    import uvicorn
    uvicorn.run(app, host=os.environ.get("BB_API_HOST", "0.0.0.0"), port=int(os.environ.get("BB_API_PORT", "8000")),
                proxy_headers=False, server_header=False)


if __name__ == "__main__":
    main()
