from __future__ import annotations

from pathlib import Path

from synapse.infra.contract_snapshot import (
    SnapshotConfig,
    build_snapshot,
    compute_hashes,
    file_sha256,
    read_snapshot,
    write_snapshot,
)


def test_snapshot_write_no_bom(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hola", encoding="utf-8")

    hashes = compute_hashes([f], base_dir=tmp_path)
    payload = build_snapshot(
        config=SnapshotConfig(name="t", schema_version="v1", include_timestamp=False),
        hashes=hashes,
        meta={"x": 1},
    )

    out = tmp_path / "snap.json"
    write_snapshot(out, payload)

    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # BOM check
    loaded = read_snapshot(out)
    assert loaded["hashes"] == hashes
    assert loaded["self_hash"] == payload["self_hash"]


def test_file_sha256_matches(tmp_path: Path) -> None:
    f = tmp_path / "b.txt"
    f.write_text("abc", encoding="utf-8")
    assert file_sha256(f) == file_sha256(f)
