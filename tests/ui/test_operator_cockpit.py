"""Behavioral tests for the A8-R74 operator cockpit (read-only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse.integration.a8_r70_smoke import SMOKE_SCHEMA_VERSION
from synapse.safety.spend_guard import GuardReasonCode
from synapse.ui import operator_cockpit as cockpit


class FakeSt:
    """Minimal Streamlit stand-in capturing rendered text. No side effects."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def _capture(self, *args: object, **kwargs: object) -> None:
        self.lines.append(" ".join(str(arg) for arg in args))

    title = _capture
    header = _capture
    subheader = _capture
    write = _capture
    caption = _capture
    warning = _capture
    success = _capture
    info = _capture
    error = _capture
    json = _capture
    dataframe = _capture

    def divider(self) -> None:
        self.lines.append("---")

    def set_page_config(self, **kwargs: object) -> None:
        self.lines.append("set_page_config")

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _snapshot_tree(root: Path) -> set[tuple[str, int]]:
    return {
        (str(path), path.stat().st_size)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_sandbox_banner_present_with_exact_text() -> None:
    view_model = cockpit.build_cockpit_view_model()
    banner = view_model["banner"]
    assert banner["text"] == "NO LIVE \u00b7 NO SPEND \u00b7 NO WRITES \u00b7 SANDBOX ONLY"
    assert view_model["schema_version"] == cockpit.COCKPIT_SCHEMA_VERSION


def test_guard_panels_present_with_canonical_decisions() -> None:
    view_model = cockpit.build_cockpit_view_model()
    trail = view_model["guard_trail"]

    assert trail["evaluation"]["decision"] == "ALLOW"
    assert trail["spend_probe"]["decision"] == "BLOCK"
    assert trail["mutation_probe"]["decision"] == "BLOCK"

    assert (
        GuardReasonCode.BLOCKED_SPEND_REQUIRES_AUTHORIZATION.value
        in trail["spend_probe"]["reason_codes"]
    )
    assert (
        GuardReasonCode.BLOCKED_EXTERNAL_MUTATION_REQUIRES_AUTHORIZATION.value
        in trail["mutation_probe"]["reason_codes"]
    )


def test_readiness_derives_from_existing_seams_not_parallel_logic() -> None:
    view_model = cockpit.build_cockpit_view_model()

    # Decision record must be the canonical A8-R70 record, not a re-derivation.
    record = view_model["decision_record"]
    assert record["schema_version"] == SMOKE_SCHEMA_VERSION
    assert view_model["smoke_schema_version"] == SMOKE_SCHEMA_VERSION

    # Checklist statuses must mirror the canonical guard trail decisions.
    checklist = {item["item"]: item["status"] for item in view_model["readiness_checklist"]}
    trail = view_model["guard_trail"]
    expected_spend = "OK" if trail["spend_probe"]["decision"] == "BLOCK" else "BLOCKED"
    expected_mutation = "OK" if trail["mutation_probe"]["decision"] == "BLOCK" else "BLOCKED"
    assert checklist["no_spend_confirmed"] == expected_spend
    assert checklist["no_writes_confirmed"] == expected_mutation
    assert checklist["shopify_read_only_dry_run"] == "PENDING"


def test_flags_panel_is_read_only_and_live_flags_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "SYNAPSE_META_LIVE",
        "SYNAPSE_SHOPIFY_LIVE",
        "SYNAPSE_DROPI_LIVE",
        "SYNAPSE_SPEND_REAL_MONEY",
        "SYNAPSE_LIVE_META",
        "SYNAPSE_LIVE_SHOPIFY",
        "SYNAPSE_LIVE_DROPI",
    ):
        monkeypatch.delenv(name, raising=False)

    view_model = cockpit.build_cockpit_view_model()
    flags = view_model["flags"]

    assert flags["read_only"] is True
    assert flags["mutable_from_ui"] is False
    if flags["status"] != cockpit.UNKNOWN:
        assert flags["status"] == "ALL_LIVE_FLAGS_OFF"
        assert all(value is False for value in flags["values"].values())


def test_ui_handles_missing_evidence_without_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    view_model = cockpit.build_cockpit_view_model(repo_root=tmp_path)

    assert view_model["evidence"]["status"] == cockpit.NOT_AVAILABLE
    assert view_model["overview"]["head"] == cockpit.UNKNOWN
    assert view_model["overview"]["last_run_dir"] == cockpit.NOT_AVAILABLE
    assert view_model["banner"]["text"]

    fake = FakeSt()
    cockpit.render_cockpit(fake, view_model)
    assert "NO LIVE" in fake.text


def test_no_writes_during_view_model_build_and_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / "marker.txt").write_text("before", encoding="utf-8")
    monkeypatch.chdir(workdir)

    before = _snapshot_tree(workdir)
    view_model = cockpit.build_cockpit_view_model(repo_root=workdir)
    cockpit.render_cockpit(FakeSt(), view_model)
    after = _snapshot_tree(workdir)

    assert before == after


def test_render_contains_all_required_panels() -> None:
    view_model = cockpit.build_cockpit_view_model()
    fake = FakeSt()
    cockpit.render_cockpit(fake, view_model)
    text = fake.text

    for fragment in (
        "NO LIVE",
        "Operator Overview",
        "Product / Candidate Detail",
        "Financial Evaluation",
        "Marketing Brief",
        "Decision Record",
        "Spend Guard / Mutation Guard",
        "Evidence / Ledger",
        "Safety Status / No-Go",
        "Readiness Checklist",
        "Approval Simulation",
    ):
        assert fragment in text, fragment


def test_approval_simulation_is_local_only_and_uses_canonical_guard() -> None:
    view_model = cockpit.build_cockpit_view_model()
    simulation = view_model["approval_simulation"]

    assert simulation["mode"] == "SIMULATION_LOCAL_ONLY"
    assert simulation["default_envelope"]["decision"] == "BLOCK"
    assert (
        GuardReasonCode.BLOCKED_SPEND_REQUIRES_AUTHORIZATION.value
        in simulation["default_envelope"]["reason_codes"]
    )
    assert simulation["hypothetical_authorized_envelope"]["decision"] == "ALLOW"
