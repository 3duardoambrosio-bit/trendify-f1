"""Tests for synapse.cli.commands.status_cmd. S9: cockpit status command."""

from __future__ import annotations

import io
import subprocess
import sys
from unittest.mock import patch

import pytest


# ------------------------------------------------------------------
# Required keys that must appear exactly once in output
# ------------------------------------------------------------------
REQUIRED_KEYS = [
    "branch=",
    "head_short=",
    "dirty_lines=",
    "doctor_overall=",
    "feature_flags_count=",
    "flag_shopify_live=",
    "flag_meta_live_api=",
    "flag_dropi_live_orders=",
    "budget_learning_spent=",
    "budget_operational_spent=",
    "safety_killswitch=",
    "ledger_last_event_ts=",
    "ledger_last_event_type=",
    "exit_code=",
]


def _capture_status(**mock_patches) -> tuple[int, str]:
    """Run print_status() capturing stdout. Returns (exit_code, output)."""
    from synapse.cli.commands.status_cmd import print_status

    buf = io.StringIO()
    rc = print_status(stream=buf)
    return rc, buf.getvalue()


# ------------------------------------------------------------------
# 1) test_status_exits_zero
# ------------------------------------------------------------------
class TestStatusExitsZero:
    def test_exit_code_is_zero(self) -> None:
        rc, output = _capture_status()
        assert rc == 0
        assert "exit_code=0" in output


# ------------------------------------------------------------------
# 2) test_status_contains_required_keys
# ------------------------------------------------------------------
class TestStatusContainsRequiredKeys:
    def test_all_required_keys_present(self) -> None:
        _, output = _capture_status()
        lines = output.strip().splitlines()

        for key in REQUIRED_KEYS:
            matches = [ln for ln in lines if ln.startswith(key)]
            assert len(matches) == 1, (
                f"Expected exactly 1 line starting with '{key}', "
                f"found {len(matches)}: {matches}"
            )

    def test_header_present(self) -> None:
        _, output = _capture_status()
        assert "=== SYNAPSE COCKPIT STATUS ===" in output


# ------------------------------------------------------------------
# 3) test_status_handles_missing_data
# ------------------------------------------------------------------
class TestStatusHandlesMissingData:
    def test_missing_vault_and_empty_ledger(self) -> None:
        """When vault state file and ledger don't exist, prints unknown/none."""
        with patch(
            "synapse.cli.commands.status_cmd._budget_info",
            return_value={
                "learning_spent": "unknown",
                "operational_spent": "unknown",
            },
        ), patch(
            "synapse.cli.commands.status_cmd._ledger_last",
            return_value={"ts": "none", "type": "none"},
        ):
            rc, output = _capture_status()

        assert rc == 0
        assert "budget_learning_spent=unknown" in output
        assert "budget_operational_spent=unknown" in output
        assert "ledger_last_event_ts=none" in output
        assert "ledger_last_event_type=none" in output

    def test_all_subsystems_fail_gracefully(self) -> None:
        """When every subsystem raises, status still exits 0 with unknowns."""
        with patch(
            "synapse.cli.commands.status_cmd._git_branch",
            side_effect=Exception("git not found"),
        ), patch(
            "synapse.cli.commands.status_cmd._git_head_short",
            side_effect=Exception("git not found"),
        ), patch(
            "synapse.cli.commands.status_cmd._git_dirty_lines",
            side_effect=Exception("git not found"),
        ), patch(
            "synapse.cli.commands.status_cmd._doctor_overall",
            side_effect=Exception("doctor broken"),
        ), patch(
            "synapse.cli.commands.status_cmd._feature_flags_info",
            side_effect=Exception("flags broken"),
        ), patch(
            "synapse.cli.commands.status_cmd._budget_info",
            side_effect=Exception("vault broken"),
        ), patch(
            "synapse.cli.commands.status_cmd._safety_killswitch",
            side_effect=Exception("killswitch broken"),
        ), patch(
            "synapse.cli.commands.status_cmd._ledger_last",
            side_effect=Exception("ledger broken"),
        ):
            rc, output = _capture_status()

        assert rc == 0
        assert "branch=unknown" in output
        assert "head_short=unknown" in output
        assert "exit_code=0" in output


# ------------------------------------------------------------------
# 4) test_status_doctor_integration
# ------------------------------------------------------------------
class TestStatusDoctorIntegration:
    def test_doctor_green_in_output(self) -> None:
        """When doctor returns GREEN, output contains doctor_overall=GREEN."""
        with patch(
            "synapse.cli.commands.status_cmd._doctor_overall",
            return_value="GREEN",
        ):
            rc, output = _capture_status()

        assert rc == 0
        assert "doctor_overall=GREEN" in output

    def test_doctor_red_in_output(self) -> None:
        """When doctor returns RED, output reflects it without crashing."""
        with patch(
            "synapse.cli.commands.status_cmd._doctor_overall",
            return_value="RED",
        ):
            rc, output = _capture_status()

        assert rc == 0
        assert "doctor_overall=RED" in output


# ------------------------------------------------------------------
# 5) Subprocess entrypoint regression
# ------------------------------------------------------------------
class TestStatusEntrypoint:
    def test_module_entrypoint_exits_zero(self) -> None:
        """python -m synapse.cli.commands.status_cmd exits 0."""
        r = subprocess.run(
            [sys.executable, "-m", "synapse.cli.commands.status_cmd"],
            capture_output=True, text=True, timeout=60,
        )
        assert r.returncode == 0
        assert "=== SYNAPSE COCKPIT STATUS ===" in r.stdout
        assert "exit_code=0" in r.stdout
