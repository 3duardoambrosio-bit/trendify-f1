import json
from pathlib import Path

import click

from buyer.catalog_normalizer import CatalogNormalizer
from buyer.buyer_block import BuyerBlock
from buyer.schemas import ProductSource
from infra.logging_config import setup_logging


@click.group()
def cli() -> None:
    """Buyer Block CLI"""
    setup_logging()


@cli.command()
@click.option("--input", "input_path", required=True, help="Input CSV file path")
@click.option("--output", "output_path", help="Output JSON file path")
@click.option(
    "--source",
    default="csv",
    type=click.Choice(["csv", "droppi"]),
    help="Data source",
)
def evaluate(input_path: str, output_path: str | None, source: str) -> None:
    """Evaluate products from CSV file"""

    input_file = Path(input_path)
    if not input_file.exists():
        click.echo(f"Error: Input file {input_path} does not exist")
        return

    product_source = ProductSource.CSV if source == "csv" else ProductSource.DROPPI

    try:
        normalizer = CatalogNormalizer(source=product_source)
        products = normalizer.normalize_from_csv(input_path)

        click.echo(f"Loaded {len(products)} products from {input_path}")

        buyer = BuyerBlock()
        decisions = buyer.evaluate_batch(products)

        decisions_dict = [decision.model_dump() for decision in decisions]

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                json.dump(decisions_dict, f, indent=2, ensure_ascii=False)
            click.echo(f"Results saved to {output_path}")
        else:
            click.echo(json.dumps(decisions_dict, indent=2, ensure_ascii=False))

    except Exception as e:  # noqa: BLE001
        click.echo(f"Error: {str(e)}")


if __name__ == "__main__":
    cli()
