from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FirstPublishAsset:
    asset_id: str
    platform: str
    priority: int
    hook: str
    opening_shot: str
    body_shots: list[str]
    caption: str
    cta: str
    success_metric: str
    fail_metric: str


@dataclass(frozen=True)
class LocalLaunchPacket:
    product: str
    decision: str
    total_score: int
    launch_mode: str
    zero_spend_rule: str
    first_publish_assets: list[FirstPublishAsset]
    preparation_checklist: list[str]
    recording_checklist: list[str]
    editing_checklist: list[str]
    publishing_checklist: list[str]
    result_logging_checklist: list[str]
    quality_gates: list[str]
    advance_conditions: list[str]
    stop_conditions: list[str]
    next_actions_after_first_publish: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("INPUT_MUST_BE_OBJECT")
    return raw


def _find_asset(manual_packet: dict[str, Any], asset_id: str) -> dict[str, Any]:
    assets = manual_packet.get("publish_assets")
    if not isinstance(assets, list):
        raise ValueError("PUBLISH_ASSETS_MISSING")

    for asset in assets:
        if isinstance(asset, dict) and asset.get("asset_id") == asset_id:
            return asset

    raise ValueError(f"PUBLISH_ASSET_NOT_FOUND={asset_id}")


def build_launch_packet(
    manual_packet: dict[str, Any],
    listing_packet: dict[str, Any],
    tracker_packet: dict[str, Any],
) -> LocalLaunchPacket:
    product = str(manual_packet["product"])
    listing_product = str(listing_packet["product"])
    tracker_product = str(tracker_packet["product"])
    decision = str(manual_packet["decision"])
    total_score = int(manual_packet["total_score"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"UNEXPECTED_PRODUCT={product}")
    if listing_product != product:
        raise ValueError(f"LISTING_PRODUCT_MISMATCH={listing_product}")
    if tracker_product != product:
        raise ValueError(f"TRACKER_PRODUCT_MISMATCH={tracker_product}")

    asset_1 = _find_asset(manual_packet, "V01_before_after_satisfying")
    asset_2 = _find_asset(manual_packet, "V02_outfit_looks_cheap")
    asset_3 = _find_asset(manual_packet, "V03_almost_threw_it_away")

    first_publish_assets = [
        FirstPublishAsset(
            asset_id=str(asset_1["asset_id"]),
            platform="TikTok",
            priority=1,
            hook=str(asset_1["hook"]),
            opening_shot="Extreme close-up of fuzzy fabric with obvious texture problem.",
            body_shots=[
                "Show the fabric before for 2 seconds.",
                "Run the lint remover on exactly half the fabric.",
                "Hold the split before/after shot steady.",
                "Brush the cleaned side with your hand.",
            ],
            caption="Clean clothes can still look old if the fabric is fuzzy.",
            cta=str(asset_1["cta"]),
            success_metric="At least one buy-intent comment, DM, save spike, or clear product question.",
            fail_metric="No one understands the transformation or asks about the product.",
        ),
        FirstPublishAsset(
            asset_id=str(asset_2["asset_id"]),
            platform="Instagram Reels",
            priority=2,
            hook=str(asset_2["hook"]),
            opening_shot="Outfit/fabric close-up that looks clean but visually worn.",
            body_shots=[
                "Point at fabric pills or fuzz.",
                "Show product touching the exact area.",
                "Cut to half-cleaned contrast.",
                "End with full item looking more presentable.",
            ],
            caption="The texture of your clothes changes the whole outfit.",
            cta=str(asset_2["cta"]),
            success_metric="Comments mention outfit, old clothes, lint, fuzz, sweater, hoodie, or link.",
            fail_metric="Only generic likes with no product or pain-specific comments.",
        ),
        FirstPublishAsset(
            asset_id=str(asset_3["asset_id"]),
            platform="TikTok",
            priority=3,
            hook=str(asset_3["hook"]),
            opening_shot="Old sweater/hoodie shown as almost discarded.",
            body_shots=[
                "Show the worst fuzzy section.",
                "Use one slow pass with the product.",
                "Show before/after side-by-side.",
                "Show final wearable look.",
            ],
            caption="Before replacing it, try fixing the fabric first.",
            cta=str(asset_3["cta"]),
            success_metric="Viewers ask where to buy, price, or whether it works on their clothes.",
            fail_metric="Viewers see it as satisfying only, with no buying curiosity.",
        ),
    ]

    preparation_checklist = [
        "Pick one hoodie, sweater, blanket, or sofa fabric with clearly visible fuzz.",
        "Charge the lint remover fully before recording.",
        "Clean the camera lens.",
        "Use vertical 9:16 framing.",
        "Prepare one plain background and one close light source.",
        "Do not record if the before/after is weak.",
        "Keep the product and fabric in the same frame for proof.",
    ]

    recording_checklist = [
        "Record a 2-second before close-up.",
        "Record one half-cleaned split test.",
        "Record one full pass with the product visible.",
        "Record a final steady before/after reveal.",
        "Record without long talking unless the visual is unclear.",
        "Avoid claims like permanent repair or guaranteed restoration.",
        "Keep the raw clip under control: short, clear, visual.",
    ]

    editing_checklist = [
        "Cut dead time from the start.",
        "Put the hook in the first second as text overlay.",
        "Show the before/after before the viewer loses attention.",
        "Keep final video under 25 seconds.",
        "Use captions that explain the problem in plain language.",
        "Do not hide the product usage.",
        "Export one final 9:16 file per asset_id.",
    ]

    publishing_checklist = [
        "Post first asset on TikTok.",
        "Post second asset on Instagram Reels.",
        "Use the exact hook from the launch packet.",
        "Use one simple CTA.",
        "Do not mention a discount before demand exists.",
        "Do not spend on ads.",
        "Save the post URL or local identifier immediately.",
    ]

    result_logging_checklist = [
        "Open result_tracker_publish_log.csv.",
        "Mark publish_status=POSTED for each published asset.",
        "Enter views, likes, comments, saves, shares, profile visits, link clicks, buy-intent comments, and DMs.",
        "Set signal_score using the score rules.",
        "Set decision=PENDING, ADVANCE_SIGNAL, WEAK_SIGNAL, or REJECT_SIGNAL.",
        "Write one blunt note: what worked, what failed, what people asked.",
        "Do not change product until the first three priority assets are reviewed.",
    ]

    quality_gates = [
        "FIRST_FRAME_CLEAR=1: the problem is visible immediately.",
        "BEFORE_AFTER_VISIBLE=1: the cleaned side is obviously different.",
        "PRODUCT_VISIBLE=1: viewer can understand what caused the result.",
        "CLAIM_RISK_LOW=1: no exaggerated repair or safety claims.",
        "ZERO_SPEND=1: no ads before signal.",
        "TRACKER_READY=1: publish log exists before posting.",
    ]

    advance_conditions = [
        "Advance if at least 3 buy-intent comments or DMs appear across first assets.",
        "Advance if one asset clearly outperforms others on saves or product-specific comments.",
        "Advance if viewers ask for link, price, availability, or whether it works on their item.",
        "Advance if before/after proof is strong enough to reuse as listing media.",
    ]

    stop_conditions = [
        "Stop if the visual before/after is weak even after better fabric selection.",
        "Stop if comments show confusion about what the product does.",
        "Stop if viewers understand it but no one asks where to buy.",
        "Stop if supplier validation later breaks safety, quality, or margin gates.",
    ]

    next_actions_after_first_publish = [
        "If strong signal: collect supplier options and validate landed cost.",
        "If medium signal: create two more visual angles before supplier work.",
        "If weak signal: improve fabric selection and retest.",
        "If no signal: reject or return to candidate engine.",
        "When cloud audit becomes available, submit A8-R42C through A8-R42H evidence bundles together.",
    ]

    return LocalLaunchPacket(
        product=product,
        decision=decision,
        total_score=total_score,
        launch_mode="LOCAL_ZERO_SPEND_FIRST_SIGNAL",
        zero_spend_rule="No ads, no inventory, no paid tools, no supplier commitment before manual signal.",
        first_publish_assets=first_publish_assets,
        preparation_checklist=preparation_checklist,
        recording_checklist=recording_checklist,
        editing_checklist=editing_checklist,
        publishing_checklist=publishing_checklist,
        result_logging_checklist=result_logging_checklist,
        quality_gates=quality_gates,
        advance_conditions=advance_conditions,
        stop_conditions=stop_conditions,
        next_actions_after_first_publish=next_actions_after_first_publish,
    )


def write_markdown(packet: LocalLaunchPacket, path: Path) -> None:
    lines: list[str] = [
        "# A8-R42H Local Launch Packet + First Publish Checklist",
        "",
        "## Product",
        "",
        f"`{packet.product}`",
        "",
        "## Launch mode",
        "",
        f"`{packet.launch_mode}`",
        "",
        "## Zero spend rule",
        "",
        packet.zero_spend_rule,
        "",
        "## Decision base",
        "",
        f"- decision: `{packet.decision}`",
        f"- total_score: `{packet.total_score}`",
        "",
        "## First publish assets",
        "",
    ]

    for asset in packet.first_publish_assets:
        lines.extend(
            [
                f"### Priority {asset.priority}: {asset.asset_id} — {asset.platform}",
                "",
                f"- hook: {asset.hook}",
                f"- opening_shot: {asset.opening_shot}",
                f"- caption: {asset.caption}",
                f"- cta: {asset.cta}",
                f"- success_metric: {asset.success_metric}",
                f"- fail_metric: {asset.fail_metric}",
                "",
                "#### Body shots",
                "",
            ]
        )
        for shot in asset.body_shots:
            lines.append(f"- {shot}")
        lines.append("")

    sections = [
        ("Preparation checklist", packet.preparation_checklist),
        ("Recording checklist", packet.recording_checklist),
        ("Editing checklist", packet.editing_checklist),
        ("Publishing checklist", packet.publishing_checklist),
        ("Result logging checklist", packet.result_logging_checklist),
        ("Quality gates", packet.quality_gates),
        ("Advance conditions", packet.advance_conditions),
        ("Stop conditions", packet.stop_conditions),
        ("Next actions after first publish", packet.next_actions_after_first_publish),
    ]

    for title, items in sections:
        lines.extend(["", f"## {title}", ""])
        for item in items:
            lines.append(f"- {item}")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual-packet", required=True)
    parser.add_argument("--listing-packet", required=True)
    parser.add_argument("--tracker-packet", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    manual_packet = _load_json(Path(args.manual_packet).resolve())
    listing_packet = _load_json(Path(args.listing_packet).resolve())
    tracker_packet = _load_json(Path(args.tracker_packet).resolve())

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    packet = build_launch_packet(manual_packet, listing_packet, tracker_packet)

    json_path = out_dir / "local_launch_packet.json"
    md_path = out_dir / "local_launch_packet.md"

    json_path.write_text(
        json.dumps(asdict(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_markdown(packet, md_path)

    print(f"LOCAL_LAUNCH_JSON={json_path}")
    print(f"LOCAL_LAUNCH_MD={md_path}")
    print(f"PRODUCT={packet.product}")
    print(f"DECISION={packet.decision}")
    print(f"TOTAL_SCORE={packet.total_score}")
    print(f"FIRST_PUBLISH_ASSET_COUNT={len(packet.first_publish_assets)}")
    print(f"PREPARATION_CHECK_COUNT={len(packet.preparation_checklist)}")
    print(f"RECORDING_CHECK_COUNT={len(packet.recording_checklist)}")
    print(f"EDITING_CHECK_COUNT={len(packet.editing_checklist)}")
    print(f"PUBLISHING_CHECK_COUNT={len(packet.publishing_checklist)}")
    print(f"RESULT_LOGGING_CHECK_COUNT={len(packet.result_logging_checklist)}")
    print(f"QUALITY_GATE_COUNT={len(packet.quality_gates)}")
    print(f"ADVANCE_CONDITION_COUNT={len(packet.advance_conditions)}")
    print(f"STOP_CONDITION_COUNT={len(packet.stop_conditions)}")
    print("A8_R42H_LOCAL_LAUNCH_PACKET_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
