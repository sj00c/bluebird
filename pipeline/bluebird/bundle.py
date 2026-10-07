"""망 간 전송 번들: 서명된 manifest + gzip NDJSON 테이블을 담은 tar 1개.

구역(zone) 체인: z1(수집존) → z2(처리존) → z3(공개존), 이용자 제출은 z3 → z2.
각 구역은 자기 서명키(Ed25519 개인키)로 번들을 서명하고, 받는 구역은 보낸 구역의 공개키로 검증한다.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
import tarfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SCHEMA_VERSION = 1
ZONES = ("z1", "z2", "z3")
KINDS = ("collect", "publish", "ticket")
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MANIFEST = "manifest.json"
SIGNATURE = "manifest.sig"


class BundleError(Exception):
    """번들 형식·서명·무결성 위반. 받는 쪽은 이 번들을 격리(quarantine)한다."""


def generate_keypair(directory: Path, zone: str) -> tuple[Path, Path]:
    if zone not in ZONES:
        raise ValueError(f"unknown zone {zone!r}")
    directory.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    priv = directory / f"{zone}.key"
    pub = directory / f"{zone}.pub"
    priv.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    os.chmod(priv, 0o600)
    pub.write_bytes(
        key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    return priv, pub


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(f"{path} is not an Ed25519 private key")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError(f"{path} is not an Ed25519 public key")
    return key


def _ndjson_gz(rows: Iterable[dict]) -> tuple[bytes, int]:
    buf = io.BytesIO()
    count = 0
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for row in rows:
            gz.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            gz.write(b"\n")
            count += 1
    return buf.getvalue(), count


def _add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def write_bundle(
    out_dir: Path,
    *,
    zone: str,
    kind: str,
    source: str,
    tables: dict[str, Iterable[dict]],
    key: Ed25519PrivateKey,
    meta: dict | None = None,
) -> Path:
    """테이블별 행을 번들로 묶어 out_dir에 원자적으로 생성한다(.part → rename)."""
    if zone not in ZONES or kind not in KINDS:
        raise ValueError(f"invalid zone/kind {zone}/{kind}")
    now = datetime.now(UTC)
    bundle_id = f"{zone}-{kind}-{source}-{now:%Y%m%dT%H%M%S%f}Z"
    files: list[dict] = []
    payloads: dict[str, bytes] = {}
    for table, rows in tables.items():
        data, count = _ndjson_gz(rows)
        name = f"{table}.ndjson.gz"
        payloads[name] = data
        files.append({"name": name, "table": table, "rows": count, "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {
        "bundle_id": bundle_id,
        "schema_version": SCHEMA_VERSION,
        "zone": zone,
        "kind": kind,
        "source": source,
        "created_at": now.isoformat(),
        "files": files,
        "meta": meta or {},
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    signature = key.sign(manifest_bytes)

    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"{bundle_id}.tar"
    part = out_dir / f".{bundle_id}.tar.part"
    with tarfile.open(part, "w") as tar:
        _add(tar, MANIFEST, manifest_bytes)
        _add(tar, SIGNATURE, signature)
        for name, data in payloads.items():
            _add(tar, name, data)
    os.replace(part, final)
    return final


@dataclass(frozen=True)
class Bundle:
    path: Path
    manifest: dict
    _payloads: dict[str, bytes]

    @property
    def bundle_id(self) -> str:
        return self.manifest["bundle_id"]

    @property
    def tables(self) -> list[str]:
        return [f["table"] for f in self.manifest["files"]]

    def rows(self, table: str) -> Iterator[dict]:
        entry = next((f for f in self.manifest["files"] if f["table"] == table), None)
        if entry is None:
            return iter(())
        text = gzip.decompress(self._payloads[entry["name"]]).decode("utf-8")
        return (json.loads(line) for line in text.splitlines() if line)


def read_bundle(path: Path, *, public_key: Ed25519PublicKey, expect_zone: str, expect_kind: str) -> Bundle:
    """서명·해시·행 수·구성 파일을 모두 검증한 뒤 Bundle을 돌려준다. 하나라도 어긋나면 BundleError."""
    members: dict[str, bytes] = {}
    try:
        with tarfile.open(path, "r") as tar:
            for m in tar.getmembers():
                if not m.isfile() or "/" in m.name or m.name.startswith("."):
                    raise BundleError(f"unexpected member {m.name!r}")
                if m.size > MAX_MEMBER_BYTES:
                    raise BundleError(f"member too large {m.name!r}")
                if m.name in members:
                    raise BundleError(f"duplicate member {m.name!r}")
                fh = tar.extractfile(m)
                assert fh is not None
                members[m.name] = fh.read()
    except tarfile.TarError as e:
        raise BundleError(f"not a valid tar: {e}") from e

    manifest_bytes = members.pop(MANIFEST, None)
    signature = members.pop(SIGNATURE, None)
    if manifest_bytes is None or signature is None:
        raise BundleError("missing manifest or signature")
    try:
        public_key.verify(signature, manifest_bytes)
    except InvalidSignature as e:
        raise BundleError("signature verification failed") from e

    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise BundleError(f"unsupported schema_version {manifest.get('schema_version')}")
    if manifest.get("zone") != expect_zone or manifest.get("kind") != expect_kind:
        raise BundleError(f"expected {expect_zone}/{expect_kind}, got {manifest.get('zone')}/{manifest.get('kind')}")
    declared = {f["name"] for f in manifest["files"]}
    if declared != set(members):
        raise BundleError(f"member set mismatch: declared={sorted(declared)} actual={sorted(members)}")
    for f in manifest["files"]:
        data = members[f["name"]]
        if hashlib.sha256(data).hexdigest() != f["sha256"]:
            raise BundleError(f"sha256 mismatch for {f['name']}")
        lines = gzip.decompress(data).count(b"\n")
        if lines != f["rows"]:
            raise BundleError(f"row count mismatch for {f['name']}: {lines} != {f['rows']}")
    return Bundle(path=path, manifest=manifest, _payloads=members)


def pending_bundles(inbox: Path) -> list[Path]:
    return sorted(p for p in inbox.glob("*.tar") if not p.name.startswith("."))


def move_bundles(src: Path, dst: Path) -> list[Path]:
    """시험 환경의 망연계 대체: src(outbox)의 완성된 번들을 dst(inbox)로 원자적으로 옮긴다."""
    dst.mkdir(parents=True, exist_ok=True)
    moved = []
    for p in pending_bundles(src):
        tmp = dst / f".{p.name}.part"
        shutil.copyfile(p, tmp)
        os.replace(tmp, dst / p.name)
        p.unlink()
        moved.append(dst / p.name)
    return moved


def archive(path: Path, done_dir: Path) -> Path:
    done_dir.mkdir(parents=True, exist_ok=True)
    target = done_dir / path.name
    shutil.move(path, target)
    return target
