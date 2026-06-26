from __future__ import annotations

import ast
import json
from decimal import Decimal
from pathlib import Path

import pytest

from synapse.integration.dropi_catalog_eval_bridge import (
    DropiCatalogEvaluationError,
    build_dropi_catalog_evaluation_assumptions,
    build_dropi_catalog_evaluated_shortlist_from_csv,
)


FIXTURE_DIR = Path("tests/fixtures/dropi_catalog_import")
NOMINAL_CSV = FIXTURE_DIR / "catalog_nominal.csv"


def _assumptions_min_mxn():
    return build_dropi_catalog_evaluation_assumptions(
        sale_price_mxn=Decimal("499.00"),
        estimated_cac_mxn=Decimal("95.00"),
        expected_units=3,
        min_margin_mxn=Decimal("50.00"),
    )


def test_a8_r97_catalog_csv_builds_deterministic_shortlist_and_evidence(tmp_path):
    evidence_path = tmp_path / "a8_r97_evidence.json"

    result = build_dropi_catalog_evaluated_shortlist_from_csv(
        NOMINAL_CSV,
        _assumptions_min_mxn(),
        max_items=10,
        evidence_path=evidence_path,
    )

    assert result.source_record_count >= 1
    assert len(result.items) == result.source_record_count
    assert result.accepted_count + result.rejected_count == len(result.items)

    ordered = [
        (
            0 if item.accepted else 1,
            -item.contribution_margin_mxn,
            -item.contribution_margin_pct,
            item.sku,
        )
        for item in result.items
    ]
    assert ordered == sorted(ordered)

    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert evidence["schema"] == "synapse.a8_r97.dropi_catalog_evaluation.v1"
    assert evidence["source_record_count"] == result.source_record_count
    assert evidence["accepted_count"] == result.accepted_count
    assert evidence["rejected_count"] == result.rejected_count
    assert evidence["safety"]["local_only"] is True
    assert evidence["safety"]["live_dropi"] is False
    assert evidence["safety"]["external_writes"] is False
    assert "sale_price_mxn" in evidence["assumptions"]
    assert "estimated_cac_mxn" in evidence["assumptions"]
    assert "expected_units" in evidence["assumptions"]


def test_a8_r97_catalog_csv_preserves_r96_landed_cost_as_cost_basis(tmp_path):
    result = build_dropi_catalog_evaluated_shortlist_from_csv(
        NOMINAL_CSV,
        _assumptions_min_mxn(),
        max_items=10,
        evidence_path=tmp_path / "evidence.json",
    )

    assert result.items
    for item in result.items:
        assert isinstance(item.landed_cost_mxn, Decimal)
        assert item.landed_cost_mxn >= Decimal("0.00")
        assert isinstance(item.contribution_margin_mxn, Decimal)
        assert isinstance(item.contribution_margin_pct, Decimal)


def test_a8_r97_requires_sale_price():
    with pytest.raises(DropiCatalogEvaluationError, match="missing_decimal:sale_price_mxn"):
        build_dropi_catalog_evaluation_assumptions(
            sale_price_mxn="",
            estimated_cac_mxn=Decimal("95.00"),
            expected_units=3,
            min_margin_mxn=Decimal("50.00"),
        )


def test_a8_r97_requires_estimated_cac():
    with pytest.raises(DropiCatalogEvaluationError, match="missing_decimal:estimated_cac_mxn"):
        build_dropi_catalog_evaluation_assumptions(
            sale_price_mxn=Decimal("499.00"),
            estimated_cac_mxn="",
            expected_units=3,
            min_margin_mxn=Decimal("50.00"),
        )


def test_a8_r97_requires_explicit_expected_units_from_real_financial_contract():
    with pytest.raises(DropiCatalogEvaluationError, match="missing_expected_units"):
        build_dropi_catalog_evaluation_assumptions(
            sale_price_mxn=Decimal("499.00"),
            estimated_cac_mxn=Decimal("95.00"),
            expected_units="",
            min_margin_mxn=Decimal("50.00"),
        )


