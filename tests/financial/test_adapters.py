from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import inspect

import pytest

import synapse.financial.adapters as adapters
from synapse.financial.adapters import candidate_to_financial_input, to_financial_input


def test_mapping_with_canonical_fields_converts_to_financial_input():
    result = candidate_to_financial_input(
        {
            "product_id": "prod-001",
            "name": "Adapter Product",
            "price": Decimal("849.00"),
            "landed_cost": Decimal("230.00"),
            "estimated_cac": Decimal("160.00"),
            "expected_units": 2,
        }
    )

    assert result.product_id == "prod-001"
    assert result.name == "Adapter Product"
    assert result.price == Decimal("849.00")
    assert result.landed_cost == Decimal("230.00")
    assert result.estimated_cac == Decimal("160.00")
    assert result.expected_units == 2


def test_mapping_aliases_id_title_and_cost_are_supported():
    result = candidate_to_financial_input(
        {
            "id": "alias-001",
            "title": "Alias Product",
            "price": "999.00",
            "cost": "260.00",
            "estimated_cac": "180.00",
        }
    )

    assert result.product_id == "alias-001"
    assert result.name == "Alias Product"
    assert result.price == Decimal("999.00")
    assert result.landed_cost == Decimal("260.00")
    assert result.estimated_cac == Decimal("180.00")
    assert result.expected_units == 1


@dataclass(frozen=True)
class ObjectCandidate:
    product_id: str
    name: str
    price: Decimal
    landed_cost: Decimal
    estimated_cac: Decimal
    expected_units: int = 1


def test_object_with_explicit_attributes_is_supported():
    result = candidate_to_financial_input(
        ObjectCandidate(
            product_id="obj-001",
            name="Object Product",
            price=Decimal("750.00"),
            landed_cost=Decimal("210.00"),
            estimated_cac=Decimal("120.00"),
            expected_units=3,
        )
    )

    assert result.product_id == "obj-001"
    assert result.name == "Object Product"
    assert result.price == Decimal("750.00")
    assert result.landed_cost == Decimal("210.00")
    assert result.estimated_cac == Decimal("120.00")
    assert result.expected_units == 3


def test_to_financial_input_alias_matches_primary_adapter():
    candidate = {
        "product_id": "alias-fn",
        "name": "Alias Function",
        "price": "500.00",
        "landed_cost": "150.00",
        "estimated_cac": "80.00",
    }

    assert to_financial_input(candidate) == candidate_to_financial_input(candidate)


def test_expected_units_defaults_to_one_when_missing():
    result = candidate_to_financial_input(
        {
            "product_id": "units-default",
            "name": "Default Units",
            "price": "500.00",
            "landed_cost": "150.00",
            "estimated_cac": "80.00",
        }
    )

    assert result.expected_units == 1


def test_expected_units_string_integer_is_supported():
    result = candidate_to_financial_input(
        {
            "product_id": "units-string",
            "name": "String Units",
            "price": "500.00",
            "landed_cost": "150.00",
            "estimated_cac": "80.00",
            "expected_units": "4",
        }
    )

    assert result.expected_units == 4


@pytest.mark.parametrize(
    ("field", "candidate"),
    [
        (
            "product_id",
            {
                "name": "Missing Product ID",
                "price": "500.00",
                "landed_cost": "150.00",
                "estimated_cac": "80.00",
            },
        ),
        (
            "name",
            {
                "product_id": "missing-name",
                "price": "500.00",
                "landed_cost": "150.00",
                "estimated_cac": "80.00",
            },
        ),
        (
            "price",
            {
                "product_id": "missing-price",
                "name": "Missing Price",
                "landed_cost": "150.00",
                "estimated_cac": "80.00",
            },
        ),
        (
            "landed_cost",
            {
                "product_id": "missing-cost",
                "name": "Missing Cost",
                "price": "500.00",
                "estimated_cac": "80.00",
            },
        ),
        (
            "estimated_cac",
            {
                "product_id": "missing-cac",
                "name": "Missing CAC",
                "price": "500.00",
                "landed_cost": "150.00",
            },
        ),
    ],
)
def test_missing_required_fields_fail_closed_without_inventing_economics(field, candidate):
    with pytest.raises(ValueError, match=f"missing required field: {field}"):
        candidate_to_financial_input(candidate)


