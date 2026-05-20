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
            "Mini cÃƒÆ’Ã‚Â¡mara WiFi",
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
            "tranquilidad visual para casa sin instalaciÃƒÆ’Ã‚Â³n complicada",
            "--primary-hook",
            "Ãƒâ€šÃ‚Â¿Sales de casa y no sabes quÃƒÆ’Ã‚Â© estÃƒÆ’Ã‚Â¡ pasando?",
            "--target-audience",
            "personas que quieren vigilar casa o negocio pequeÃƒÆ’Ã‚Â±o",
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


def test_a8_r54_blocks_generic_factory_leak_phrases(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli",
            "simulate",
            "--evidence-root",
            str(tmp_path),
            "--product",
            "Mini cÃƒÆ’Ã‚Â¡mara WiFi",
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
            "tranquilidad visual para casa sin instalaciÃƒÆ’Ã‚Â³n complicada",
            "--primary-hook",
            "Ãƒâ€šÃ‚Â¿Sales de casa y no sabes quÃƒÆ’Ã‚Â© estÃƒÆ’Ã‚Â¡ pasando?",
            "--target-audience",
            "personas que quieren vigilar casa o negocio pequeÃƒÆ’Ã‚Â±o",
            "--use-case",
            "revisar visualmente un espacio desde el celular",
        ],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout_lower = result.stdout.lower()

    banned_fragments = [
        "dile adiÃƒÆ’Ã‚Â³s",
        "dile adios",
        "lo que usan los que saben",
        "los que saben",
        "realmente funciona",
        "desorden y la incomodidad",
    ]

    for fragment in banned_fragments:
        assert fragment not in stdout_lower

    evidence_match = re.search(r"^EVIDENCE_DIR=(.+)$", result.stdout, flags=re.MULTILINE)
    assert evidence_match is not None
    evidence_dir = Path(evidence_match.group(1).strip())

    creative_pack = json.loads((evidence_dir / "creative_pack.json").read_text(encoding="utf-8"))
    hooks = "\\n".join(creative_pack["hook_variants"]).lower()

    for fragment in banned_fragments:
        assert fragment not in hooks

    assert creative_pack["creative_integrity"]["generic_phrase_count"] == 0
    assert creative_pack["creative_integrity"]["passed"] is True


def test_a8_r54f_lists_presets(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "simulate", "--list-presets"],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = result.stdout

    assert "SYNAPSE SIMULATION PRESETS" in stdout
    assert "PRESET_COUNT=3" in stdout
    assert "PRESET::home_security_wifi" in stdout
    assert "PRESET::car_cleaning_demo" in stdout
    assert "PRESET::pet_hair_clothes" in stdout


def test_a8_r54f_runs_preset_and_allows_override(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli",
            "simulate",
            "--preset",
            "pet_hair_clothes",
            "--evidence-root",
            str(tmp_path),
            "--price",
            "279",
            "--traffic",
            "1500",
        ],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = result.stdout

    assert "PRODUCT=Removedor de pelusa reutilizable" in stdout
    assert "PRICE_MXN=279" in stdout
    assert "TRAFFIC=1500" in stdout
    assert "FINAL_OUTCOME=TEST_SMALL_BUDGET_SANDBOX" in stdout
    assert "GENERIC_PHRASE_COUNT=0" in stdout
    assert "CREATIVE_INTEGRITY_PASS=1" in stdout
    assert "EXTERNAL_MUTATION=0" in stdout
    assert "SPEND_COUNT=0" in stdout

def test_a8_r54h_primary_hook_generic_phrase_is_gated(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli",
            "simulate",
            "--preset",
            "pet_hair_clothes",
            "--evidence-root",
            str(tmp_path),
            "--primary-hook",
            "el mejor producto, compra ahora, no te lo pierdas",
        ],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "PRIMARY_HOOK=el mejor producto, compra ahora, no te lo pierdas" in result.stdout
    assert "CREATIVE_INTEGRITY_PASS=0" in result.stdout

    evidence_match = re.search(r"^EVIDENCE_DIR=(.+)$", result.stdout, flags=re.MULTILINE)
    assert evidence_match is not None
    evidence_dir = Path(evidence_match.group(1).strip())

    creative_pack = json.loads((evidence_dir / "creative_pack.json").read_text(encoding="utf-8"))
    integrity = creative_pack["creative_integrity"]

    assert integrity["passed"] is False
    assert integrity["generic_phrase_count"] >= 1
    assert any("generic" in reason for reason in integrity.get("failed_reasons", []))


def test_a8_r54h_primary_hook_specific_phrase_still_passes(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli",
            "simulate",
            "--preset",
            "pet_hair_clothes",
            "--evidence-root",
            str(tmp_path),
            "--primary-hook",
            "Muestra una playera negra con pelo de mascota y una pasada real.",
        ],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "PRIMARY_HOOK=Muestra una playera negra con pelo de mascota y una pasada real." in result.stdout
    assert "GENERIC_PHRASE_COUNT=0" in result.stdout
    assert "CREATIVE_INTEGRITY_PASS=1" in result.stdout

    evidence_match = re.search(r"^EVIDENCE_DIR=(.+)$", result.stdout, flags=re.MULTILINE)
    assert evidence_match is not None
    evidence_dir = Path(evidence_match.group(1).strip())

    creative_pack = json.loads((evidence_dir / "creative_pack.json").read_text(encoding="utf-8"))
    integrity = creative_pack["creative_integrity"]

    assert integrity["passed"] is True
    assert integrity["generic_phrase_count"] == 0
