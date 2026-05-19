from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def test_visible_single_scenario_simulation_direct_module_contract(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli.simulate",
            "--evidence-root",
            str(tmp_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr

    stdout = result.stdout
    required_tokens = [
        "SYNAPSE SIMULATION",
        "SCENARIO_ID=",
        "DECISION_ID=",
        "LIVE_MODE=0",
        "STEP_01_INPUT",
        "STEP_02_SIGNALS",
        "STEP_03_SCORE_OR_POLICY",
        "STEP_04_PERMISSION_GATE",
        "STEP_05_DECISION",
        "STEP_06_LEDGER_EVENT",
        "STEP_07_EVIDENCE",
        "STEP_08_LIVE_FLAGS",
        "STEP_09_MUTATION_COUNTS",
        "FINAL_OUTCOME=",
        "EVIDENCE_DIR=",
        "EXTERNAL_MUTATION=0",
        "SPEND_COUNT=0",
        "SHOPIFY_WRITE_COUNT=0",
        "META_WRITE_COUNT=0",
        "DROPI_WRITE_COUNT=0",
        "flag_shopify_live=0",
        "flag_meta_live_api=0",
        "flag_dropi_live_orders=0",
    ]
    for token in required_tokens:
        assert token in stdout

    step_count = len(re.findall(r"^STEP_\d+_", stdout, flags=re.MULTILINE))
    assert step_count >= 7

    evidence_match = re.search(r"^EVIDENCE_DIR=(.+)$", stdout, flags=re.MULTILINE)
    assert evidence_match is not None

    evidence_dir = Path(evidence_match.group(1).strip())
    assert evidence_dir.exists()
    assert evidence_dir.is_dir()

    ledger_path = evidence_dir / "ledger_sandbox.ndjson"
    idempotency_path = evidence_dir / "idempotency_sandbox.json"
    scenario_path = evidence_dir / "scenario.json"
    safety_path = evidence_dir / "safety_posture.json"
    decision_path = evidence_dir / "decision.json"

    assert ledger_path.exists()
    assert idempotency_path.exists()
    assert scenario_path.exists()
    assert safety_path.exists()
    assert decision_path.exists()

    ledger_lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger_lines) >= 1

    ledger_event = json.loads(ledger_lines[0])
    assert ledger_event["scenario_id"] == "A8-R53-VISIBLE-SINGLE-SCENARIO-001"
    assert ledger_event["external_mutation"] == 0
    assert ledger_event["spend_count"] == 0
    assert ledger_event["shopify_write_count"] == 0
    assert ledger_event["meta_write_count"] == 0
    assert ledger_event["dropi_write_count"] == 0
    assert ledger_event["live_mode"] == 0

    idem = json.loads(idempotency_path.read_text(encoding="utf-8"))
    assert idem["sandbox_only"] is True
    assert idem["scenario_id"] == "A8-R53-VISIBLE-SINGLE-SCENARIO-001"
    assert idem["decision_id"].startswith("dec_")


def test_synapse_cli_dispatcher_simulate_if_available(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli",
            "simulate",
            "--evidence-root",
            str(tmp_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0 and (
        "No module named synapse.cli.__main__" in result.stderr
        or "is a package and cannot be directly executed" in result.stderr
    ):
        return

    assert result.returncode == 0, result.stderr
    assert "SYNAPSE SIMULATION" in result.stdout
    assert "FINAL_OUTCOME=" in result.stdout
    assert "EXTERNAL_MUTATION=0" in result.stdout