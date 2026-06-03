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


def test_build_run_inventory_status_complete_8_of_8() -> None:
    status = read_model.build_run_inventory_status(8)

    assert status["observed_count"] == 8
    assert status["expected_count"] == 8
    assert status["displayed_count"] == 8
    assert status["hidden_count"] == 0
    assert status["missing_count"] == 0
    assert status["inventory_label"] == "8/8"
    assert status["state"] == "complete"
    assert status["should_warn"] is False


def test_build_run_inventory_status_empty_warns() -> None:
    status = read_model.build_run_inventory_status(0)

    assert status["observed_count"] == 0
    assert status["expected_count"] == 8
    assert status["displayed_count"] == 0
    assert status["hidden_count"] == 0
    assert status["missing_count"] == 8
    assert status["inventory_label"] == "0/8"
    assert status["state"] == "empty"
    assert status["should_warn"] is True


def test_build_run_inventory_status_partial_warns() -> None:
    status = read_model.build_run_inventory_status(5)

    assert status["observed_count"] == 5
    assert status["expected_count"] == 8
    assert status["displayed_count"] == 5
    assert status["hidden_count"] == 0
    assert status["missing_count"] == 3
    assert status["inventory_label"] == "5/8"
    assert status["state"] == "partial"
    assert status["should_warn"] is True


def test_build_run_inventory_status_overflow_warns_and_caps_display() -> None:
    status = read_model.build_run_inventory_status(9)

    assert status["observed_count"] == 9
    assert status["expected_count"] == 8
    assert status["displayed_count"] == 8
    assert status["hidden_count"] == 1
    assert status["missing_count"] == 0
    assert status["inventory_label"] == "8/8"
    assert status["state"] == "overflow"
    assert status["should_warn"] is True


def test_build_run_inventory_status_rejects_negative_run_count() -> None:
    try:
        read_model.build_run_inventory_status(-1)
    except ValueError as exc:
        assert "run_count" in str(exc)
    else:
        raise AssertionError("Expected ValueError for negative run_count")


def test_build_run_inventory_status_rejects_negative_expected_count() -> None:
    try:
        read_model.build_run_inventory_status(1, expected_count=-1)
    except ValueError as exc:
        assert "expected_count" in str(exc)
    else:
        raise AssertionError("Expected ValueError for negative expected_count")
