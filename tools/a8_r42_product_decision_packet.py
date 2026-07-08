from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Candidate:
    name: str
    target_buyer: str
    pain_or_desire: str
    estimated_margin_pct: float
    wow_factor: int
    problem_intensity: int
    content_potential: int
    supplier_risk: int
    competition_risk: int
    complexity_risk: int


@dataclass(frozen=True)
class DecisionPacket:
    product: str
    decision: str
    total_score: int
    score_breakdown: dict[str, int]
    target_buyer: str
    core_promise: str
    offer_angle: str
    objections: list[str]
    content_angles: list[str]
    first_test_checklist: list[str]
    reject_or_advance_rule: str


def clamp_0_10(value: Any) -> int:
    number = int(value)
    if number < 0:
        return 0
    if number > 10:
        return 10
    return number


def load_candidates(path: Path) -> list[Candidate]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("INPUT_MUST_BE_LIST_OF_CANDIDATES")

    candidates: list[Candidate] = []
    for item in raw:
        candidates.append(
            Candidate(
                name=str(item["name"]),
                target_buyer=str(item["target_buyer"]),
                pain_or_desire=str(item["pain_or_desire"]),
                estimated_margin_pct=float(item["estimated_margin_pct"]),
                wow_factor=clamp_0_10(item["wow_factor"]),
                problem_intensity=clamp_0_10(item["problem_intensity"]),
                content_potential=clamp_0_10(item["content_potential"]),
                supplier_risk=clamp_0_10(item["supplier_risk"]),
                competition_risk=clamp_0_10(item["competition_risk"]),
                complexity_risk=clamp_0_10(item["complexity_risk"]),
            )
        )
    return candidates


def score_candidate(candidate: Candidate) -> tuple[int, dict[str, int]]:
    margin_score = 10 if candidate.estimated_margin_pct >= 55 else 8 if candidate.estimated_margin_pct >= 45 else 6 if candidate.estimated_margin_pct >= 35 else 3

    positive = {
        "margin": margin_score * 3,
        "wow_factor": candidate.wow_factor * 2,
        "problem_intensity": candidate.problem_intensity * 3,
        "content_potential": candidate.content_potential * 2,
    }
    negative = {
        "supplier_risk_penalty": candidate.supplier_risk * -2,
        "competition_risk_penalty": candidate.competition_risk * -2,
        "complexity_risk_penalty": candidate.complexity_risk * -2,
    }

    breakdown = {**positive, **negative}
    total = sum(breakdown.values())
    return total, breakdown


def build_packet(candidate: Candidate) -> DecisionPacket:
    total, breakdown = score_candidate(candidate)
    decision = "ADVANCE" if total >= 45 else "WATCHLIST" if total >= 30 else "REJECT"

    core_promise = f"Help {candidate.target_buyer} solve or satisfy: {candidate.pain_or_desire}."
    offer_angle = f"Position {candidate.name} as the fastest visible improvement for {candidate.target_buyer}."

    objections = [
        "Why should I trust this product?",
        "Can I get this cheaper elsewhere?",
        "Will it actually solve my problem?",
        "How fast do I receive it?",
    ]

    content_angles = [
        f"Before/after demonstration for {candidate.pain_or_desire}",
        f"Problem agitation: what happens when {candidate.target_buyer} ignores this",
        f"Quick demo: 3 seconds to understand why {candidate.name} is useful",
        "Comparison angle: cheap alternative vs better result",
        "Objection handling: does it actually work?",
    ]

    first_test_checklist = [
        "Confirm landed cost and estimated margin.",
        "Find 3 competitor listings and record price range.",
        "Write 1 landing/listing headline.",
        "Write 3 short-form video hooks.",
        "Prepare 1 manual test post/ad draft.",
        "Define reject rule before publishing.",
    ]

    reject_or_advance_rule = (
        "ADVANCE only if margin is viable, supplier risk is controllable, "
        "and at least 3 content angles are publishable without heavy production."
    )

    return DecisionPacket(
        product=candidate.name,
        decision=decision,
        total_score=total,
        score_breakdown=breakdown,
        target_buyer=candidate.target_buyer,
        core_promise=core_promise,
        offer_angle=offer_angle,
        objections=objections,
        content_angles=content_angles,
        first_test_checklist=first_test_checklist,
        reject_or_advance_rule=reject_or_advance_rule,
    )


def write_markdown(packet: DecisionPacket, path: Path) -> None:
    lines = [
        "# Product Decision Packet",
        "",
        f"## Product: {packet.product}",
        "",
        f"- decision: `{packet.decision}`",
        f"- total_score: `{packet.total_score}`",
        f"- target_buyer: `{packet.target_buyer}`",
        "",
        "## Score breakdown",
        "",
    ]

    for key, value in packet.score_breakdown.items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(
        [
            "",
            "## Core promise",
            "",
            packet.core_promise,
            "",
            "## Offer angle",
            "",
            packet.offer_angle,
            "",
            "## Objections",
            "",
        ]
    )

    for item in packet.objections:
        lines.append(f"- {item}")

    lines.extend(["", "## Content angles", ""])
    for item in packet.content_angles:
        lines.append(f"- {item}")

    lines.extend(["", "## First test checklist", ""])
    for item in packet.first_test_checklist:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## Reject / advance rule",
            "",
            packet.reject_or_advance_rule,
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = load_candidates(input_path)
    packets = [build_packet(candidate) for candidate in candidates]
    packets.sort(key=lambda packet: packet.total_score, reverse=True)

    best = packets[0]
    json_path = out_dir / "product_decision_packets.json"
    best_json_path = out_dir / "best_product_decision_packet.json"
    best_md_path = out_dir / "best_product_decision_packet.md"

    json_path.write_text(
        json.dumps([asdict(packet) for packet in packets], ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    best_json_path.write_text(json.dumps(asdict(best), ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    write_markdown(best, best_md_path)

    print(f"PACKETS_JSON={json_path}")
    print(f"BEST_PACKET_JSON={best_json_path}")
    print(f"BEST_PACKET_MD={best_md_path}")
    print(f"CANDIDATE_COUNT={len(candidates)}")
    print(f"BEST_PRODUCT={best.product}")
    print(f"BEST_DECISION={best.decision}")
    print(f"BEST_TOTAL_SCORE={best.total_score}")
    print("A8_R42B_PRODUCT_DECISION_PACKET_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
