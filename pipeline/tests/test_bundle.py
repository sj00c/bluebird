import io
import tarfile
from pathlib import Path

import pytest

from bluebird.bundle import (
    BundleError,
    generate_keypair,
    load_private_key,
    load_public_key,
    move_bundles,
    read_bundle,
    write_bundle,
)


@pytest.fixture
def keys(tmp_path):
    generate_keypair(tmp_path / "k", "z1")
    generate_keypair(tmp_path / "k", "z2")
    return {
        "z1": (load_private_key(tmp_path / "k/z1.key"), load_public_key(tmp_path / "k/z1.pub")),
        "z2": (load_private_key(tmp_path / "k/z2.key"), load_public_key(tmp_path / "k/z2.pub")),
    }


def _write(tmp_path, keys, rows=None):
    rows = rows if rows is not None else [{"a": 1, "t": "한글"}, {"a": 2, "t": "x"}]
    return write_bundle(tmp_path / "out", zone="z1", kind="collect", source="s1",
                        tables={"award_record": rows}, key=keys["z1"][0])


def test_roundtrip(tmp_path, keys):
    p = _write(tmp_path, keys)
    b = read_bundle(p, public_key=keys["z1"][1], expect_zone="z1", expect_kind="collect")
    assert list(b.rows("award_record")) == [{"a": 1, "t": "한글"}, {"a": 2, "t": "x"}]
    assert b.manifest["files"][0]["rows"] == 2
    assert not list((tmp_path / "out").glob(".*part"))


def test_wrong_key_rejected(tmp_path, keys):
    p = _write(tmp_path, keys)
    with pytest.raises(BundleError, match="signature"):
        read_bundle(p, public_key=keys["z2"][1], expect_zone="z1", expect_kind="collect")


def test_wrong_zone_or_kind_rejected(tmp_path, keys):
    p = _write(tmp_path, keys)
    with pytest.raises(BundleError, match="expected"):
        read_bundle(p, public_key=keys["z1"][1], expect_zone="z2", expect_kind="publish")


def _rewrite(src: Path, dst: Path, mutate) -> None:
    with tarfile.open(src) as t:
        members = {m.name: t.extractfile(m).read() for m in t.getmembers()}
    mutate(members)
    with tarfile.open(dst, "w") as t:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))


def test_tampered_payload_rejected(tmp_path, keys):
    p = _write(tmp_path, keys)
    bad = tmp_path / "bad.tar"
    _rewrite(p, bad, lambda m: m.__setitem__("award_record.ndjson.gz", m["award_record.ndjson.gz"] + b"x"))
    with pytest.raises(BundleError, match="sha256"):
        read_bundle(bad, public_key=keys["z1"][1], expect_zone="z1", expect_kind="collect")


def test_extra_member_rejected(tmp_path, keys):
    p = _write(tmp_path, keys)
    bad = tmp_path / "bad.tar"
    _rewrite(p, bad, lambda m: m.__setitem__("evil.ndjson.gz", b""))
    with pytest.raises(BundleError, match="member set mismatch"):
        read_bundle(bad, public_key=keys["z1"][1], expect_zone="z1", expect_kind="collect")


def test_path_member_rejected(tmp_path, keys):
    p = _write(tmp_path, keys)
    bad = tmp_path / "bad.tar"
    _rewrite(p, bad, lambda m: m.__setitem__("../x", b""))
    with pytest.raises(BundleError, match="unexpected member"):
        read_bundle(bad, public_key=keys["z1"][1], expect_zone="z1", expect_kind="collect")


def test_move_only_complete_bundles(tmp_path, keys):
    p = _write(tmp_path, keys)
    (p.parent / ".partial.tar.part").write_bytes(b"x")
    moved = move_bundles(p.parent, tmp_path / "inbox")
    assert [m.name for m in moved] == [p.name]
    assert not p.exists()
    assert (p.parent / ".partial.tar.part").exists()
