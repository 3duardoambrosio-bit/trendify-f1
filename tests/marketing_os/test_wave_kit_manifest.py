from __future__ import annotations

from pathlib import Path

from synapse.marketing_os.wave_kit_manifest import (
    artifact_from_file,
    build_manifest,
    read_manifest,
    write_manifest,
)


def test_manifest_roundtrip_and_self_hash(tmp_path: Path) -> None:
    base = tmp_path
    f = base / "a.txt"
    f.write_text("hola", encoding="utf-8")

    art = artifact_from_file(f, base_dir=base)
    m = build_manifest(
        product_id="p1",
        schema_version="wk1",
        artifacts=[art],
        meta={"x": 1},
    )

    out = base / "manifest.json"
    write_manifest(out, m)

    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # no BOM

    loaded = read_manifest(out)
    assert loaded["product_id"] == "p1"
    assert loaded["schema_version"] == "wk1"
    assert loaded["self_hash"] == m["self_hash"]
    assert loaded["artifacts"][0]["relpath"] == "a.txt"
