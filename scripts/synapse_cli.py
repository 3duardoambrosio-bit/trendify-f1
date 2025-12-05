import click

from buyer.buyer_block import BuyerBlock
from buyer.schemas import ProductSchema, ProductSource


def make_good_product() -> ProductSchema:
    """Replica del good_product del demo/tests, pero local al CLI."""
    return ProductSchema(
        product_id="good_123",
        external_id="ext_123",
        name="Good Product",
        category="Electronics",
        cost_price=100.0,
        sale_price=200.0,  # 50% margin
        trust_score=9.0,
        source=ProductSource.CSV,
    )


def make_bad_product() -> ProductSchema:
    """Replica del bad_product del demo/tests, pero local al CLI."""
    return ProductSchema(
        product_id="bad_123",
        external_id="ext_123",
        name="Bad Product",
        category="Electronics",
        cost_price=100.0,
        sale_price=110.0,  # 9% margin - debajo del umbral
        trust_score=9.0,
        source=ProductSource.CSV,
    )


@click.group()
def cli() -> None:
    """CLI mínimo de SYNAPSE / Trendify Fase 1."""
    # No hace falta lógica aquí, los comandos viven abajo.
    pass


@cli.command()
def status() -> None:
    """
    Checador simple de estado.

    F0: solo verifica que BuyerBlock se puede instanciar sin reventar.
    En el futuro aquí se enchufa health real de los sistemas.
    """
    try:
        _ = BuyerBlock()
        click.echo("[SYNAPSE] STATUS: OK - BuyerBlock operativo ✅")
    except Exception as e:  # noqa: BLE001
        click.echo("[SYNAPSE] STATUS: ERROR - BuyerBlock falló al inicializar ❌")
        click.echo(f"Detalle: {e}")


@cli.command("buyer-demo")
def buyer_demo() -> None:
    """
    Ejecuta una demo rápida del Buyer:
    - Evalúa un producto bueno
    - Evalúa un producto malo
    """
    buyer = BuyerBlock()

    good_product = make_good_product()
    bad_product = make_bad_product()

    good_decision = buyer.evaluate_product(good_product)
    bad_decision = buyer.evaluate_product(bad_product)

    click.echo("\n=== GOOD PRODUCT DECISION ===")
    # Pydantic v2 → model_dump; si no, decision.__dict__ también sirve
    try:
        click.echo(good_decision.model_dump())
    except AttributeError:
        click.echo(good_decision.__dict__)

    click.echo("\n=== BAD PRODUCT DECISION ===")
    try:
        click.echo(bad_decision.model_dump())
    except AttributeError:
        click.echo(bad_decision.__dict__)

    click.echo("\n[SYNAPSE] Demo completada ✅")


if __name__ == "__main__":
    cli()