@pytest.mark.parametrize(
    ("field", "candidate"),
    [
        (
            "product_id",
            {
                "product_id": " ",
                "name": "Blank Product ID",
                "price": "500.00",
                "landed_cost": "150.00",
                "estimated_cac": "80.00",
            },
        ),
        (
            "name",
            {
                "product_id": "blank-name",
                "name": " ",
                "price": "500.00",
                "landed_cost": "150.00",
                "estimated_cac": "80.00",
            },
        ),
    ],
)
def test_blank_text_fields_fail_closed(field, candidate):
    with pytest.raises(ValueError, match=f"{field} must not be empty"):
        candidate_to_financial_input(candidate)


@pytest.mark.parametrize(
    ("field", "candidate"),
    [
        (
            "price",
            {
                "product_id": "bad-price",
                "name": "Bad Price",
                "price": "not-a-number",
                "landed_cost": "150.00",
                "estimated_cac": "80.00",
            },
        ),
        (
            "landed_cost",
            {
                "product_id": "bad-cost",
                "name": "Bad Cost",
                "price": "500.00",
                "landed_cost": None,
                "estimated_cac": "80.00",
            },
        ),
        (
            "estimated_cac",
            {
                "product_id": "bad-cac",
                "name": "Bad CAC",
                "price": "500.00",
                "landed_cost": "150.00",
                "estimated_cac": "",
            },
        ),
    ],
)
def test_invalid_decimal_fields_fail_closed(field, candidate):
    with pytest.raises(ValueError, match=f"{field} must be a finite decimal"):
        candidate_to_financial_input(candidate)


@pytest.mark.parametrize("bad_value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_decimal_values_are_rejected(bad_value):
    with pytest.raises(ValueError, match="price must be a finite decimal"):
        candidate_to_financial_input(
            {
                "product_id": "non-finite",
                "name": "Non Finite",
                "price": bad_value,
                "landed_cost": "150.00",
                "estimated_cac": "80.00",
            }
        )


def test_boolean_decimal_fields_are_rejected():
    with pytest.raises(ValueError, match="price must be a finite decimal"):
        candidate_to_financial_input(
            {
                "product_id": "bool-price",
                "name": "Bool Price",
                "price": True,
                "landed_cost": "150.00",
                "estimated_cac": "80.00",
            }
        )


@pytest.mark.parametrize("bad_units", ["0", "-1", "1.5", "many", True])
def test_invalid_expected_units_are_rejected(bad_units):
    with pytest.raises(ValueError, match="expected_units must be a positive integer"):
        candidate_to_financial_input(
            {
                "product_id": "bad-units",
                "name": "Bad Units",
                "price": "500.00",
                "landed_cost": "150.00",
                "estimated_cac": "80.00",
                "expected_units": bad_units,
            }
        )


def test_adapter_does_not_mutate_mapping_source():
    candidate = {
        "product_id": "immutable-source",
        "name": "Immutable Source",
        "price": "500.00",
        "landed_cost": "150.00",
        "estimated_cac": "80.00",
    }
    before = dict(candidate)

    result = candidate_to_financial_input(candidate)

    assert candidate == before
    assert result.product_id == "immutable-source"


def test_adapter_output_is_deterministic_for_same_input():
    candidate = {
        "product_id": "deterministic",
        "name": "Deterministic",
        "price": "849.00",
        "landed_cost": "230.00",
        "estimated_cac": "160.00",
    }

    assert candidate_to_financial_input(candidate) == candidate_to_financial_input(candidate)


def test_adapter_has_no_io_or_external_mutation_surface():
    source = inspect.getsource(adapters)

    forbidden = (
        "requests.",
        "httpx.",
        "urllib.",
        "subprocess",
        "socket.",
        "open(",
        "Path(",
        "write_text",
        "read_text",
        "os.environ",
    )

    for token in forbidden:
        assert token not in source