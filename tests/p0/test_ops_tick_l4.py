# tests/p0/test_ops_tick_l4.py
"""L4 test suite for synapse.ops_tick — unit + hypothesis."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

import deal
import pytest
from hypothesis import given, settings, strategies as st

from synapse.ops_tick import (
    StepResult,
    TickConfig,
    main,
    _parse_tick_config,
    _compute_status,
    _readonly_checks,
    _execute_steps,
    _skip_step,
)


# ── Strategies ────────────────────────────────────────────

_BOOL = st.booleans()
_ARGV = st.lists(
    st.sampled_from(["--prune", "--no-import", "--readonly", "--write"]),
    max_size=4,
    unique=True,
)


# ── main ──────────────────────────────────────────────────

def test_main_unit_default_returns_int(tmp_path: Path) -> None:
    """main() with mocked subprocess returns 0 or 2."""
    fake = StepResult(cmd="fake", returncode=0, stdout_tail="", stderr_tail="")
    with patch("synapse.ops_tick._execute_steps", return_value=[fake]):
        with patch("synapse.ops_tick._persist_report"):
            result = main(["--no-import", "--readonly"])
    assert result in (0, 2)


@settings(max_examples=60, deadline=None)
@given(_ARGV)
def test_main_property_returns_0_or_2(argv: List[str]) -> None:
    fake = StepResult(cmd="fake", returncode=0, stdout_tail="", stderr_tail="")
    with patch("synapse.ops_tick._execute_steps", return_value=[fake]):
        with patch("synapse.ops_tick._persist_report"):
            result = main(argv)
    assert result in (0, 2)


def test_main_contract_rejects_non_list() -> None:
    with pytest.raises(deal.PreContractError):
        main("not a list")  # type: ignore[arg-type]


# ── _compute_status ───────────────────────────────────────

def test_compute_status_unit_all_ok() -> None:
    steps = [StepResult(cmd="a", returncode=0, stdout_tail="", stderr_tail="")]
    assert _compute_status(steps, {}) == "OK"


def test_compute_status_unit_fail_on_nonzero() -> None:
    steps = [StepResult(cmd="a", returncode=1, stdout_tail="", stderr_tail="")]
    assert _compute_status(steps, {}) == "FAIL"


def test_compute_status_unit_fail_on_invariant() -> None:
    steps = [StepResult(cmd="a", returncode=0, stdout_tail="", stderr_tail="")]
    assert _compute_status(steps, {"readonly_invariant_ok": False}) == "FAIL"


@settings(max_examples=80, deadline=None)
@given(st.lists(st.integers(min_value=0, max_value=2), min_size=1, max_size=7))
def test_compute_status_property_deterministic(codes: List[int]) -> None:
    steps = [StepResult(cmd=f"s{i}", returncode=c, stdout_tail="", stderr_tail="")
             for i, c in enumerate(codes)]
    result = _compute_status(steps, {})
    assert result in ("OK", "FAIL")
    if any(c != 0 for c in codes):
        assert result == "FAIL"


# ── _readonly_checks ──────────────────────────────────────

def test_readonly_checks_unit_no_ledger(tmp_path: Path) -> None:
    checks = _readonly_checks(tmp_path / "nope.jsonl", None, True)
    assert checks == {}


@settings(max_examples=50, deadline=None)
@given(_BOOL)
def test_readonly_checks_property_returns_dict(readonly: bool) -> None:
    checks = _readonly_checks(Path("/nonexistent/path"), None, readonly)
    assert isinstance(checks, dict)


# ── _skip_step ────────────────────────────────────────────

def test_skip_step_unit() -> None:
    s = _skip_step("test", "reason")
    assert s.returncode == 0
    assert "<SKIP>" in s.cmd


@settings(max_examples=50, deadline=None)
@given(st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=50))
def test_skip_step_property_always_zero(name: str, reason: str) -> None:
    s = _skip_step(name, reason)
    assert s.returncode == 0
    assert isinstance(s, StepResult)
