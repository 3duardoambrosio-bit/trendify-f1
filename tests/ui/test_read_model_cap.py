from __future__ import annotations

import json
from pathlib import Path

from synapse.ui import read_model


REQUIRED_FILES = (
    "scenario.json",
    "decision.json",
    "safety_posture.json",
    "creative_pack.json",
    "ledger_sandbox.ndjson",
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_complete_run(root: Path, index: int) -> Path:
    run_dir = root / f"KC{index:02d}_producto_{index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "scenario.json", {"product_name": f"Producto temporal {index}"})
    _write_json(run_dir / "decision.json", {"score": 0.75, "threshold": 0.60, "final_outcome": "PASS"})
    _write_json(run_dir / "safety_posture.json", {"runtime_mode": "sandbox", "live_reads": 0, "live_writes": 0})
    _write_json(run_dir / "creative_pack.json", {"hooks": [f"Hook temporal {index}"], "angles": ["observability"]})

    (run_dir / "ledger_sandbox.ndjson").write_text(
        json.dumps({"event": "created", "index": index}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "ledger.ndjson").write_text(
        json.dumps({"event": "created", "index": index}) + "\n",
        encoding="utf-8",
    )

    for file_name in REQUIRED_FILES:
        assert (run_dir / file_name).exists(), file_name

    return run_dir


def test_max_run_dirs_constant_is_8() -> None:
    assert read_model.MAX_RUN_DIRS_DISPLAYED == 8


def test_discover_run_dirs_respects_max_constant(tmp_path: Path) -> None:
    for index in range(1, read_model.MAX_RUN_DIRS_DISPLAYED + 4):
        _make_complete_run(tmp_path, index)

    discovered = read_model.discover_run_dirs(tmp_path)

    assert len(discovered) == read_model.MAX_RUN_DIRS_DISPLAYED
    assert all(path.is_dir() for path in discovered)


def test_discover_run_dirs_returns_all_when_below_max(tmp_path: Path) -> None:
    for index in range(1, 4):
        _make_complete_run(tmp_path, index)

    discovered = read_model.discover_run_dirs(tmp_path)

    assert len(discovered) == 3
    assert all(path.is_dir() for path in discovered)
