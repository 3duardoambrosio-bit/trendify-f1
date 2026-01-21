from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cli_snapshot_writes_file_no_bom(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hola", encoding="utf-8")

    out = tmp_path / "snap.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli",
            "snapshot",
            "--paths",
            str(f),
            "--out",
            str(out),
            "--no-timestamp",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "v1"
    assert "hashes" in payload and payload["hashes"]
    assert "self_hash" in payload and isinstance(payload["self_hash"], str)
