from synapse.infra.cli_logging import cli_print

import csv
from typing import List, Dict, Any
from buyer.schemas import ProductSchema, ProductSource


class CatalogNormalizer:
    def __init__(self, source: ProductSource = ProductSource.CSV) -> None:
        self.source = source

    def normalize_from_csv(self, file_path: str) -> List[ProductSchema]:
        """Normalize products from CSV file"""
        products: List[ProductSchema] = []

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for row_num, row in enumerate(reader, 1):
                    product = self._normalize_row(row, row_num)
                    if product:
                        products.append(product)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Error reading CSV file {file_path}: {str(e)}") from e

        return products

    def _normalize_row(self, row: Dict[str, Any], row_num: int) -> ProductSchema | None:
        """Normalize a single CSV row to ProductSchema"""
        try:
            product_id = row.get("product_id") or f"row_{row_num}"
            external_id = row.get("external_id") or product_id
            name = (row.get("name") or "").strip()
            category = (row.get("category") or "uncategorized").strip()

            if not name:
                raise ValueError(f"Missing product name in row {row_num}")

            try:
                cost_price = float(row.get("cost_price", 0))
                sale_price = float(row.get("sale_price", 0))
            except (TypeError, ValueError) as e:
                raise ValueError(f"Invalid price values in row {row_num}") from e

            trust_score = None
            if row.get("trust_score"):
                try:
                    trust_score = float(row["trust_score"])
                except (TypeError, ValueError):
                    trust_score = None

            return ProductSchema(
                product_id=product_id,
                external_id=external_id,
                name=name,
                description=(row.get("description") or "").strip(),
                category=category,
                cost_price=cost_price,
                sale_price=sale_price,
                trust_score=trust_score,
                supplier=(row.get("supplier") or "").strip(),
                source=self.source,
                metadata={
                    "row_number": row_num,
                    "raw_data": {
                        k: v
                        for k, v in row.items()
                        if k
                        not in [
                            "product_id",
                            "external_id",
                            "name",
                            "description",
                            "category",
                            "cost_price",
                            "sale_price",
                            "trust_score",
                            "supplier",
                        ]
                    },
                },
            )

        except Exception as e:  # noqa: BLE001
            cli_print(f"Warning: Skipping row {row_num}: {str(e)}")
            return None
