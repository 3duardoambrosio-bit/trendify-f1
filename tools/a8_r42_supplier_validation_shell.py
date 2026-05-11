from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LandedCostScenario:
    scenario_id: str
    supplier_slot: str
    product_cost_usd: float
    shipping_cost_usd: float
    packaging_cost_usd: float
    payment_fee_usd: float
    defect_allowance_usd: float
    total_landed_cost_usd: float
    target_sell_price_usd: float
    gross_profit_usd: float
    gross_margin_pct: float
    break_even_cpa_usd: float
    decision: str


@dataclass(frozen=True)
class SupplierEvidenceSlot:
    supplier_slot: str
    supplier_name: str
    source_url_or_note: str
    validation_status: str
    product_match_status: str
    rechargeable_confirmed: str
    blade_guard_confirmed: str
    battery_claim_documented: str
    real_photos_available: str
    packaging_photos_available: str
    sample_available: str
    return_policy_clear: str
    defect_policy_clear: str
    landed_cost_supported: str
    safety_risk_status: str
    quality_risk_status: str
    decision: str
    missing_evidence: list[str]


@dataclass(frozen=True)
class SupplierValidationPacket:
    product: str
    decision: str
    total_score: int
    validation_mode: str
    zero_commitment_rule: str
    required_evidence_fields: list[str]
    supplier_slots: list[SupplierEvidenceSlot]
    landed_cost_scenarios: list[LandedCostScenario]
    supplier_validation_checklist: list[str]
    hard_disqualifiers: list[str]
    advance_requirements: list[str]
    evidence_capture_instructions: list[str]
    next_actions_after_validation: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("INPUT_MUST_BE_OBJECT")
    return raw


def _landed_cost(
    *,
    scenario_id: str,
    supplier_slot: str,
    product_cost_usd: float,
    shipping_cost_usd: float,
    packaging_cost_usd: float,
    payment_fee_usd: float,
    defect_allowance_usd: float,
    target_sell_price_usd: float,
) -> LandedCostScenario:
    total_landed = round(
        product_cost_usd
        + shipping_cost_usd
        + packaging_cost_usd
        + payment_fee_usd
        + defect_allowance_usd,
        2,
    )
    gross_profit = round(target_sell_price_usd - total_landed, 2)
    gross_margin_pct = round((gross_profit / target_sell_price_usd) * 100, 2)

    if gross_profit >= 9.0 and gross_margin_pct >= 45.0:
        decision = "MARGIN_OK_PENDING_EVIDENCE"
    elif gross_profit >= 6.0:
        decision = "MARGIN_WEAK_REVIEW_REQUIRED"
    else:
        decision = "MARGIN_REJECT"

    return LandedCostScenario(
        scenario_id=scenario_id,
        supplier_slot=supplier_slot,
        product_cost_usd=product_cost_usd,
        shipping_cost_usd=shipping_cost_usd,
        packaging_cost_usd=packaging_cost_usd,
        payment_fee_usd=payment_fee_usd,
        defect_allowance_usd=defect_allowance_usd,
        total_landed_cost_usd=total_landed,
        target_sell_price_usd=target_sell_price_usd,
        gross_profit_usd=gross_profit,
        gross_margin_pct=gross_margin_pct,
        break_even_cpa_usd=gross_profit,
        decision=decision,
    )


def _supplier_slot(slot: str) -> SupplierEvidenceSlot:
    missing = [
        "supplier source URL or local note",
        "real product photos",
        "rechargeable model confirmation",
        "blade guard / safety design confirmation",
        "unit cost",
        "shipping cost",
        "defect or return policy",
        "packaging evidence",
        "delivery estimate",
        "sample availability",
    ]

    return SupplierEvidenceSlot(
        supplier_slot=slot,
        supplier_name="TBD",
        source_url_or_note="TBD_LOCAL_ONLY",
        validation_status="NOT_VALIDATED",
        product_match_status="UNKNOWN",
        rechargeable_confirmed="UNKNOWN",
        blade_guard_confirmed="UNKNOWN",
        battery_claim_documented="UNKNOWN",
        real_photos_available="UNKNOWN",
        packaging_photos_available="UNKNOWN",
        sample_available="UNKNOWN",
        return_policy_clear="UNKNOWN",
        defect_policy_clear="UNKNOWN",
        landed_cost_supported="UNKNOWN",
        safety_risk_status="UNKNOWN",
        quality_risk_status="UNKNOWN",
        decision="PENDING_EVIDENCE",
        missing_evidence=missing,
    )


