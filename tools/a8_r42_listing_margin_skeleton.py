from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MarginScenario:
    name: str
    sell_price_usd: float
    product_cost_usd: float
    shipping_allowance_usd: float
    payment_fee_usd: float
    packaging_allowance_usd: float
    gross_profit_usd: float
    gross_margin_pct: float
    break_even_cpa_usd: float
    signal_quality: str


@dataclass(frozen=True)
class ListingMarginPacket:
    product: str
    decision: str
    total_score: int
    listing_title: str
    subtitle: str
    one_sentence_description: str
    product_description: str
    listing_bullets: list[str]
    image_requirements: list[str]
    offer_stack: list[str]
    trust_blocks: list[str]
    price_positioning: str
    margin_scenarios: list[MarginScenario]
    supplier_validation_checklist: list[str]
    listing_readiness_checklist: list[str]
    manual_test_before_spend_rules: list[str]
    hard_reject_rules: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("INPUT_MUST_BE_OBJECT")
    return raw


def _margin(
    *,
    name: str,
    sell_price_usd: float,
    product_cost_usd: float,
    shipping_allowance_usd: float,
    payment_fee_usd: float,
    packaging_allowance_usd: float,
    signal_quality: str,
) -> MarginScenario:
    gross_profit = round(
        sell_price_usd
        - product_cost_usd
        - shipping_allowance_usd
        - payment_fee_usd
        - packaging_allowance_usd,
        2,
    )
    gross_margin_pct = round((gross_profit / sell_price_usd) * 100, 2)
    break_even_cpa = gross_profit

    return MarginScenario(
        name=name,
        sell_price_usd=sell_price_usd,
        product_cost_usd=product_cost_usd,
        shipping_allowance_usd=shipping_allowance_usd,
        payment_fee_usd=payment_fee_usd,
        packaging_allowance_usd=packaging_allowance_usd,
        gross_profit_usd=gross_profit,
        gross_margin_pct=gross_margin_pct,
        break_even_cpa_usd=break_even_cpa,
        signal_quality=signal_quality,
    )


