from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def test_a8_r54_manipulable_simulation_user_inputs(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli",
            "simulate",
            "--evidence-root",
            str(tmp_path),
            "--product",
            "Mini cámara WiFi",
            "--category",
            "home_security",
            "--price",
            "599",
            "--cost",
            "180",
            "--traffic",
            "900",
            "--days",
            "3",
            "--marketing-angle",
            "tranquilidad visual para casa sin instalación complicada",
            "--primary-hook",
            "¿Sales de casa y no sabes qué está pasando?",
            "--target-audience",
            "personas que quieren vigilar casa o negocio pequeño",
            "--use-case",
            "revisar visualmente un espacio desde el celular",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = result.stdout

    required_tokens = [
        "SYNAPSE SIMULATION",
        "SIMULATION_VERSION=a8-r54-manipulable-v1",
        "SCENARIO_ID=A8-R54-MANIPULABLE",
        "STEP_10_CREATIVE_DIRECTION",
        "STEP_11_HOOK_VARIANTS",
        "STEP_12_CREATIVE_BRIEF",
        "STEP_13_CREATIVE_INTEGRITY",
        "HOOK_VARIANTS_COUNT=",
        "GENERIC_PHRASE_COUNT=0",
        "CLAIM_SAFETY=PASS",
        "EXTERNAL_MUTATION=0",
        "SPEND_COUNT=0",
        "SHOPIFY_WRITE_COUNT=0",
        "META_WRITE_COUNT=0",
        "DROPI_WRITE_COUNT=0",
    ]
    for token in required_tokens:
        assert token in stdout

    hooks_match = re.search(r"^HOOK_VARIANTS_COUNT=(\d+)$", stdout, flags=re.MULTILINE)
    assert hooks_match is not None
    assert int(hooks_match.group(1)) >= 5

    uniqueness_match = re.search(r"^HOOK_UNIQUENESS_SCORE=([0-9.]+)$", stdout, flags=re.MULTILINE)
    assert uniqueness_match is not None
    assert float(uniqueness_match.group(1)) >= 0.70

    evidence_match = re.search(r"^EVIDENCE_DIR=(.+)$", stdout, flags=re.MULTILINE)
    assert evidence_match is not None
    evidence_dir = Path(evidence_match.group(1).strip())
    assert evidence_dir.exists()

    creative_pack = json.loads((evidence_dir / "creative_pack.json").read_text(encoding="utf-8"))
    assert creative_pack["creative_integrity"]["generic_phrase_count"] == 0
    assert creative_pack["creative_integrity"]["hook_uniqueness_score"] >= 0.70
    assert creative_pack["creative_integrity"]["claim_safety"] == "PASS"

    ledger_lines = (evidence_dir / "ledger_sandbox.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger_lines) >= 1
    ledger_event = json.loads(ledger_lines[0])
    assert ledger_event["external_mutation"] == 0
    assert ledger_event["spend_count"] == 0
    assert ledger_event["shopify_write_count"] == 0
    assert ledger_event["meta_write_count"] == 0
    assert ledger_event["dropi_write_count"] == 0
    assert ledger_event["sandbox_only"] is True
    assert "governed_anchor" in ledger_event


def test_a8_r54_known_cases_contract(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli",
            "simulate",
            "--known-cases",
            "--evidence-root",
            str(tmp_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = result.stdout

    assert "KNOWN_CASES_TOTAL=8" in stdout
    assert "KNOWN_CASES_PASS=8" in stdout
    assert "KNOWN_CASES_FAIL=0" in stdout
    assert "FINAL_OUTCOME=KNOWN_CASES_PASS" in stdout
    assert "EXTERNAL_MUTATION=0" in stdout
    assert "SPEND_COUNT=0" in stdout
    assert "SHOPIFY_WRITE_COUNT=0" in stdout
    assert "META_WRITE_COUNT=0" in stdout
    assert "DROPI_WRITE_COUNT=0" in stdout

    evidence_match = re.search(r"^EVIDENCE_DIR=(.+)$", stdout, flags=re.MULTILINE)
    assert evidence_match is not None
    evidence_dir = Path(evidence_match.group(1).strip())

    known_cases = json.loads((evidence_dir / "known_cases.json").read_text(encoding="utf-8"))
    assert known_cases["total"] == 8
    assert known_cases["passed"] >= 6
    assert all(case["passed"] == 1 for case in known_cases["cases"])