def build_supplier_validation_packet(
    listing_packet: dict[str, Any],
    launch_packet: dict[str, Any],
) -> SupplierValidationPacket:
    product = str(listing_packet["product"])
    launch_product = str(launch_packet["product"])
    decision = str(listing_packet["decision"])
    total_score = int(listing_packet["total_score"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"UNEXPECTED_PRODUCT={product}")
    if launch_product != product:
        raise ValueError(f"LAUNCH_PRODUCT_MISMATCH={launch_product}")

    required_evidence_fields = [
        "supplier_slot",
        "supplier_name",
        "source_url_or_note",
        "product_match_status",
        "rechargeable_confirmed",
        "blade_guard_confirmed",
        "battery_claim_documented",
        "real_photos_available",
        "packaging_photos_available",
        "sample_available",
        "return_policy_clear",
        "defect_policy_clear",
        "unit_cost_usd",
        "shipping_cost_usd",
        "estimated_delivery_days",
        "safety_risk_status",
        "quality_risk_status",
        "decision",
    ]

    supplier_slots = [
        _supplier_slot("SUPPLIER_A"),
        _supplier_slot("SUPPLIER_B"),
        _supplier_slot("SUPPLIER_C"),
    ]

    landed_cost_scenarios = [
        _landed_cost(
            scenario_id="A_base_target",
            supplier_slot="SUPPLIER_A",
            product_cost_usd=6.00,
            shipping_cost_usd=2.50,
            packaging_cost_usd=0.50,
            payment_fee_usd=0.85,
            defect_allowance_usd=0.50,
            target_sell_price_usd=18.99,
        ),
        _landed_cost(
            scenario_id="B_safe_margin",
            supplier_slot="SUPPLIER_B",
            product_cost_usd=5.50,
            shipping_cost_usd=2.25,
            packaging_cost_usd=0.50,
            payment_fee_usd=0.85,
            defect_allowance_usd=0.50,
            target_sell_price_usd=18.99,
        ),
        _landed_cost(
            scenario_id="C_reject_pressure",
            supplier_slot="SUPPLIER_C",
            product_cost_usd=8.50,
            shipping_cost_usd=3.25,
            packaging_cost_usd=0.75,
            payment_fee_usd=0.85,
            defect_allowance_usd=0.75,
            target_sell_price_usd=18.99,
        ),
    ]

    supplier_validation_checklist = [
        "Confirm the supplier sells the exact rechargeable electric lint remover category.",
        "Confirm the unit is rechargeable, not battery-only.",
        "Confirm blade guard or safety mesh is present.",
        "Collect real photos that are not only polished catalog renders.",
        "Collect packaging photos or packaging specs.",
        "Confirm charging cable, voltage, battery details, and included accessories.",
        "Confirm unit dimensions and weight.",
        "Confirm defect handling and return/replacement policy.",
        "Confirm shipping cost and estimated delivery range.",
        "Confirm total landed cost supports base-case economics.",
        "Reject if any safety claim is vague, exaggerated, or unsupported.",
        "Reject if supplier cannot provide evidence before commitment.",
    ]

    hard_disqualifiers = [
        "No rechargeable confirmation.",
        "No blade guard or unclear safety design.",
        "No real product photo evidence.",
        "Supplier refuses to clarify defect policy.",
        "Landed cost breaks minimum margin.",
        "Product appears materially different from listing promise.",
        "Shipping cost or delivery window is unclear.",
        "Safety or fabric-damage complaints appear in evidence.",
        "Supplier requires commitment before evidence.",
        "Any fake, copied, or inconsistent product media.",
    ]

    advance_requirements = [
        "At least one supplier has complete evidence fields.",
        "Base landed-cost scenario produces gross_profit_usd >= 9.00.",
        "Gross margin is >= 45 percent at base target price.",
        "Supplier can confirm rechargeable model and safety guard.",
        "Supplier risk status is not HIGH.",
        "Manual content signal exists before any paid test.",
    ]

    evidence_capture_instructions = [
        "Save supplier screenshots locally before entering data.",
        "Name screenshots by supplier slot and evidence type.",
        "Do not enter supplier as ADVANCE unless evidence exists.",
        "Do not use catalog claims as proof when real photos are missing.",
        "Keep all supplier evidence local while cloud audit is unavailable.",
        "When cloud audit returns, submit supplier shell plus evidence ZIP.",
    ]

    next_actions_after_validation = [
        "If supplier evidence passes: create first supplier comparison packet.",
        "If margin fails: adjust price scenario or reject product.",
        "If safety evidence fails: reject supplier immediately.",
        "If all suppliers fail: return to candidate engine without forcing launch.",
        "If supplier passes and manual signal exists: prepare lightweight listing implementation.",
    ]

    return SupplierValidationPacket(
        product=product,
        decision=decision,
        total_score=total_score,
        validation_mode="LOCAL_SUPPLIER_EVIDENCE_SHELL_NO_SUPPLIER_SELECTED",
        zero_commitment_rule="No supplier commitment, no inventory, no ads, no paid tools before evidence and manual signal.",
        required_evidence_fields=required_evidence_fields,
        supplier_slots=supplier_slots,
        landed_cost_scenarios=landed_cost_scenarios,
        supplier_validation_checklist=supplier_validation_checklist,
        hard_disqualifiers=hard_disqualifiers,
        advance_requirements=advance_requirements,
        evidence_capture_instructions=evidence_capture_instructions,
        next_actions_after_validation=next_actions_after_validation,
    )


def write_markdown(packet: SupplierValidationPacket, path: Path) -> None:
    lines: list[str] = [
        "# A8-R42I Supplier Validation Shell + Landed-Cost Evidence",
        "",
        "## Product",
        "",
        f"`{packet.product}`",
        "",
        "## Validation mode",
        "",
        f"`{packet.validation_mode}`",
        "",
        "## Zero commitment rule",
        "",
        packet.zero_commitment_rule,
        "",
        "## Decision base",
        "",
        f"- decision: `{packet.decision}`",
        f"- total_score: `{packet.total_score}`",
        "",
        "## Required evidence fields",
        "",
    ]

    for item in packet.required_evidence_fields:
        lines.append(f"- {item}")

    lines.extend(["", "## Supplier slots", ""])
    for supplier in packet.supplier_slots:
        lines.extend(
            [
                f"### {supplier.supplier_slot}",
                "",
                f"- supplier_name: {supplier.supplier_name}",
                f"- validation_status: {supplier.validation_status}",
                f"- product_match_status: {supplier.product_match_status}",
                f"- rechargeable_confirmed: {supplier.rechargeable_confirmed}",
                f"- blade_guard_confirmed: {supplier.blade_guard_confirmed}",
                f"- landed_cost_supported: {supplier.landed_cost_supported}",
                f"- decision: {supplier.decision}",
                "",
                "#### Missing evidence",
                "",
            ]
        )
        for item in supplier.missing_evidence:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend(["## Landed-cost scenarios", ""])
    for scenario in packet.landed_cost_scenarios:
        lines.extend(
            [
                f"### {scenario.scenario_id}",
                "",
                f"- supplier_slot: {scenario.supplier_slot}",
                f"- product_cost_usd: {scenario.product_cost_usd}",
                f"- shipping_cost_usd: {scenario.shipping_cost_usd}",
                f"- packaging_cost_usd: {scenario.packaging_cost_usd}",
                f"- payment_fee_usd: {scenario.payment_fee_usd}",
                f"- defect_allowance_usd: {scenario.defect_allowance_usd}",
                f"- total_landed_cost_usd: {scenario.total_landed_cost_usd}",
                f"- target_sell_price_usd: {scenario.target_sell_price_usd}",
                f"- gross_profit_usd: {scenario.gross_profit_usd}",
                f"- gross_margin_pct: {scenario.gross_margin_pct}",
                f"- break_even_cpa_usd: {scenario.break_even_cpa_usd}",
                f"- decision: {scenario.decision}",
                "",
            ]
        )

    sections = [
        ("Supplier validation checklist", packet.supplier_validation_checklist),
        ("Hard disqualifiers", packet.hard_disqualifiers),
        ("Advance requirements", packet.advance_requirements),
        ("Evidence capture instructions", packet.evidence_capture_instructions),
        ("Next actions after validation", packet.next_actions_after_validation),
    ]

    for title, items in sections:
        lines.extend(["", f"## {title}", ""])
        for item in items:
            lines.append(f"- {item}")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def write_supplier_csv(packet: SupplierValidationPacket, path: Path) -> None:
    fieldnames = [
        "supplier_slot",
        "supplier_name",
        "source_url_or_note",
        "validation_status",
        "product_match_status",
        "rechargeable_confirmed",
        "blade_guard_confirmed",
        "battery_claim_documented",
        "real_photos_available",
        "packaging_photos_available",
        "sample_available",
        "return_policy_clear",
        "defect_policy_clear",
        "landed_cost_supported",
        "safety_risk_status",
        "quality_risk_status",
        "decision",
        "missing_evidence",
    ]

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for supplier in packet.supplier_slots:
            row = asdict(supplier)
            row["missing_evidence"] = " | ".join(supplier.missing_evidence)
            writer.writerow(row)


def write_landed_cost_csv(packet: SupplierValidationPacket, path: Path) -> None:
    fieldnames = [
        "scenario_id",
        "supplier_slot",
        "product_cost_usd",
        "shipping_cost_usd",
        "packaging_cost_usd",
        "payment_fee_usd",
        "defect_allowance_usd",
        "total_landed_cost_usd",
        "target_sell_price_usd",
        "gross_profit_usd",
        "gross_margin_pct",
        "break_even_cpa_usd",
        "decision",
    ]

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for scenario in packet.landed_cost_scenarios:
            writer.writerow(asdict(scenario))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listing-packet", required=True)
    parser.add_argument("--launch-packet", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    listing_packet = _load_json(Path(args.listing_packet).resolve())
    launch_packet = _load_json(Path(args.launch_packet).resolve())

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    packet = build_supplier_validation_packet(listing_packet, launch_packet)

    json_path = out_dir / "supplier_validation_shell.json"
    md_path = out_dir / "supplier_validation_shell.md"
    supplier_csv_path = out_dir / "supplier_evidence_slots.csv"
    landed_cost_csv_path = out_dir / "landed_cost_scenarios.csv"

    json_path.write_text(
        json.dumps(asdict(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_markdown(packet, md_path)
    write_supplier_csv(packet, supplier_csv_path)
    write_landed_cost_csv(packet, landed_cost_csv_path)

    margin_ok = [
        scenario
        for scenario in packet.landed_cost_scenarios
        if scenario.decision == "MARGIN_OK_PENDING_EVIDENCE"
    ]

    print(f"SUPPLIER_VALIDATION_JSON={json_path}")
    print(f"SUPPLIER_VALIDATION_MD={md_path}")
    print(f"SUPPLIER_EVIDENCE_CSV={supplier_csv_path}")
    print(f"LANDED_COST_CSV={landed_cost_csv_path}")
    print(f"PRODUCT={packet.product}")
    print(f"DECISION={packet.decision}")
    print(f"TOTAL_SCORE={packet.total_score}")
    print(f"SUPPLIER_SLOT_COUNT={len(packet.supplier_slots)}")
    print(f"LANDED_COST_SCENARIO_COUNT={len(packet.landed_cost_scenarios)}")
    print(f"REQUIRED_EVIDENCE_FIELD_COUNT={len(packet.required_evidence_fields)}")
    print(f"SUPPLIER_VALIDATION_CHECK_COUNT={len(packet.supplier_validation_checklist)}")
    print(f"HARD_DISQUALIFIER_COUNT={len(packet.hard_disqualifiers)}")
    print(f"ADVANCE_REQUIREMENT_COUNT={len(packet.advance_requirements)}")
    print(f"EVIDENCE_CAPTURE_INSTRUCTION_COUNT={len(packet.evidence_capture_instructions)}")
    print(f"MARGIN_OK_SCENARIO_COUNT={len(margin_ok)}")
    print("A8_R42I_SUPPLIER_VALIDATION_SHELL_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