def build_listing_margin_packet(
    offer_packet: dict[str, Any],
    manual_packet: dict[str, Any],
) -> ListingMarginPacket:
    product = str(offer_packet["product"])
    decision = str(offer_packet["decision"])
    total_score = int(offer_packet["total_score"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"UNEXPECTED_PRODUCT={product}")

    manual_product = str(manual_packet["product"])
    if manual_product != product:
        raise ValueError(f"MANUAL_PACKET_PRODUCT_MISMATCH={manual_product}")

    listing_bullets = [
        "Removes lint, fuzz, and fabric pills from sweaters, hoodies, blankets, sofas, and daily outfits.",
        "Helps tired-looking fabric look cleaner and more presentable before replacing the item.",
        "Rechargeable portable design for fast at-home fabric touch-ups.",
        "Clear before/after effect that is easy to understand without complicated explanation.",
        "Useful for people who want clothes and fabric surfaces to look sharper with less waste.",
    ]

    image_requirements = [
        "Image 01: product visible beside fuzzy fabric.",
        "Image 02: close before shot of fabric pills.",
        "Image 03: half-cleaned split before/after shot.",
        "Image 04: cleaned final result on sweater or hoodie.",
        "Image 05: product in hand for scale.",
        "Image 06: safe-use guidance visual: test a small area first.",
    ]

    offer_stack = [
        "Portable electric fabric shaver.",
        "Rechargeable use case.",
        "Before/after fabric cleanup promise.",
        "Use cases: sweaters, hoodies, blankets, sofas.",
        "Simple safe-use guidance.",
    ]

    trust_blocks = [
        "Use gently and test a small area first.",
        "Best for visible lint, fuzz, and fabric pills.",
        "Not positioned as a repair tool for damaged fabric.",
        "Results depend on fabric type and condition.",
        "Product page must show real before/after visuals, not exaggerated claims.",
    ]

    margin_scenarios = [
        _margin(
            name="conservative",
            sell_price_usd=14.99,
            product_cost_usd=7.00,
            shipping_allowance_usd=2.50,
            payment_fee_usd=0.75,
            packaging_allowance_usd=0.50,
            signal_quality="Weak unless organic demand is strong.",
        ),
        _margin(
            name="base_case",
            sell_price_usd=18.99,
            product_cost_usd=6.00,
            shipping_allowance_usd=2.50,
            payment_fee_usd=0.85,
            packaging_allowance_usd=0.50,
            signal_quality="Usable if creative generates clear buy intent.",
        ),
        _margin(
            name="premium_bundle",
            sell_price_usd=22.99,
            product_cost_usd=7.50,
            shipping_allowance_usd=2.75,
            payment_fee_usd=1.00,
            packaging_allowance_usd=0.75,
            signal_quality="Preferred only if bundle or quality angle is credible.",
        ),
    ]

    supplier_validation_checklist = [
        "Confirm rechargeable model, charging cable, and battery details.",
        "Confirm blade guard and safe-use design.",
        "Request real product dimensions and weight.",
        "Check supplier can provide consistent packaging photos.",
        "Check replacement/defect policy before any paid traffic.",
        "Reject suppliers with unclear safety claims or fake before/after media.",
        "Validate that landed cost can support at least base-case gross margin.",
    ]

    listing_readiness_checklist = [
        "Listing title has product + use case.",
        "First image shows clear fabric problem.",
        "Second image shows before/after split.",
        "Bullets do not overpromise fabric repair.",
        "Safe-use note is visible.",
        "CTA explains why the buyer should try fixing fabric before replacing clothes.",
        "Price scenario chosen before traffic.",
        "Manual content signal exists before paid scaling.",
    ]

    manual_test_before_spend_rules = [
        "Do not buy ads before at least one organic before/after asset gets meaningful saves or buy-intent comments.",
        "Do not buy inventory before supplier quality and landed cost are checked.",
        "Do not build full store page until the manual asset packet gets signal.",
        "Keep the first test lightweight: content first, listing second, supplier third.",
    ]

    hard_reject_rules = [
        "Reject if before/after is not visually obvious on camera.",
        "Reject if landed cost makes break-even CPA too low for testing.",
        "Reject if product quality creates safety or fabric-damage risk.",
        "Reject if comments show curiosity but no buying intent.",
        "Reject if the product requires too much explanation to sell in short-form content.",
    ]

    return ListingMarginPacket(
        product=product,
        decision=decision,
        total_score=total_score,
        listing_title="Rechargeable Electric Lint Remover for Clothes and Fabric",
        subtitle="Make fuzzy clothes, blankets, and fabric surfaces look cleaner in minutes.",
        one_sentence_description=(
            "A portable rechargeable fabric shaver that helps remove lint, fuzz, and fabric pills "
            "so everyday clothes and home fabrics look cleaner and more presentable."
        ),
        product_description=(
            "Clean clothes can still look old when the fabric is covered in fuzz, lint, or fabric pills. "
            "This rechargeable electric lint remover is built for quick visual fabric cleanup on sweaters, "
            "hoodies, blankets, sofas, and other compatible fabric surfaces. The offer should be sold through "
            "real before/after proof, safe-use guidance, and a simple message: try improving the fabric texture "
            "before replacing the item."
        ),
        listing_bullets=listing_bullets,
        image_requirements=image_requirements,
        offer_stack=offer_stack,
        trust_blocks=trust_blocks,
        price_positioning=(
            "Start with base-case price testing. Conservative pricing leaves weak room for acquisition. "
            "Premium bundle pricing only works if product quality, bundle value, or creative proof supports it."
        ),
        margin_scenarios=margin_scenarios,
        supplier_validation_checklist=supplier_validation_checklist,
        listing_readiness_checklist=listing_readiness_checklist,
        manual_test_before_spend_rules=manual_test_before_spend_rules,
        hard_reject_rules=hard_reject_rules,
    )


def write_markdown(packet: ListingMarginPacket, path: Path) -> None:
    lines: list[str] = [
        "# A8-R42F First Listing + Price/Margin Skeleton",
        "",
        "## Product",
        "",
        f"`{packet.product}`",
        "",
        "## Decision",
        "",
        f"- decision: `{packet.decision}`",
        f"- total_score: `{packet.total_score}`",
        "",
        "## Listing draft",
        "",
        f"- title: {packet.listing_title}",
        f"- subtitle: {packet.subtitle}",
        "",
        "## One sentence description",
        "",
        packet.one_sentence_description,
        "",
        "## Product description",
        "",
        packet.product_description,
        "",
        "## Listing bullets",
        "",
    ]

    for item in packet.listing_bullets:
        lines.append(f"- {item}")

    sections = [
        ("Image requirements", packet.image_requirements),
        ("Offer stack", packet.offer_stack),
        ("Trust blocks", packet.trust_blocks),
        ("Supplier validation checklist", packet.supplier_validation_checklist),
        ("Listing readiness checklist", packet.listing_readiness_checklist),
        ("Manual test before spend rules", packet.manual_test_before_spend_rules),
        ("Hard reject rules", packet.hard_reject_rules),
    ]

    for title, items in sections:
        lines.extend(["", f"## {title}", ""])
        for item in items:
            lines.append(f"- {item}")

    lines.extend(["", "## Price positioning", "", packet.price_positioning, ""])
    lines.extend(["## Margin scenarios", ""])

    for scenario in packet.margin_scenarios:
        lines.extend(
            [
                f"### {scenario.name}",
                "",
                f"- sell_price_usd: {scenario.sell_price_usd}",
                f"- product_cost_usd: {scenario.product_cost_usd}",
                f"- shipping_allowance_usd: {scenario.shipping_allowance_usd}",
                f"- payment_fee_usd: {scenario.payment_fee_usd}",
                f"- packaging_allowance_usd: {scenario.packaging_allowance_usd}",
                f"- gross_profit_usd: {scenario.gross_profit_usd}",
                f"- gross_margin_pct: {scenario.gross_margin_pct}",
                f"- break_even_cpa_usd: {scenario.break_even_cpa_usd}",
                f"- signal_quality: {scenario.signal_quality}",
                "",
            ]
        )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offer-packet", required=True)
    parser.add_argument("--manual-packet", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    offer_packet = _load_json(Path(args.offer_packet).resolve())
    manual_packet = _load_json(Path(args.manual_packet).resolve())

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    packet = build_listing_margin_packet(offer_packet, manual_packet)

    json_path = out_dir / "listing_margin_skeleton.json"
    md_path = out_dir / "listing_margin_skeleton.md"

    json_path.write_text(
        json.dumps(asdict(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_markdown(packet, md_path)

    print(f"LISTING_MARGIN_JSON={json_path}")
    print(f"LISTING_MARGIN_MD={md_path}")
    print(f"PRODUCT={packet.product}")
    print(f"DECISION={packet.decision}")
    print(f"TOTAL_SCORE={packet.total_score}")
    print(f"LISTING_BULLET_COUNT={len(packet.listing_bullets)}")
    print(f"IMAGE_REQUIREMENT_COUNT={len(packet.image_requirements)}")
    print(f"MARGIN_SCENARIO_COUNT={len(packet.margin_scenarios)}")
    print(f"SUPPLIER_VALIDATION_COUNT={len(packet.supplier_validation_checklist)}")
    print(f"LISTING_READINESS_COUNT={len(packet.listing_readiness_checklist)}")
    print(f"HARD_REJECT_RULE_COUNT={len(packet.hard_reject_rules)}")
    print("A8_R42F_LISTING_MARGIN_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
