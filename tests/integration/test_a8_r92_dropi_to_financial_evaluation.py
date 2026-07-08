from __future__ import annotations

import ast
import copy
from dataclasses import fields
from decimal import Decimal
from pathlib import Path

import pytest

from synapse.financial import FinancialInput, FinancialResult
from synapse.integration.dropi_fixture_readonly import (
    DropiFixtureValidationError,
    dropi_product_to_financial_candidate,
    load_dropi_fixture,
)
from synapse.integration.dropi_to_financial_evaluation import (
    DropiFinancialBridgeError,
    dropi_candidate_to_financial_input,
    evaluate_dropi_candidate_financials,
)


FIXTURE_PATH = Path("tests/fixtures/dropi_supplier_products_nominal.json")
SOURCE_PATH = Path("synapse/integration/dropi_to_financial_evaluation.py")


def _payload():
    return load_dropi_fixture(FIXTURE_PATH)


def _first_candidate():
    payload = _payload()
    return dropi_product_to_financial_candidate(payload["products"][0], payload["supplier"])


def test_a8_r92_dropi_candidate_maps_to_existing_financial_input_contract():
    candidate = _first_candidate()

    financial_input = dropi_candidate_to_financial_input(
        candidate,
        price=Decimal("499.00"),
        estimated_cac=Decimal("80.00"),
        expected_units=7,
    )

    assert isinstance(financial_input, FinancialInput)
    assert financial_input.price == Decimal("499.00")
    assert financial_input.landed_cost == Decimal("250.00")
    assert financial_input.estimated_cac == Decimal("80.00")

    field_names = {field.name for field in fields(FinancialInput)}
    if "candidate_id" in field_names:
        assert financial_input.candidate_id == "dropi_fixture_product_001"
    if "product_id" in field_names:
        assert financial_input.product_id == "dropi_fixture_product_001"
    if "title" in field_names:
        assert financial_input.title == candidate["title"]
    if "category" in field_names:
        assert financial_input.category == candidate["category"]
    if "expected_units" in field_names:
        assert financial_input.expected_units == 7


def test_a8_r92_dropi_bridge_evaluates_candidate_without_side_effects():
    payload = _payload()

    bridge = evaluate_dropi_candidate_financials(
        payload["products"][0],
        payload["supplier"],
        price="499.00",
        estimated_cac="80.00",
        expected_units=7,
    )

    assert bridge["read_only"] is True
    assert bridge["external_side_effects"] is False
    assert bridge["source"] == "dropi_fixture"
    assert bridge["target"] == "synapse.financial.evaluation.FinancialInput"
    assert bridge["operator_review_required"] is True
    assert bridge["boundaries"] == {
        "live_dropi": False,
        "external_writes": False,
        "spend": False,
        "fulfillment_automation": False,
        "order_placement": False,
        "inventory_reservation": False,
    }
    assert isinstance(bridge["financial_input"], FinancialInput)
    assert isinstance(bridge["financial_result"], FinancialResult)
    assert bridge["candidate"]["safety"]["external_side_effects"] is False
    assert bridge["candidate"]["inventory"]["inventory_reservation"] is False


@pytest.mark.parametrize(
    ("flag", "error"),
    [
        ("live_dropi", "candidate.safety.live_dropi must be false"),
        ("external_writes", "candidate.safety.external_writes must be false"),
        ("spend", "candidate.safety.spend must be false"),
        ("fulfillment_automation", "candidate.safety.fulfillment_automation must be false"),
        ("order_placement", "candidate.safety.order_placement must be false"),
        ("inventory_reservation", "candidate.safety.inventory_reservation must be false"),
    ],
)
def test_a8_r92_dropi_financial_input_rejects_unsafe_candidate_flags(flag, error):
    candidate = copy.deepcopy(_first_candidate())
    candidate["safety"][flag] = True

    with pytest.raises(DropiFinancialBridgeError, match=error):
        dropi_candidate_to_financial_input(
            candidate,
            price="499.00",
            estimated_cac="80.00",
            expected_units=7,
        )


def test_a8_r92_dropi_financial_input_rejects_non_fixture_source():
    candidate = copy.deepcopy(_first_candidate())
    candidate["source"] = "live_dropi"

    with pytest.raises(DropiFinancialBridgeError, match="candidate.source must be dropi_fixture"):
        dropi_candidate_to_financial_input(
            candidate,
            price="499.00",
            estimated_cac="80.00",
            expected_units=7,
        )


def test_a8_r92_dropi_bridge_fails_closed_before_financial_eval_on_product_side_effect():
    payload = _payload()
    unsafe = copy.deepcopy(payload)
    unsafe["products"][0]["safety"]["live_dropi"] = True

    with pytest.raises(DropiFixtureValidationError, match="product.safety.live_dropi must be false"):
        evaluate_dropi_candidate_financials(
            unsafe["products"][0],
            unsafe["supplier"],
            price="499.00",
            estimated_cac="80.00",
            expected_units=7,
        )


def test_a8_r92_dropi_financial_bridge_has_no_dangerous_imports_or_calls():
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))

    dangerous_import_roots = {
        "request" + "s",
        "http" + "x",
        "urllib",
        "socket",
        "sub" + "process",
    }
    dangerous_calls = {
        "url" + "open",
        "Popen",
        "run",
        "call",
        "check_call",
        "check_output",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in dangerous_import_roots

        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in dangerous_import_roots

        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id not in dangerous_calls
            elif isinstance(func, ast.Attribute):
                assert func.attr not in dangerous_calls