def test_a8_r97_requires_exactly_one_margin_threshold():
    with pytest.raises(DropiCatalogEvaluationError, match="exactly_one_margin_threshold_required"):
        build_dropi_catalog_evaluation_assumptions(
            sale_price_mxn=Decimal("499.00"),
            estimated_cac_mxn=Decimal("95.00"),
            expected_units=3,
        )

    with pytest.raises(DropiCatalogEvaluationError, match="exactly_one_margin_threshold_required"):
        build_dropi_catalog_evaluation_assumptions(
            sale_price_mxn=Decimal("499.00"),
            estimated_cac_mxn=Decimal("95.00"),
            expected_units=3,
            min_margin_mxn=Decimal("50.00"),
            min_margin_pct=Decimal("0.1000"),
        )


@pytest.mark.parametrize(
    ("field", "kwargs", "match"),
    [
        (
            "sale_price_mxn",
            {
                "sale_price_mxn": 499.0,
                "estimated_cac_mxn": Decimal("95.00"),
                "expected_units": 3,
                "min_margin_mxn": Decimal("50.00"),
            },
            "float_money_not_allowed:sale_price_mxn",
        ),
        (
            "estimated_cac_mxn",
            {
                "sale_price_mxn": Decimal("499.00"),
                "estimated_cac_mxn": 95.0,
                "expected_units": 3,
                "min_margin_mxn": Decimal("50.00"),
            },
            "float_money_not_allowed:estimated_cac_mxn",
        ),
        (
            "min_margin_mxn",
            {
                "sale_price_mxn": Decimal("499.00"),
                "estimated_cac_mxn": Decimal("95.00"),
                "expected_units": 3,
                "min_margin_mxn": 50.0,
            },
            "float_money_not_allowed:min_margin_mxn",
        ),
        (
            "min_margin_pct",
            {
                "sale_price_mxn": Decimal("499.00"),
                "estimated_cac_mxn": Decimal("95.00"),
                "expected_units": 3,
                "min_margin_pct": 0.2,
            },
            "float_money_not_allowed:min_margin_pct",
        ),
    ],
)
def test_a8_r97_rejects_float_money_assumptions(field, kwargs, match):
    with pytest.raises(DropiCatalogEvaluationError, match=match):
        build_dropi_catalog_evaluation_assumptions(**kwargs)


def test_a8_r97_rejects_invalid_decimal_money():
    with pytest.raises(DropiCatalogEvaluationError, match="invalid_decimal:sale_price_mxn"):
        build_dropi_catalog_evaluation_assumptions(
            sale_price_mxn="not-money",
            estimated_cac_mxn=Decimal("95.00"),
            expected_units=3,
            min_margin_mxn=Decimal("50.00"),
        )


def test_a8_r97_min_margin_pct_path_produces_shortlist(tmp_path):
    assumptions = build_dropi_catalog_evaluation_assumptions(
        sale_price_mxn=Decimal("499.00"),
        estimated_cac_mxn=Decimal("95.00"),
        expected_units=3,
        min_margin_pct=Decimal("0.1000"),
    )

    result = build_dropi_catalog_evaluated_shortlist_from_csv(
        NOMINAL_CSV,
        assumptions,
        max_items=10,
        evidence_path=tmp_path / "evidence.json",
    )

    assert result.source_record_count >= 1
    assert all(isinstance(item.contribution_margin_pct, Decimal) for item in result.items)


def test_a8_r97_static_guard_new_files_local_only():
    paths = [
        Path("synapse/integration/dropi_catalog_eval_bridge.py"),
        Path("tests/integration/test_a8_r97_dropi_catalog_eval_bridge.py"),
    ]

    forbidden_import_roots = {
        "requests",
        "httpx",
        "urllib",
        "aiohttp",
        "socket",
        "ftplib",
        "paramiko",
        "boto3",
    }
    forbidden_calls = {
        "urlopen",
        "Request",
        "request",
        "post",
        "put",
        "patch",
        "delete",
        "system",
        "popen",
        "Popen",
        "check_call",
        "check_output",
    }

    hits = []

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in forbidden_import_roots:
                        hits.append((str(path), "import", alias.name))

            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                root = mod.split(".", 1)[0]
                if root in forbidden_import_roots:
                    hits.append((str(path), "import-from", mod))

            if isinstance(node, ast.Call):
                fn = node.func
                name = None
                if isinstance(fn, ast.Name):
                    name = fn.id
                elif isinstance(fn, ast.Attribute):
                    name = fn.attr
                if name in forbidden_calls:
                    hits.append((str(path), "call", name))

    assert hits == []