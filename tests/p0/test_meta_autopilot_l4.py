# tests/p0/test_meta_autopilot_l4.py
"""L4 test suite for synapse.meta_autopilot — unit + hypothesis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import deal
import pytest
from hypothesis import given, settings, strategies as st

from synapse.meta_autopilot import (
    Action,
    AutopilotConfig,
    ReportContext,
    main,
    _build_context,
    _build_output,
    _generate_actions_fail,
    _generate_actions_ok,
    _risk_color,
)


# ── Strategies ────────────────────────────────────────────

_STATUS = st.sampled_from(["OK", "WARN", "FAIL", "UNKNOWN"])
_REPORT = st.fixed_dictionaries({
    "status": _STATUS,
    "reason": st.text(min_size=0, max_size=30),
    "mode": st.sampled_from(["simulate", "live"]),
})
_INDEX = st.fixed_dictionaries({
    "runs": st.lists(
        st.fixed_dictionaries({"ts": st.text(min_size=5, max_size=30)}),
        max_size=5,
    ),
})


# ── main ──────────────────────────────────────────────────

def test_main_unit_with_empty_files(tmp_path: Path) -> None:
    report_f = tmp_path / "report.json"
    index_f = tmp_path / "index.json"
    report_f.write_text("{}", encoding="utf-8")
    index_f.write_text("{}", encoding="utf-8")
    out_json = tmp_path / "out.json"
    out_txt = tmp_path / "out.txt"

    with patch("synapse.meta_autopilot.cli_print"):
        result = main([
            "--report", str(report_f),
            "--index", str(index_f),
            "--out-json", str(out_json),
            "--out-txt", str(out_txt),
        ])
    assert result == 0
    assert out_json.exists()
    assert out_txt.exists()


@settings(max_examples=60, deadline=None)
@given(_REPORT, _INDEX)
def test_main_property_always_returns_0(
    report_data: Dict[str, Any],
    index_data: Dict[str, Any],
) -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        rf = p / "r.json"
        xf = p / "x.json"
        rf.write_text(json.dumps(report_data), encoding="utf-8")
        xf.write_text(json.dumps(index_data), encoding="utf-8")
        with patch("synapse.meta_autopilot.cli_print"):
            result = main([
                "--report", str(rf),
                "--index", str(xf),
                "--out-json", str(p / "o.json"),
                "--out-txt", str(p / "o.txt"),
            ])
        assert result == 0


def test_main_contract_rejects_non_list() -> None:
    with pytest.raises(deal.PreContractError):
        main("bad")  # type: ignore[arg-type]


# ── _build_context ────────────────────────────────────────

def test_build_context_unit_empty() -> None:
    ctx = _build_context({}, {})
    assert isinstance(ctx, ReportContext)
    assert ctx.runs_indexed == 0


@settings(max_examples=80, deadline=None)
@given(_REPORT, _INDEX)
def test_build_context_property_returns_context(
    report: Dict[str, Any],
    index: Dict[str, Any],
) -> None:
    ctx = _build_context(report, index)
    assert isinstance(ctx, ReportContext)
    assert ctx.runs_indexed >= 0


# ── _generate_actions_fail ────────────────────────────────

def test_generate_actions_fail_unit() -> None:
    ctx = ReportContext(
        mode="simulate", report_status="FAIL", report_reason="broken",
        fp12="", files_sha12="", missing_files=0, runs_indexed=0, last_run_ts="",
    )
    actions = _generate_actions_fail(ctx)
    assert len(actions) == 1
    assert actions[0].priority == 0


@settings(max_examples=50, deadline=None)
@given(st.text(min_size=1, max_size=50))
def test_generate_actions_fail_property_always_p0(reason: str) -> None:
    ctx = ReportContext(
        mode="simulate", report_status="FAIL", report_reason=reason,
        fp12="", files_sha12="", missing_files=0, runs_indexed=0, last_run_ts="",
    )
    actions = _generate_actions_fail(ctx)
    assert all(a.priority == 0 for a in actions)


# ── _generate_actions_ok ──────────────────────────────────

def test_generate_actions_ok_unit_with_missing_files() -> None:
    ctx = ReportContext(
        mode="simulate", report_status="OK", report_reason="-",
        fp12="", files_sha12="", missing_files=3, runs_indexed=0, last_run_ts="",
    )
    actions = _generate_actions_ok(ctx, {"runs": []})
    priorities = [a.priority for a in actions]
    assert 1 in priorities  # missing files action


@settings(max_examples=60, deadline=None)
@given(st.integers(min_value=0, max_value=10))
def test_generate_actions_ok_property_always_has_p3_p4(missing: int) -> None:
    ctx = ReportContext(
        mode="simulate", report_status="OK", report_reason="-",
        fp12="", files_sha12="", missing_files=missing, runs_indexed=0, last_run_ts="",
    )
    actions = _generate_actions_ok(ctx, {"runs": []})
    priorities = [a.priority for a in actions]
    assert 3 in priorities
    assert 4 in priorities


# ── _risk_color ───────────────────────────────────────────

def test_risk_color_unit() -> None:
    assert _risk_color("OK") == "GREEN"
    assert _risk_color("WARN") == "YELLOW"
    assert _risk_color("FAIL") == "RED"
    assert _risk_color("other") == "RED"


@settings(max_examples=50, deadline=None)
@given(st.text(min_size=0, max_size=20))
def test_risk_color_property_returns_valid(status: str) -> None:
    result = _risk_color(status)
    assert result in ("GREEN", "YELLOW", "RED")


# ── _build_output ─────────────────────────────────────────

def test_build_output_unit() -> None:
    ctx = ReportContext(
        mode="simulate", report_status="OK", report_reason="-",
        fp12="abc", files_sha12="def", missing_files=0, runs_indexed=1, last_run_ts="t",
    )
    actions = [Action(priority=3, title="test", why="because", cmd="echo")]
    out = _build_output(ctx, actions, {"ts": "now"})
    assert out["health"] == "GREEN"
    assert len(out["next_actions"]) == 1


@settings(max_examples=50, deadline=None)
@given(_STATUS)
def test_build_output_property_has_health(status: str) -> None:
    ctx = ReportContext(
        mode="sim", report_status=status, report_reason="r",
        fp12="", files_sha12="", missing_files=0, runs_indexed=0, last_run_ts="",
    )
    out = _build_output(ctx, [], {"ts": ""})
    assert out["health"] in ("GREEN", "YELLOW", "RED")
