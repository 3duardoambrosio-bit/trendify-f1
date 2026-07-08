from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

SAFE_CONTRACT_CASES = [{'test_id': 'A8R40_SAFE_001', 'runtime_file': 'synapse/shopify/cod_risk_scorer.py', 'symbol': '__init__', 'kind': 'function', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}, {'test_id': 'A8R40_SAFE_002', 'runtime_file': 'synapse/discovery/niche_selector.py', 'symbol': 'get_current', 'kind': 'function', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}, {'test_id': 'A8R40_SAFE_003', 'runtime_file': 'synapse/discovery/catalog_scanner.py', 'symbol': 'quick_scan', 'kind': 'function', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}, {'test_id': 'A8R40_SAFE_004', 'runtime_file': 'synapse/discovery/product_ranker.py', 'symbol': 'rank', 'kind': 'function', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}, {'test_id': 'A8R40_SAFE_005', 'runtime_file': 'synapse/discovery/niche_selector.py', 'symbol': 'CompetitionLevel', 'kind': 'class', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}, {'test_id': 'A8R40_SAFE_006', 'runtime_file': 'synapse/discovery/niche_selector.py', 'symbol': 'NicheCategory', 'kind': 'class', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}, {'test_id': 'A8R40_SAFE_007', 'runtime_file': 'synapse/discovery/niche_selector.py', 'symbol': 'NicheRisk', 'kind': 'class', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}, {'test_id': 'A8R40_SAFE_008', 'runtime_file': 'synapse/discovery/niche_selector.py', 'symbol': 'list_niches', 'kind': 'function', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}, {'test_id': 'A8R40_SAFE_009', 'runtime_file': 'synapse/product_evaluator.py', 'symbol': 'QualityResult', 'kind': 'class', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}, {'test_id': 'A8R40_SAFE_010', 'runtime_file': 'synapse/shopify/cod_risk_scorer.py', 'symbol': 'CodRiskConfig', 'kind': 'class', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}, {'test_id': 'A8R40_SAFE_011', 'runtime_file': 'tools/product_decision_engine.py', 'symbol': 'ProductCandidate', 'kind': 'class', 'target_test_file': 'tests/meta/test_a8_r40_product_selection_safe_contracts.py', 'recommended_action': 'QUEUE_TARGETED_CONTRACT_TEST', 'mutation_allowed': 0, 'runtime_patch_allowed': 0}]

EXPECTED_SAFE_CASE_COUNT = 11


def _runtime_text(case: dict[str, object]) -> str:
    path = REPO_ROOT / str(case["runtime_file"])
    assert path.exists(), f"runtime file missing: {path}"
    return path.read_text(encoding="utf-8")


def test_a8_r40_safe_contract_queue_shape() -> None:
    assert len(SAFE_CONTRACT_CASES) == EXPECTED_SAFE_CASE_COUNT

    ids = [case["test_id"] for case in SAFE_CONTRACT_CASES]
    assert len(ids) == len(set(ids))
    assert all(str(test_id).startswith("A8R40_SAFE_") for test_id in ids)

    assert all(case["mutation_allowed"] == 0 for case in SAFE_CONTRACT_CASES)
    assert all(case["runtime_patch_allowed"] == 0 for case in SAFE_CONTRACT_CASES)


@pytest.mark.parametrize("case", SAFE_CONTRACT_CASES, ids=lambda case: case["test_id"])
def test_a8_r40_safe_contract_runtime_symbol_is_present(case: dict[str, object]) -> None:
    text = _runtime_text(case)
    assert str(case["symbol"]) in text


@pytest.mark.parametrize("case", SAFE_CONTRACT_CASES, ids=lambda case: case["test_id"])
def test_a8_r40_safe_contract_case_is_test_only(case: dict[str, object]) -> None:
    assert case["mutation_allowed"] == 0
    assert case["runtime_patch_allowed"] == 0
    assert str(case["target_test_file"]).endswith("test_a8_r40_product_selection_safe_contracts.py")
    assert str(case["kind"]) in {"class", "function"}
