from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OfferPacket:
    product: str
    decision: str
    total_score: int
    target_buyer: str
    one_sentence_offer: str
    core_promise: str
    positioning: str
    value_stack: list[str]
    short_form_hooks: list[str]
    short_video_scripts: list[dict[str, str]]
    listing_title_options: list[str]
    listing_bullets: list[str]
    objections_and_answers: list[dict[str, str]]
    manual_test_plan: list[str]
    reject_or_advance_rules: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("DECISION_PACKET_MUST_BE_OBJECT")
    return raw


def build_offer_packet(decision_packet: dict[str, Any]) -> OfferPacket:
    product = str(decision_packet["product"])
    decision = str(decision_packet["decision"])
    total_score = int(decision_packet["total_score"])
    target_buyer = str(decision_packet["target_buyer"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"UNEXPECTED_WINNING_PRODUCT={product}")

    one_sentence_offer = (
        "Make your clothes, sofas, and daily outfits look cleaner in minutes "
        "without replacing them or paying for expensive care."
    )

    core_promise = (
        "Turn fuzzy, tired-looking fabric into a cleaner, sharper, more presentable look fast."
    )

    positioning = (
        "A simple before/after fabric-cleanup gadget for people who hate looking careless "
        "because of lint, fuzz, pills, or worn-looking clothes."
    )

    value_stack = [
        "Visible before/after result.",
        "Works on clothes, sofas, blankets, and fabric surfaces.",
        "Rechargeable and portable.",
        "Easy to demonstrate in short-form content.",
        "Clear pain: clean clothes can still look old if fabric is fuzzy.",
    ]

    short_form_hooks = [
        "Your clothes are clean, but they still look old. This is why.",
        "This tiny gadget makes an old hoodie look way cleaner in seconds.",
        "I thought this sweater was ruined until I tried this.",
        "If your clothes get those little fabric balls, watch this.",
        "Stop throwing away clothes that only need this 20-second fix.",
        "This is the cheapest way to make your outfit look more put together.",
        "The before and after on this fabric cleaner is weirdly satisfying.",
        "POV: your sofa looks dirty but it is actually just full of lint and fuzz.",
        "Nobody talks about this, but fuzzy clothes make outfits look cheaper.",
        "I tested a lint remover on an old sweater. The result surprised me.",
    ]

    short_video_scripts = [
        {
            "name": "before_after_satisfying",
            "hook": "Your clothes are clean, but they still look old.",
            "body": "Show close-up of fuzzy fabric. Run the lint remover across half the surface. Show split before/after.",
            "cta": "If your clothes get fuzzy, this is the kind of fix you want before replacing them.",
        },
        {
            "name": "problem_agitation",
            "hook": "This is why some outfits look cheap even when they are clean.",
            "body": "Point to lint, fuzz, and fabric pills. Explain that the fabric texture makes the outfit look neglected.",
            "cta": "Clean the fabric first. Then judge the outfit.",
        },
        {
            "name": "old_item_rescue",
            "hook": "I almost threw this sweater away.",
            "body": "Show sweater before. Use remover. Show improved section. Compare side by side.",
            "cta": "Try fixing it before replacing it.",
        },
        {
            "name": "home_fabric_angle",
            "hook": "Your sofa might not be dirty. It might just be covered in fuzz.",
            "body": "Show sofa/blanket texture. Clean a small area. Show contrast.",
            "cta": "This is a quick home reset for fabric surfaces.",
        },
        {
            "name": "student_budget_angle",
            "hook": "Cheap way to make old clothes look more presentable.",
            "body": "Show one old hoodie, one pass, quick before/after.",
            "cta": "Useful if you want your clothes to last longer.",
        },
    ]

    listing_title_options = [
        "Rechargeable Electric Lint Remover for Clothes and Fabric",
        "Portable Fabric Shaver for Sweaters, Sofas, Blankets, and Outfits",
        "Electric Lint Remover — Make Old Fabric Look Cleaner Fast",
    ]

    listing_bullets = [
        "Removes lint, fuzz, and fabric pills from everyday clothes and home fabric.",
        "Helps old sweaters, hoodies, blankets, and sofas look cleaner and more presentable.",
        "Rechargeable design for easy use without disposable batteries.",
        "Portable size for quick fabric touch-ups at home.",
        "Strong before/after visual result for simple product demonstration.",
    ]

    objections_and_answers = [
        {
            "objection": "Can I just use a normal lint roller?",
            "answer": "A lint roller removes loose lint. This targets stuck fabric pills and fuzz that make clothes look worn.",
        },
        {
            "objection": "Will it damage clothes?",
            "answer": "Use it gently on compatible fabrics and test a small area first. The offer should clearly include safe-use guidance.",
        },
        {
            "objection": "Is this just a cheap gadget?",
            "answer": "The value is the visible before/after. Show real fabric improvement instead of relying on claims.",
        },
        {
            "objection": "Why buy this now?",
            "answer": "Because replacing clothes costs more than restoring items that only look old because of fuzz.",
        },
    ]

    manual_test_plan = [
        "Create one before/after demo video using a sweater, hoodie, blanket, or sofa fabric.",
        "Publish one problem-agitation hook: clean clothes that still look old.",
        "Publish one satisfying transformation clip.",
        "Track views, saves, comments, clicks, and direct questions.",
        "Reject if no one asks where to buy after multiple clear before/after posts.",
        "Advance if viewers comment about needing it, ask for link, or save the video.",
    ]

    reject_or_advance_rules = [
        "ADVANCE if at least 3 comments or DMs show buying intent.",
        "ADVANCE if before/after video gets materially higher saves than baseline content.",
        "REJECT if viewers understand the product but show no desire after repeated tests.",
        "REJECT if supplier quality, safety, or margin cannot be controlled.",
    ]

    return OfferPacket(
        product=product,
        decision=decision,
        total_score=total_score,
        target_buyer=target_buyer,
        one_sentence_offer=one_sentence_offer,
        core_promise=core_promise,
        positioning=positioning,
        value_stack=value_stack,
        short_form_hooks=short_form_hooks,
        short_video_scripts=short_video_scripts,
        listing_title_options=listing_title_options,
        listing_bullets=listing_bullets,
        objections_and_answers=objections_and_answers,
        manual_test_plan=manual_test_plan,
        reject_or_advance_rules=reject_or_advance_rules,
    )


def write_markdown(packet: OfferPacket, path: Path) -> None:
    lines: list[str] = [
        "# A8-R42D Offer + Content Hooks Packet",
        "",
        f"## Product",
        "",
        f"`{packet.product}`",
        "",
        "## Decision",
        "",
        f"- decision: `{packet.decision}`",
        f"- total_score: `{packet.total_score}`",
        f"- target_buyer: `{packet.target_buyer}`",
        "",
        "## One sentence offer",
        "",
        packet.one_sentence_offer,
        "",
        "## Core promise",
        "",
        packet.core_promise,
        "",
        "## Positioning",
        "",
        packet.positioning,
        "",
        "## Value stack",
        "",
    ]

    for item in packet.value_stack:
        lines.append(f"- {item}")

    lines.extend(["", "## Short-form hooks", ""])
    for index, hook in enumerate(packet.short_form_hooks, start=1):
        lines.append(f"{index}. {hook}")

    lines.extend(["", "## Short video scripts", ""])
    for script in packet.short_video_scripts:
        lines.extend(
            [
                f"### {script['name']}",
                "",
                f"- hook: {script['hook']}",
                f"- body: {script['body']}",
                f"- cta: {script['cta']}",
                "",
            ]
        )

    lines.extend(["## Listing title options", ""])
    for item in packet.listing_title_options:
        lines.append(f"- {item}")

    lines.extend(["", "## Listing bullets", ""])
    for item in packet.listing_bullets:
        lines.append(f"- {item}")

    lines.extend(["", "## Objections and answers", ""])
    for item in packet.objections_and_answers:
        lines.append(f"- objection: {item['objection']}")
        lines.append(f"  answer: {item['answer']}")

    lines.extend(["", "## Manual test plan", ""])
    for item in packet.manual_test_plan:
        lines.append(f"- {item}")

    lines.extend(["", "## Reject / advance rules", ""])
    for item in packet.reject_or_advance_rules:
        lines.append(f"- {item}")

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision-packet", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    decision_packet_path = Path(args.decision_packet).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    decision_packet = _load_json(decision_packet_path)
    packet = build_offer_packet(decision_packet)

    json_path = out_dir / "offer_content_hooks_packet.json"
    md_path = out_dir / "offer_content_hooks_packet.md"

    json_path.write_text(
        json.dumps(asdict(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_markdown(packet, md_path)

    print(f"OFFER_PACKET_JSON={json_path}")
    print(f"OFFER_PACKET_MD={md_path}")
    print(f"PRODUCT={packet.product}")
    print(f"DECISION={packet.decision}")
    print(f"TOTAL_SCORE={packet.total_score}")
    print(f"HOOK_COUNT={len(packet.short_form_hooks)}")
    print(f"SCRIPT_COUNT={len(packet.short_video_scripts)}")
    print(f"LISTING_BULLET_COUNT={len(packet.listing_bullets)}")
    print(f"OBJECTION_COUNT={len(packet.objections_and_answers)}")
    print("A8_R42D_OFFER_CONTENT_HOOKS_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
