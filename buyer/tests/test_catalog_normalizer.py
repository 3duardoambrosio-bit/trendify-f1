import csv
import os
import tempfile

from buyer.catalog_normalizer import CatalogNormalizer
from buyer.schemas import ProductSource


def _make_temp_csv(fieldnames, row) -> str:
    # En Windows, delete=False y luego cerramos el archivo
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)  # liberamos el handle

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)

    return path


def test_normalize_from_csv_valid():
    """Test CSV normalization with valid data"""
    path = _make_temp_csv(
        [
            "product_id",
            "external_id",
            "name",
            "description",
            "category",
            "cost_price",
            "sale_price",
            "trust_score",
            "supplier",
        ],
        {
            "product_id": "prod1",
            "external_id": "ext1",
            "name": "Product 1",
            "description": "Description 1",
            "category": "Category 1",
            "cost_price": "100.0",
            "sale_price": "150.0",
            "trust_score": "8.5",
            "supplier": "Supplier 1",
        },
    )

    try:
        normalizer = CatalogNormalizer(source=ProductSource.CSV)
        products = normalizer.normalize_from_csv(path)

        assert len(products) == 1
        product = products[0]
        assert product.product_id == "prod1"
        assert product.name == "Product 1"
        assert product.cost_price == 100.0
        assert product.sale_price == 150.0
        assert product.trust_score == 8.5
    finally:
        os.remove(path)


def test_normalize_from_csv_missing_name():
    """Test CSV normalization with missing required field"""
    path = _make_temp_csv(
        [
            "product_id",
            "external_id",
            "name",
            "category",
            "cost_price",
            "sale_price",
        ],
        {
            "product_id": "prod1",
            "external_id": "ext1",
            "name": "",  # Empty name
            "category": "Category 1",
            "cost_price": "100.0",
            "sale_price": "150.0",
        },
    )

    try:
        normalizer = CatalogNormalizer(source=ProductSource.CSV)
        products = normalizer.normalize_from_csv(path)

        # Should skip invalid row
        assert len(products) == 0
    finally:
        os.remove(path)


def test_normalize_from_csv_invalid_prices():
    """Test CSV normalization with invalid price values"""
    path = _make_temp_csv(
        [
            "product_id",
            "external_id",
            "name",
            "category",
            "cost_price",
            "sale_price",
        ],
        {
            "product_id": "prod1",
            "external_id": "ext1",
            "name": "Product 1",
            "category": "Category 1",
            "cost_price": "invalid",  # Invalid price
            "sale_price": "150.0",
        },
    )

    try:
        normalizer = CatalogNormalizer(source=ProductSource.CSV)
        products = normalizer.normalize_from_csv(path)

        # Should skip invalid row
        assert len(products) == 0
    finally:
        os.remove(path)
