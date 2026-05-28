import ast
import json
from pathlib import Path

from synapse.ui import read_model


def test_shopify_read_only_snapshot_loads_local_fixtures(tmp_path: Path) -> None:
    products_path = tmp_path / "products.json"
    ops_path = tmp_path / "ops.json"

    products_path.write_text(
        json.dumps(
            [
                {
                    "product_id": "prod-alpha",
                    "title": "Neck Fan Pro",
                    "category": "gadgets",
                    "price": 499.0,
                    "cost": 219.0,
                    "margin_percent": 56.11,
                    "sales": 920,
                    "supplier_name": "Dropi Alpha",
                }
            ]
        ),
        encoding="utf-8",
    )
    ops_path.write_text(
        json.dumps(
            {
                "flags": {
                    "shopify_live": False,
                    "spend_real_money": False,
                },
                "shopify": {
                    "api_ok": True,
                    "checkout_ok": True,
                    "orders_last_hour": 0,
                },
            }
        ),
        encoding="utf-8",
    )

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
        products=[
            {
                "product_id": "prod-alpha",
                "title": "Neck Fan Pro",
                "category": "gadgets",
                "price": 499.0,
                "cost": 219.0,
                "margin_percent": 56.11,
                "sales": 920,
                "supplier_name": "Dropi Alpha",
                "access_token": "must_not_surface",
            }
        ],
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
        products=[
            {
                "product_id": "prod-alpha",
                "title": "Neck Fan Pro",
                "category": "gadgets",
                "price": 499.0,
                "cost": 219.0,
                "margin_percent": 56.11,
                "sales": 920,
                "supplier_name": "Dropi Alpha",
            }
        ],
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
