from decimal import Decimal
from pathlib import Path

import pytest

from synapse.integration.dropi_catalog_import_readonly import (
    DropiCatalogImportError,
    DropiCatalogImportRecord,
    normalize_dropi_catalog_row,
    parse_dropi_catalog_csv,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dropi_catalog_import"
MODULE = Path(__file__).resolve().parents[2] / "synapse" / "integration" / "dropi_catalog_import_readonly.py"


def test_nominal_csv_parses_decimal_money_and_utf8() -> None:
    records = parse_dropi_catalog_csv(FIXTURES / "catalog_nominal.csv")

    assert len(records) == 2
    first = records[0]

    assert isinstance(first, DropiCatalogImportRecord)
    assert first.title == "Cámara portátil café"
    assert first.supplier == "Proveedor Águila"
    assert first.sku == "CAM-CAF-001"
    assert first.supplier_cost_mxn == Decimal("120.50")
    assert first.shipping_cost_mxn == Decimal("30.00")
    assert first.landed_cost_mxn == Decimal("150.50")
    assert first.stock == 7
    assert first.shipping_days == 3
    assert first.supplier_rating == Decimal("4.8")


def test_alias_headers_map_deterministically(tmp_path: Path) -> None:
    csv_path = tmp_path / "aliases.csv"
    csv_path.write_text(
        "name,cost_mxn,shipping_mxn,supplier_name,inventory,external_id\n"
        "Producto Alias,101.239,9.991,Proveedor Alias,2,ALIAS-001\n",
        encoding="utf-8",
    )

    record = parse_dropi_catalog_csv(csv_path)[0]

    assert record.title == "Producto Alias"
    assert record.supplier_cost_mxn == Decimal("101.24")
    assert record.shipping_cost_mxn == Decimal("9.99")
    assert record.stock == 2
    assert record.sku == "ALIAS-001"


def test_missing_required_field_is_rejected() -> None:
    with pytest.raises(DropiCatalogImportError, match="missing_required_field:sku"):
        parse_dropi_catalog_csv(FIXTURES / "catalog_missing_required.csv")


def test_invalid_money_is_rejected() -> None:
    with pytest.raises(DropiCatalogImportError, match="invalid_money:supplier_cost_mxn"):
        parse_dropi_catalog_csv(FIXTURES / "catalog_invalid_money.csv")


def test_direct_api_rejects_float_money() -> None:
    with pytest.raises(DropiCatalogImportError, match="float_money_not_allowed:supplier_cost_mxn"):
        normalize_dropi_catalog_row(
            {
                "title": "Float money",
                "supplier_cost_mxn": 12.3,
                "shipping_cost_mxn": "1.00",
                "supplier": "Proveedor",
                "stock": "1",
                "sku": "FLOAT-001",
            }
        )


def test_negative_money_is_rejected() -> None:
    with pytest.raises(DropiCatalogImportError, match="negative_money:supplier_cost_mxn"):
        normalize_dropi_catalog_row(
            {
                "title": "Negative money",
                "supplier_cost_mxn": "-1.00",
                "shipping_cost_mxn": "1.00",
                "supplier": "Proveedor",
                "stock": "1",
                "sku": "NEG-001",
            }
        )


def test_negative_stock_is_rejected() -> None:
    with pytest.raises(DropiCatalogImportError, match="negative_stock"):
        normalize_dropi_catalog_row(
            {
                "title": "Negative stock",
                "supplier_cost_mxn": "1.00",
                "shipping_cost_mxn": "1.00",
                "supplier": "Proveedor",
                "stock": "-1",
                "sku": "NEG-STOCK-001",
            }
        )


def test_deterministic_output_order() -> None:
    records = parse_dropi_catalog_csv(FIXTURES / "catalog_nominal.csv")
    assert [r.sku for r in records] == ["CAM-CAF-001", "SOP-ERG-002"]


def test_record_exposes_evaluation_seed_without_float_money() -> None:
    record = parse_dropi_catalog_csv(FIXTURES / "catalog_nominal.csv")[0]
    seed = record.to_evaluation_seed()

    assert seed["supplier_cost_mxn"] == "120.50"
    assert seed["shipping_cost_mxn"] == "30.00"
    assert seed["landed_cost_mxn"] == "150.50"
    assert seed["stock"] == 7


def test_module_has_no_live_transport_or_write_verbs() -> None:
    source = MODULE.read_text(encoding="utf-8")

    forbidden = [
        "requests",
        "httpx",
        "urllib",
        ".post(",
        ".put(",
        ".delete(",
        ".write_text(",
        ".write_bytes(",
    ]

    for token in forbidden:
        assert token not in source