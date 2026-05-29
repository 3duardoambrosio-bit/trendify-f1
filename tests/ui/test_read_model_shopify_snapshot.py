import ast
import json
from pathlib import Path

import pytest

from synapse.ui import read_model


def valid_product(**overrides):
    product = {
        "category": "gadgets",
        "cost": 219.0,
        "image_url": "https://example.test/neck-fan.jpg",
        "images_count": 4,
        "keyword_matches": ["neck fan", "portable fan"],
        "margin_absolute": 280.0,
        "margin_percent": 56.11,
        "match_score": 0.91,
        "price": 499.0,
        "product_id": "prod-alpha",
        "rating": 4.7,
        "reviews": 184,
        "sales": 920,
        "shipping_days": 7,
        "supplier_id": "supplier-alpha",
        "supplier_name": "Dropi Alpha",
        "title": "Neck Fan Pro",
    }
    product.update(overrides)
    return product


def valid_ops(**overrides):
    ops = {
        "circuit_breaker": {},
        "dropi": {},
        "finance": {},
        "flags": {
            "dropi_live": False,
            "meta_live": False,
            "shopify_live": False,
            "spend_real_money": False,
        },
        "healthy": True,
        "meta": {},
        "shopify": {
            "api_ok": True,
            "checkout_ok": True,
            "orders_last_hour": 0,
        },
        "signals": {},
        "status": "nominal",
        "timestamp": "2026-05-28T00:00:00Z",
        "ts": "2026-05-28T00:00:00Z",
    }
    ops.update(overrides)
    return ops


def test_shopify_read_only_snapshot_loads_local_fixtures(tmp_path: Path) -> None:
    products_path = tmp_path / "products.json"
    ops_path = tmp_path / "ops.json"

    products_path.write_text(json.dumps([valid_product()]), encoding="utf-8")
    ops_path.write_text(json.dumps(valid_ops()), encoding="utf-8")

    snapshot = read_model.load_shopify_read_only_snapshot(products_path, ops_path)

    assert snapshot.product_count == 1
    assert snapshot.products[0]["title"] == "Neck Fan Pro"
    assert snapshot.shopify_live_enabled is False
    assert snapshot.spend_real_money_enabled is False
    assert snapshot.shopify_health["api_ok"] is True


def test_shopify_guardrail_rows_stay_read_only() -> None:
    snapshot = read_model.ShopifyReadOnlySnapshot(
        products=[],
        ops_tick={
            "flags": {
                "shopify_live": False,
                "spend_real_money": False,
            },
            "shopify": {
                "api_ok": True,
                "orders_last_hour": 0,
            },
        },
        product_source=Path("products.json"),
        ops_source=Path("ops.json"),
    )

    rows = read_model.shopify_guardrail_rows(snapshot)
    by_name = {row["guardrail"]: row for row in rows}

    assert by_name["source_mode"]["value"] == "local_fixture_only"
    assert by_name["shopify_live"]["value"] is False
    assert by_name["shopify_live"]["ok"] is True
    assert by_name["spend_real_money"]["value"] is False
    assert by_name["spend_real_money"]["ok"] is True


def test_shopify_product_rows_expose_safe_display_fields() -> None:
    snapshot = read_model.ShopifyReadOnlySnapshot(
        products=[valid_product()],
        ops_tick={},
        product_source=Path("products.json"),
        ops_source=Path("ops.json"),
    )

    rows = read_model.shopify_product_rows(snapshot)

    assert rows == [
        {
            "product_id": "prod-alpha",
            "title": "Neck Fan Pro",
            "category": "gadgets",
            "price": 499.0,
            "cost": 219.0,
            "margin_percent": 56.11,
            "sales": 920,
            "supplier": "Dropi Alpha",
            "source": "local_fixture",
        }
    ]


