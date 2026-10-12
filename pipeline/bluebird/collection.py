"""Repeatable official contest collection through audited Egress and the seed adapters."""

from __future__ import annotations

import csv
import html
import json
import os
import re
import tempfile
import tomllib
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import psycopg

from . import ingest
from .egress import Egress, EgressError
from .sources import ADAPTERS, SourceSpec, file_sha256, load_sources

MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024


class CollectionError(ValueError):
    pass


class _MetadataScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts: list[str] = []
        self._parts: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self._parts = []

    def handle_data(self, data):
        if self._parts is not None:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._parts is not None:
            self.scripts.append("".join(self._parts))
            self._parts = None


def _official_url(url: str, host: str) -> str:
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in {host, "www." + host}
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise CollectionError(f"expected an HTTPS {host} URL")
    return url


def _response(response, limit: int, *, label: str) -> bytes:
    if response.status != 200:
        raise CollectionError(f"{label}: HTTP {response.status}")
    if not response.content or len(response.content) > limit:
        raise CollectionError(f"{label}: empty or oversized response (limit {limit} bytes)")
    return response.content


def download_data_go(*, source: dict, destination: Path, egress: Egress) -> dict:
    """Discover the current portal attachment, rather than pinning an expiring file ID."""
    dataset_id = str(source.get("dataset_id", ""))
    if not re.fullmatch(r"\d+", dataset_id):
        raise CollectionError("data_go_csv requires a numeric dataset_id")
    detail_url = _official_url(source["url"], "data.go.kr")
    if urlsplit(detail_url).path != f"/data/{dataset_id}/fileData.do":
        raise CollectionError("detail URL does not match dataset_id")
    response = egress.get("collect", detail_url, path_template="/data/{dataset_id}/fileData.do")
    content = _response(response, MAX_METADATA_BYTES, label="dataset metadata")
    parser = _MetadataScripts()
    parser.feed(content.decode("utf-8-sig"))
    attachments = set()
    for script in parser.scripts:
        # Some official descriptions contain unescaped quotes, making the whole
        # JSON-LD invalid. Parse only the independently valid URL string value.
        if not re.search(r'"encodingFormat"\s*:\s*"(?:CSV|text/csv)"', script, re.IGNORECASE):
            continue
        for match in re.finditer(r'"contentUrl"\s*:\s*("(?:[^"\\]|\\.)*")', script):
            url = urljoin(detail_url, html.unescape(json.loads(match.group(1))))
            _official_url(url, "data.go.kr")
            if urlsplit(url).path == "/cmm/cmm/fileDownload.do":
                attachments.add(url)
    if len(attachments) != 1:
        raise CollectionError(f"expected one official CSV attachment, found {len(attachments)}")
    url = attachments.pop()
    response = egress.get("collect", url, path_template="/cmm/cmm/fileDownload.do")
    payload = _response(response, MAX_DOWNLOAD_BYTES, label="CSV attachment")
    if ("html" in response.headers.get("content-type", "").lower()
            or payload.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<")):
        raise CollectionError("CSV attachment returned HTML/XML instead of data")
    destination.write_bytes(payload)
    return {"url": url, "bytes": len(payload)}


def _download(*, source: dict, destination: Path, egress: Egress) -> dict:
    if source.get("collector") == "data_go_csv":
        return download_data_go(source=source, destination=destination, egress=egress)
    if source.get("collector") == "science_archive":
        from .collect_science import download
        return download(source=source, destination=destination, egress=egress)
    if source.get("collector") == "kidp_awards":
        from .collect_design import download
        return download(source=source, destination=destination, egress=egress)
    raise CollectionError(f"unknown collector: {source.get('collector')!r}")


def _sources(configs: list[Path], out_dir: Path, only: str | None) -> list[tuple[Path, SourceSpec, dict]]:
    selected = []
    ids, files = set(), set()
    for config in configs:
        raw_sources = tomllib.loads(config.read_text(encoding="utf-8")).get("source", [])
        for spec, raw in zip(load_sources(config, out_dir), raw_sources, strict=True):
            filename = raw["file"]
            if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".csv"):
                raise CollectionError(f"source {spec.id}: file must be a plain CSV filename")
            if spec.id in ids or filename in files:
                raise CollectionError(f"duplicate source ID or output filename: {spec.id}")
            ids.add(spec.id)
            files.add(filename)
            if spec.adapter != "mapped_contest_csv":
                raise CollectionError(f"source {spec.id}: collection requires mapped_contest_csv")
            if spec.public_ok or spec.export_grade != "pending" or spec.policy_approved_by or spec.policy_approved_at:
                raise CollectionError(f"source {spec.id}: collection must remain unapproved and pending")
            if only is None or spec.id == only:
                selected.append((config, spec, raw))
    if not selected:
        raise CollectionError(f"no contest sources selected{': ' + only if only else ''}")
    return selected


def collect_contests(*, configs: list[Path], out_dir: Path, secret_path: Path,
                     dsn: str, egress: Egress, only: str | None = None,
                     download_only: bool = False) -> list[dict]:
    """Validate a private candidate before ingestion/replacement; failures keep last-good files."""
    sources = _sources(configs, out_dir, only)
    secret = ingest.load_secret(secret_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for config, spec, raw in sources:
        result = {"source": spec.id, "status": "error"}
        try:
            with tempfile.TemporaryDirectory(prefix=".contest-", dir=out_dir) as staging:
                candidate = Path(staging) / spec.path.name
                metadata = _download(source=raw, destination=candidate, egress=egress)
                if not candidate.is_file() or not 0 < candidate.stat().st_size <= MAX_DOWNLOAD_BYTES:
                    raise CollectionError("collector produced an empty or oversized file")
                candidate_spec = replace(spec, path=candidate)
                rows = 0
                for row in ADAPTERS[spec.adapter](candidate_spec, secret):
                    ingest._validate(row, candidate_spec)
                    rows += 1
                if not rows:
                    raise CollectionError("CSV contains no qualifying project records")
                result.update(download_rows=rows, download=metadata)
                unchanged = spec.path.exists() and file_sha256(spec.path) == file_sha256(candidate)
                if not download_only:
                    imported = ingest.ingest(dsn=dsn, config=config, seed_dir=Path(staging),
                                             secret_path=secret_path, only=spec.id)
                    if len(imported) != 1 or imported[0]["status"] not in {"ok", "unchanged"}:
                        raise CollectionError("ingestion did not succeed")
                    result["ingest"] = imported[0]
                # Same-volume rename is atomic, and an ingestion failure never replaces
                # a usable local snapshot. Raw files remain private; only adapters emit records.
                if not unchanged:
                    candidate.chmod(0o600)
                    with candidate.open("rb") as stream:
                        os.fsync(stream.fileno())
                    os.replace(candidate, spec.path)
                result["status"] = "unchanged" if unchanged else "downloaded" if download_only else "ingested"
        except (ValueError, KeyError, TypeError, OSError, csv.Error,
                ingest.IngestError, EgressError, psycopg.Error) as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return results
