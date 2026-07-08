from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PublishLogEntry:
    asset_id: str
    platform: str
    publish_status: str
    hook: str
    format: str
    cta: str
    views: int
    likes: int
    comments: int
    saves: int
    shares: int
    profile_visits: int
    link_clicks: int
    buy_intent_comments: int
    dms: int
    signal_score: int
    decision: str
    notes: str


@dataclass(frozen=True)
class TrackerPacket:
    product: str
    decision: str
    total_score: int
    tracker_mode: str
    tracked_platforms: list[str]
    metric_fields: list[str]
    publish_log_entries: list[PublishLogEntry]
    signal_score_rules: list[str]
    advance_rules: list[str]
    reject_rules: list[str]
    review_checklist: list[str]
    next_actions: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("INPUT_MUST_BE_OBJECT")
    return raw


def _empty_entry(asset: dict[str, Any], platform: str) -> PublishLogEntry:
    return PublishLogEntry(
        asset_id=str(asset["asset_id"]),
        platform=platform,
        publish_status="NOT_POSTED",
        hook=str(asset["hook"]),
        format=str(asset["format"]),
        cta=str(asset["cta"]),
        views=0,
        likes=0,
        comments=0,
        saves=0,
        shares=0,
        profile_visits=0,
        link_clicks=0,
        buy_intent_comments=0,
        dms=0,
        signal_score=0,
        decision="PENDING",
        notes="Fill after publishing.",
    )


