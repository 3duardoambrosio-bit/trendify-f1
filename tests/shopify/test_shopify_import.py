# tests/shopify/test_shopify_import.py
import os
import csv
import tempfile

from synapse.shopify import ShopifyProductInput, generate_shopify_csv


def test_generate_shopify_csv_writes_header_and_rows():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "products.csv")
        p = ShopifyProductInput(
            product_id="34357",
            title="Audífonos Bluetooth M10",
            price_mxn=399,
            tags=["audio", "bluetooth"],
            image_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
        )
        path = generate_shopify_csv([p], out)
        assert os.path.exists(path)

        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2  # 2 images => 2 rows
        assert rows[0]["Title"] == "Audífonos Bluetooth M10"
        assert "34357" in rows[0]["Handle"]
        assert rows[0]["Image Position"] == "1"
        assert rows[1]["Image Position"] == "2"
