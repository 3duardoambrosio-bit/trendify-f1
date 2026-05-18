from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_offline_e2e_gate.ps1"
DOC = ROOT / "docs" / "ops" / "A8_R52_OFFLINE_E2E_HARDENING_GATE.md"


def test_a8_r52_offline_e2e_gate_contract_files_exist() -> None:
    assert TOOL.exists()
    assert DOC.exists()


def test_a8_r52_offline_e2e_gate_has_required_markers() -> None:
    text = TOOL.read_text(encoding="utf-8")
    required = [
        "A8-R52 OFFLINE E2E HARDENING GATE",
        "scripts\\run_burnin_mock.py",
        "SUMMARY_DISPATCH_COUNT",
        "SUMMARY_LEDGER_EVENT_COUNT",
        "SUMMARY_PRE_SPEND_GATE_BLOCKED_COUNT",
        "flag_shopify_live=0",
        "flag_meta_live_api=0",
        "flag_dropi_live_orders=0",
        "A8_R52_OFFLINE_E2E_GATE_PASS=1",
        "NO_EXTERNAL_MUTATION=1",
        "NO_SHOPIFY_MUTATION=1",
        "NO_META_MUTATION=1",
        "NO_DROPI_MUTATION=1",
        "AllowDirtyRepo",
    ]
    for marker in required:
        assert marker in text


def test_a8_r52_offline_e2e_gate_doc_has_canonical_command_and_gates() -> None:
    text = DOC.read_text(encoding="utf-8")
    required = [
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/run_offline_e2e_gate.ps1 -Cycles 25",
        "dispatch_count",
        "ledger_event_count",
        "pre_spend_gate_blocked",
        "doctor_overall",
        "repo status after gate",
        "A8_R52_OFFLINE_E2E_GATE_PASS=1",
    ]
    for marker in required:
        assert marker in text