def build_tracker_packet(
    manual_packet: dict[str, Any],
    listing_packet: dict[str, Any],
) -> TrackerPacket:
    product = str(manual_packet["product"])
    listing_product = str(listing_packet["product"])
    decision = str(manual_packet["decision"])
    total_score = int(manual_packet["total_score"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"UNEXPECTED_PRODUCT={product}")
    if listing_product != product:
        raise ValueError(f"LISTING_PRODUCT_MISMATCH={listing_product}")

    publish_assets = manual_packet.get("publish_assets")
    if not isinstance(publish_assets, list) or len(publish_assets) < 5:
        raise ValueError("PUBLISH_ASSETS_TOO_LOW")

    tracked_platforms = ["TikTok", "Instagram Reels"]
    entries: list[PublishLogEntry] = []

    for asset in publish_assets:
        if not isinstance(asset, dict):
            raise ValueError("PUBLISH_ASSET_MUST_BE_OBJECT")
        for platform in tracked_platforms:
            entries.append(_empty_entry(asset, platform))

    metric_fields = [
        "asset_id",
        "platform",
        "publish_status",
        "hook",
        "format",
        "cta",
        "views",
        "likes",
        "comments",
        "saves",
        "shares",
        "profile_visits",
        "link_clicks",
        "buy_intent_comments",
        "dms",
        "signal_score",
        "decision",
        "notes",
    ]

    signal_score_rules = [
        "+3 for each buy-intent comment.",
        "+3 for each DM asking for link, price, availability, or where to buy.",
        "+2 if saves are visibly stronger than baseline.",
        "+2 if comments mention the exact pain: lint, fuzz, fabric balls, old-looking clothes, sweater, sofa, blanket.",
        "+1 if viewers tag other people or share the post.",
        "-3 if comments show confusion about what the product does.",
        "-5 if safety, fabric damage, or quality concerns dominate comments.",
    ]

    advance_rules = [
        "ADVANCE if total signal_score across assets is >= 9.",
        "ADVANCE if at least 3 buy-intent comments or DMs appear.",
        "ADVANCE if one asset produces clear save/comment outperformance.",
        "ADVANCE if viewers understand the before/after without explanation.",
    ]

    reject_rules = [
        "REJECT if 10 posted entries produce zero buy-intent comments and zero DMs.",
        "REJECT if before/after proof is not visible enough.",
        "REJECT if viewers understand the product but do not show buying intent.",
        "REJECT if supplier quality, safety, or landed cost breaks the base-case economics.",
    ]

    review_checklist = [
        "Confirm every posted asset has publish_status=POSTED.",
        "Enter numeric metrics only; leave unknown as 0.",
        "Mark buy-intent comments separately from normal comments.",
        "Mark DMs only when they show real purchase curiosity.",
        "Update decision field per entry: PENDING, ADVANCE_SIGNAL, WEAK_SIGNAL, or REJECT_SIGNAL.",
        "Review all entries together before changing product.",
    ]

    next_actions = [
        "If ADVANCE: collect supplier options and validate landed cost.",
        "If ADVANCE: turn best hook into first listing hero section.",
        "If WEAK: create two more before/after angles before rejecting.",
        "If REJECT: document why and return to candidate engine.",
        "Do not spend on ads until organic/manual signal exists.",
    ]

    return TrackerPacket(
        product=product,
        decision=decision,
        total_score=total_score,
        tracker_mode="LOCAL_MANUAL_SIGNAL_TRACKING",
        tracked_platforms=tracked_platforms,
        metric_fields=metric_fields,
        publish_log_entries=entries,
        signal_score_rules=signal_score_rules,
        advance_rules=advance_rules,
        reject_rules=reject_rules,
        review_checklist=review_checklist,
        next_actions=next_actions,
    )


def write_markdown(packet: TrackerPacket, path: Path) -> None:
    lines: list[str] = [
        "# A8-R42G Result Tracker + Publish Log",
        "",
        "## Product",
        "",
        f"`{packet.product}`",
        "",
        "## Tracker mode",
        "",
        f"`{packet.tracker_mode}`",
        "",
        "## Decision base",
        "",
        f"- decision: `{packet.decision}`",
        f"- total_score: `{packet.total_score}`",
        "",
        "## Tracked platforms",
        "",
    ]

    for item in packet.tracked_platforms:
        lines.append(f"- {item}")

    sections = [
        ("Metric fields", packet.metric_fields),
        ("Signal score rules", packet.signal_score_rules),
        ("Advance rules", packet.advance_rules),
        ("Reject rules", packet.reject_rules),
        ("Review checklist", packet.review_checklist),
        ("Next actions", packet.next_actions),
    ]

    for title, items in sections:
        lines.extend(["", f"## {title}", ""])
        for item in items:
            lines.append(f"- {item}")

    lines.extend(["", "## Publish log entries", ""])

    for entry in packet.publish_log_entries:
        lines.extend(
            [
                f"### {entry.asset_id} — {entry.platform}",
                "",
                f"- publish_status: {entry.publish_status}",
                f"- hook: {entry.hook}",
                f"- format: {entry.format}",
                f"- cta: {entry.cta}",
                f"- views: {entry.views}",
                f"- likes: {entry.likes}",
                f"- comments: {entry.comments}",
                f"- saves: {entry.saves}",
                f"- shares: {entry.shares}",
                f"- profile_visits: {entry.profile_visits}",
                f"- link_clicks: {entry.link_clicks}",
                f"- buy_intent_comments: {entry.buy_intent_comments}",
                f"- dms: {entry.dms}",
                f"- signal_score: {entry.signal_score}",
                f"- decision: {entry.decision}",
                f"- notes: {entry.notes}",
                "",
            ]
        )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def write_csv(packet: TrackerPacket, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=packet.metric_fields)
        writer.writeheader()
        for entry in packet.publish_log_entries:
            writer.writerow(asdict(entry))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual-packet", required=True)
    parser.add_argument("--listing-packet", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    manual_packet = _load_json(Path(args.manual_packet).resolve())
    listing_packet = _load_json(Path(args.listing_packet).resolve())

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    packet = build_tracker_packet(manual_packet, listing_packet)

    json_path = out_dir / "result_tracker_publish_log.json"
    md_path = out_dir / "result_tracker_publish_log.md"
    csv_path = out_dir / "result_tracker_publish_log.csv"

    json_path.write_text(
        json.dumps(asdict(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_markdown(packet, md_path)
    write_csv(packet, csv_path)

    print(f"RESULT_TRACKER_JSON={json_path}")
    print(f"RESULT_TRACKER_MD={md_path}")
    print(f"RESULT_TRACKER_CSV={csv_path}")
    print(f"PRODUCT={packet.product}")
    print(f"DECISION={packet.decision}")
    print(f"TOTAL_SCORE={packet.total_score}")
    print(f"TRACKED_PLATFORM_COUNT={len(packet.tracked_platforms)}")
    print(f"METRIC_FIELD_COUNT={len(packet.metric_fields)}")
    print(f"PUBLISH_LOG_ENTRY_COUNT={len(packet.publish_log_entries)}")
    print(f"SIGNAL_SCORE_RULE_COUNT={len(packet.signal_score_rules)}")
    print(f"ADVANCE_RULE_COUNT={len(packet.advance_rules)}")
    print(f"REJECT_RULE_COUNT={len(packet.reject_rules)}")
    print(f"REVIEW_CHECKLIST_COUNT={len(packet.review_checklist)}")
    print("A8_R42G_RESULT_TRACKER_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
