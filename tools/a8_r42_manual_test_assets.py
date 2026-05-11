from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ManualTestAssetPacket:
    product: str
    decision: str
    total_score: int
    test_mode: str
    primary_platforms: list[str]
    asset_folder_structure: list[str]
    filming_setup: list[str]
    shot_list: list[str]
    publish_assets: list[dict[str, str]]
    caption_bank: list[str]
    comment_reply_bank: list[str]
    daily_execution_checklist: list[str]
    metrics_to_track: list[str]
    advance_thresholds: list[str]
    reject_thresholds: list[str]
    next_actions_after_signal: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("OFFER_PACKET_MUST_BE_OBJECT")
    return raw


def build_manual_packet(offer_packet: dict[str, Any]) -> ManualTestAssetPacket:
    product = str(offer_packet["product"])
    decision = str(offer_packet["decision"])
    total_score = int(offer_packet["total_score"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"UNEXPECTED_PRODUCT={product}")

    return ManualTestAssetPacket(
        product=product,
        decision=decision,
        total_score=total_score,
        test_mode="LOCAL_MANUAL_FIRST_SIGNAL_TEST",
        primary_platforms=["TikTok", "Instagram Reels", "Facebook Marketplace optional"],
        asset_folder_structure=[
            "assets/a8_r42e/raw/",
            "assets/a8_r42e/edited/",
            "assets/a8_r42e/thumbnails/",
            "assets/a8_r42e/captions/",
            "assets/a8_r42e/results/",
        ],
        filming_setup=[
            "Use one fuzzy hoodie, sweater, blanket, or sofa fabric surface.",
            "Record in vertical 9:16.",
            "Use natural light or one strong lamp.",
            "Film close enough to show fuzz clearly.",
            "Clean only half the fabric first to create visible contrast.",
            "Do not overexplain; let the before/after carry the video.",
        ],
        shot_list=[
            "Shot 01: close-up of fuzzy fabric before.",
            "Shot 02: finger pointing at fabric pills/fuzz.",
            "Shot 03: lint remover enters frame.",
            "Shot 04: one slow pass over half the fabric.",
            "Shot 05: split before/after comparison.",
            "Shot 06: hand brushing cleaned side.",
            "Shot 07: final full fabric reveal.",
            "Shot 08: product in hand with quick CTA.",
        ],
        publish_assets=[
            {
                "asset_id": "V01_before_after_satisfying",
                "hook": "Your clothes are clean, but they still look old.",
                "format": "direct before/after demo",
                "cta": "Try fixing the fabric before replacing the item.",
            },
            {
                "asset_id": "V02_outfit_looks_cheap",
                "hook": "This is why some outfits look cheap even when they are clean.",
                "format": "problem-agitation-visual proof",
                "cta": "Clean the texture first. Then judge the outfit.",
            },
            {
                "asset_id": "V03_almost_threw_it_away",
                "hook": "I almost threw this sweater away.",
                "format": "rescue transformation",
                "cta": "This is useful if your clothes get fuzzy fast.",
            },
            {
                "asset_id": "V04_sofa_reset",
                "hook": "Your sofa might not be dirty. It might just be full of fuzz.",
                "format": "home fabric reset",
                "cta": "Use it on fabric surfaces that look tired.",
            },
            {
                "asset_id": "V05_budget_clothing_fix",
                "hook": "Cheap way to make old clothes look more presentable.",
                "format": "student/budget angle",
                "cta": "Save clothes before replacing them.",
            },
        ],
        caption_bank=[
            "Clean clothes can still look old if the fabric is fuzzy.",
            "Before replacing it, try fixing the fabric first.",
            "This before/after is way too satisfying.",
            "Small fabric reset, big visual difference.",
            "Useful for hoodies, sweaters, blankets, and sofas.",
            "The texture of your clothes changes the whole outfit.",
            "If your clothes get those tiny fabric balls, this is for that.",
            "Old fabric does not always mean ruined fabric.",
        ],
        comment_reply_bank=[
            "It is for lint, fuzz, and fabric pills that make clothes look old.",
            "A lint roller removes loose lint; this is for stuck fabric fuzz.",
            "Test a small area first and use it gently.",
            "It works best when the before/after is visible on camera.",
            "I would use it on sweaters, hoodies, blankets, and sofas first.",
            "The point is not magic; it is making fabric texture look cleaner.",
        ],
        daily_execution_checklist=[
            "Pick one fabric item with visible fuzz.",
            "Record at least two close before shots.",
            "Record one half-cleaned split test.",
            "Export one 9:16 video under 25 seconds.",
            "Post one video with one direct hook.",
            "Save comments, questions, clicks, and DMs in results notes.",
            "Do not change the product until at least five assets are tested.",
        ],
        metrics_to_track=[
            "views",
            "watch retention proxy",
            "saves",
            "comments",
            "DMs",
            "profile visits",
            "link clicks if available",
            "buy-intent comments",
        ],
        advance_thresholds=[
            "At least 3 buy-intent comments or DMs.",
            "At least 1 asset clearly outperforms baseline saves.",
            "Multiple comments mention clothes, sweaters, sofas, lint, fuzz, or link.",
            "People understand the product without long explanation.",
        ],
        reject_thresholds=[
            "No one asks where to buy after 5 clear assets.",
            "Viewers understand the product but show no buying intent.",
            "The before/after is not visually strong on camera.",
            "Supplier quality or safety cannot be controlled.",
        ],
        next_actions_after_signal=[
            "Build first lightweight landing/listing draft.",
            "Source 2 to 3 supplier options for quality comparison.",
            "Create price/margin worksheet.",
            "Prepare first paid or organic test batch only after signal.",
            "Keep all results local until cloud audit is available again.",
        ],
    )


def write_markdown(packet: ManualTestAssetPacket, path: Path) -> None:
    lines: list[str] = [
        "# A8-R42E Manual Test Asset Packet",
        "",
        "## Product",
        "",
        f"`{packet.product}`",
        "",
        "## Decision",
        "",
        f"- decision: `{packet.decision}`",
        f"- total_score: `{packet.total_score}`",
        f"- test_mode: `{packet.test_mode}`",
        "",
        "## Primary platforms",
        "",
    ]

    for item in packet.primary_platforms:
        lines.append(f"- {item}")

    sections = [
        ("Asset folder structure", packet.asset_folder_structure),
        ("Filming setup", packet.filming_setup),
        ("Shot list", packet.shot_list),
        ("Caption bank", packet.caption_bank),
        ("Comment reply bank", packet.comment_reply_bank),
        ("Daily execution checklist", packet.daily_execution_checklist),
        ("Metrics to track", packet.metrics_to_track),
        ("Advance thresholds", packet.advance_thresholds),
        ("Reject thresholds", packet.reject_thresholds),
        ("Next actions after signal", packet.next_actions_after_signal),
    ]

    for title, items in sections:
        lines.extend(["", f"## {title}", ""])
        for item in items:
            lines.append(f"- {item}")

    lines.extend(["", "## Publish assets", ""])
    for item in packet.publish_assets:
        lines.extend(
            [
                f"### {item['asset_id']}",
                "",
                f"- hook: {item['hook']}",
                f"- format: {item['format']}",
                f"- cta: {item['cta']}",
                "",
            ]
        )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offer-packet", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    offer_packet_path = Path(args.offer_packet).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    offer_packet = _load_json(offer_packet_path)
    packet = build_manual_packet(offer_packet)

    json_path = out_dir / "manual_test_asset_packet.json"
    md_path = out_dir / "manual_test_asset_packet.md"

    json_path.write_text(
        json.dumps(asdict(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_markdown(packet, md_path)

    print(f"MANUAL_PACKET_JSON={json_path}")
    print(f"MANUAL_PACKET_MD={md_path}")
    print(f"PRODUCT={packet.product}")
    print(f"DECISION={packet.decision}")
    print(f"TOTAL_SCORE={packet.total_score}")
    print(f"PLATFORM_COUNT={len(packet.primary_platforms)}")
    print(f"PUBLISH_ASSET_COUNT={len(packet.publish_assets)}")
    print(f"SHOT_COUNT={len(packet.shot_list)}")
    print(f"CAPTION_COUNT={len(packet.caption_bank)}")
    print(f"COMMENT_REPLY_COUNT={len(packet.comment_reply_bank)}")
    print(f"DAILY_CHECKLIST_COUNT={len(packet.daily_execution_checklist)}")
    print(f"ADVANCE_THRESHOLD_COUNT={len(packet.advance_thresholds)}")
    print(f"REJECT_THRESHOLD_COUNT={len(packet.reject_thresholds)}")
    print("A8_R42E_MANUAL_TEST_ASSETS_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
