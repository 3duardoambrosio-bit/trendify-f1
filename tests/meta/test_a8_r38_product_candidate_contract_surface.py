"""A8-R38 product candidate contract surface guards.

These tests intentionally protect the existing contract surface first.
They do not change product-selection behavior.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


CONTRACT_FILES = {
    "core_orchestrator": "synapse/core/orchestrator.py",
    "pipeline_orchestrator": "synapse/discovery/pipeline_orchestrator.py",
    "cli_contract_test": "tests/ops/test_a8_r35_product_candidate_pipeline_cli_contract.py",
    "closed_loop_probe": "tests/core/capa_b_closed_loop_probe.py",
    "golden_fixture_doc": "docs/audit/A8_R36_PRODUCT_CANDIDATE_PIPELINE_GOLDEN_FIXTURES.md",
}


SURFACE_TERMS = (
    "product_candidate",
    "candidate",
    "pipeline",
    "json",
)


CONTRACT_MARKERS = (
    "golden",
    "fixture",
    "expected",
    "snapshot",
)


def _contract_path(label: str) -> Path:
    relative_path = CONTRACT_FILES[label]
    return ROOT / relative_path


def _read_contract_file(label: str) -> str:
    path = _contract_path(label)
    assert path.is_file(), f"missing contract file: {CONTRACT_FILES[label]}"
    return path.read_text(encoding="utf-8")


def _combined_contract_surface() -> str:
    return "\n".join(_read_contract_file(label) for label in CONTRACT_FILES).lower()


def test_product_candidate_contract_files_exist() -> None:
    missing = [
        relative_path
        for relative_path in CONTRACT_FILES.values()
        if not (ROOT / relative_path).is_file()
    ]

    assert missing == []


def test_product_candidate_contract_terms_are_present() -> None:
    surface = _combined_contract_surface()

    missing_terms = [
        term
        for term in SURFACE_TERMS
        if term.lower() not in surface
    ]

    assert missing_terms == []


def test_product_candidate_cli_contract_keeps_json_and_assertion_surface() -> None:
    cli_text = _read_contract_file("cli_contract_test").lower()
    surface = _combined_contract_surface()

    assert "product_candidate" in cli_text
    assert "json" in surface
    assert re.search(r"\bassert\b", cli_text) is not None
    assert any(marker in surface for marker in CONTRACT_MARKERS)


def test_product_candidate_contract_surface_has_no_fixme_or_hack_markers() -> None:
    offenders: list[str] = []

    for label, relative_path in CONTRACT_FILES.items():
        text = _read_contract_file(label)

        if re.search(r"\b(FIXME|HACK)\b", text):
            offenders.append(relative_path)

    assert offenders == []