def test_read_model_shopify_ui_does_not_import_live_client() -> None:
    tree = ast.parse(Path("synapse/ui/read_model.py").read_text(encoding="utf-8"))

    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert "synapse.integrations.shopify_admin_client" not in imported_modules


def test_render_shopify_read_only_snapshot_uses_streamlit_only_for_display() -> None:
    class FakeSt:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []
            self.tables: list[list[dict[str, object]]] = []

        def subheader(self, value: str) -> None:
            self.messages.append(("subheader", value))

        def caption(self, value: str) -> None:
            self.messages.append(("caption", value))

        def info(self, value: str) -> None:
            self.messages.append(("info", value))

        def success(self, value: str) -> None:
            self.messages.append(("success", value))

        def warning(self, value: str) -> None:
            self.messages.append(("warning", value))

        def write(self, value: str) -> None:
            self.messages.append(("write", value))

        def dataframe(self, rows, use_container_width: bool) -> None:
            assert use_container_width is True
            self.tables.append(list(rows))

    snapshot = read_model.ShopifyReadOnlySnapshot(
        products=[valid_product()],
        ops_tick={
            "flags": {
                "shopify_live": False,
                "spend_real_money": False,
            },
            "shopify": {
                "api_ok": True,
                "orders_last_hour": 0,
            },
        },
        product_source=Path("products.json"),
        ops_source=Path("ops.json"),
    )

    fake = FakeSt()
    read_model.render_shopify_read_only_snapshot(fake, snapshot)

    assert ("subheader", "Shopify read-only snapshot") in fake.messages
    assert any(message[0] == "success" for message in fake.messages)
    assert len(fake.tables) == 2
    assert fake.tables[0][0]["guardrail"] == "source_mode"
    assert fake.tables[1][0]["title"] == "Neck Fan Pro"


def test_shopify_product_rows_allowlist_is_exact() -> None:
    snapshot = read_model.ShopifyReadOnlySnapshot(
        products=[
            valid_product(
                admin_secret="must_not_surface",
                graphql_token="must_not_surface",
            )
        ],
        ops_tick={},
        product_source=Path("products.json"),
        ops_source=Path("ops.json"),
    )

    row = read_model.shopify_product_rows(snapshot)

    assert tuple(row[0].keys()) == read_model.SHOPIFY_PRODUCT_ROW_KEYS
    assert "admin_secret" not in row[0]
    assert "graphql_token" not in row[0]


def test_shopify_fixture_paths_are_repo_root_absolute() -> None:
    assert read_model.SHOPIFY_PRODUCTS_FIXTURE_PATH.is_absolute()
    assert read_model.SHOPIFY_OPS_TICK_FIXTURE_PATH.is_absolute()
    assert read_model.SHOPIFY_PRODUCTS_FIXTURE_PATH.name == "products_nominal.json"
    assert read_model.SHOPIFY_OPS_TICK_FIXTURE_PATH.name == "ops_tick_nominal.json"


def test_shopify_fixture_invalid_json_is_wrapped(tmp_path: Path) -> None:
    products_path = tmp_path / "products.json"
    ops_path = tmp_path / "ops.json"

    products_path.write_text("{bad-json", encoding="utf-8")
    ops_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON fixture"):
        read_model.load_shopify_read_only_snapshot(products_path, ops_path)


def test_render_shopify_read_only_snapshot_panel_handles_fixture_error(tmp_path: Path) -> None:
    class FakeSt:
        def __init__(self) -> None:
            self.warnings: list[str] = []

        def warning(self, value: str) -> None:
            self.warnings.append(value)

    products_path = tmp_path / "products.json"
    ops_path = tmp_path / "ops.json"

    products_path.write_text("{bad-json", encoding="utf-8")
    ops_path.write_text("{}", encoding="utf-8")

    fake = FakeSt()
    read_model.render_shopify_read_only_snapshot_panel(fake, products_path, ops_path)

    assert len(fake.warnings) == 1
    assert "Shopify read-only snapshot no disponible" in fake.warnings[0]
