"""Console runtime configuration, read when a request needs the core database."""

import os


def database_dsn() -> str:
    dsn = os.environ.get("BB_DSN")
    if not dsn:
        raise RuntimeError("BB_DSN not set")
    return dsn
