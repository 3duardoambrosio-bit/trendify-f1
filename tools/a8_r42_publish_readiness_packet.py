from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReadinessGate:
    gate_id: str
    category: str
    requirement: str
    pass_value: str
    evidence_file: str
    hard_blocker: bool


@dataclass(frozen=True)
class PlatformReadinessCard:
    asset_id: str
    platform: str
    priority: int
    required_export_file: str
    required_caption_file: str
    required_publish_record_file: str
    required_metric_record_file: str
    publish_allowed: str
    no_go_if: str


@dataclass(frozen=True)
class PublishReadinessPacket:
    product: str
    decision: str
    total_score: int
    mode: str
    launch_authorization: str
    zero_spend_policy: str
    readiness_gates: list[ReadinessGate]
    platform_cards: list[PlatformReadinessCard]
    required_files: list[str]
    no_go_rules: list[str]
    metric_trigger_rules: list[str]
    final_decision_options: list[str]
    operator_commands: list[str]
    output_files: list[str]
    next_actions: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("INPUT_MUST_BE_OBJECT")
    return raw


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _assert_same_product(product: str, packets: dict[str, dict[str, Any]]) -> None:
    for label, packet in packets.items():
        actual = str(packet["product"])
        if actual != product:
            raise ValueError(f"{label.upper()}_PRODUCT_MISMATCH={actual}")


def _platform_cards(scaffold_packet: dict[str, Any]) -> list[PlatformReadinessCard]:
    assets = scaffold_packet.get("execution_assets")
    if not isinstance(assets, list) or len(assets) != 3:
        raise ValueError("EXECUTION_ASSET_COUNT_BAD")

    cards: list[PlatformReadinessCard] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("EXECUTION_ASSET_MUST_BE_OBJECT")

        cards.append(
            PlatformReadinessCard(
                asset_id=str(asset["asset_id"]),
                platform=str(asset["platform"]),
                priority=int(asset["priority"]),
                required_export_file=str(asset["required_export_file"]),
                required_caption_file=str(asset["caption_file"]),
                required_publish_record_file=str(asset["publish_record_file"]),
                required_metric_record_file=str(asset["metric_record_file"]),
                publish_allowed="ONLY_IF_ALL_PRE_PUBLISH_GATES_PASS",
                no_go_if="Missing export, missing caption, paid ad, supplier commitment, unsupported claim, or unclear product transformation.",
            )
        )

    return cards


def build_publish_readiness_packet(
    *,
    launch_packet: dict[str, Any],
    tracker_packet: dict[str, Any],
    supplier_packet: dict[str, Any],
    scaffold_packet: dict[str, Any],
    offline_packet: dict[str, Any],
) -> PublishReadinessPacket:
    product = str(launch_packet["product"])
    decision = str(launch_packet["decision"])
    total_score = int(launch_packet["total_score"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"UNEXPECTED_PRODUCT={product}")
    if decision != "ADVANCE":
        raise ValueError(f"UNEXPECTED_DECISION={decision}")
    if total_score != 59:
        raise ValueError(f"UNEXPECTED_TOTAL_SCORE={total_score}")

    _assert_same_product(
        product,
        {
            "tracker": tracker_packet,
            "supplier": supplier_packet,
            "scaffold": scaffold_packet,
            "offline": offline_packet,
        },
    )

    cards = _platform_cards(scaffold_packet)

    readiness_gates = [
        ReadinessGate("G01", "repo", "Repo clean before execution", "FINAL_STATUS_COUNT=0", "git_status_short.txt", True),
        ReadinessGate("G02", "asset", "Three priority assets selected", "ASSET_CARD_COUNT=3", "asset_execution_cards.csv", True),
        ReadinessGate("G03", "asset", "Three raw folders exist", "RAW_FOLDER_COUNT=3", "asset_manifest.json", True),
        ReadinessGate("G04", "asset", "Three caption placeholders exist", "CAPTION_FILE_COUNT=3", "A8_R42_EXECUTION_RECHARGEABLE_LINT_REMOVER/05_captions", True),
        ReadinessGate("G05", "asset", "Three publish records exist", "PUBLISH_RECORD_COUNT=3", "A8_R42_EXECUTION_RECHARGEABLE_LINT_REMOVER/06_publish_records", True),
        ReadinessGate("G06", "asset", "Three metric records exist", "METRIC_RECORD_COUNT=3", "A8_R42_EXECUTION_RECHARGEABLE_LINT_REMOVER/07_metrics", True),
        ReadinessGate("G07", "policy", "No paid ads", "NO_PAID_ADS=1", "pre_publish_gate_sheet.csv", True),
        ReadinessGate("G08", "policy", "No supplier commitment", "NO_SUPPLIER_COMMITMENT=1", "pre_publish_gate_sheet.csv", True),
        ReadinessGate("G09", "policy", "No inventory purchase", "NO_INVENTORY_PURCHASE=1", "pre_publish_gate_sheet.csv", True),
        ReadinessGate("G10", "content", "Before/after is visible", "BEFORE_AFTER_VISIBLE=1", "operator_runbook.md", True),
        ReadinessGate("G11", "content", "No unsupported claims", "NO_UNSUPPORTED_CLAIMS=1", "fail_fast_rules.md", True),
        ReadinessGate("G12", "tracking", "Metrics are numeric", "METRICS_NUMERIC=1", "metric_capture_rules.md", True),
        ReadinessGate("G13", "tracking", "Buy intent is separated from generic comments", "BUY_INTENT_SEPARATE=1", "metric_capture_rules.md", False),
        ReadinessGate("G14", "decision", "Decision rules exist", "DECISION_RULE_COUNT>=6", "decision_rules.md", True),
        ReadinessGate("G15", "audit", "Cloud audit deferred explicitly", "CLOUD_AUDIT_DEFERRED=1", "publish_readiness_packet.md", False),
    ]

    required_files = [
        "offline_execution_packet.json",
        "offline_execution_packet.md",
        "operator_runbook.md",
        "operator_steps.csv",
        "asset_execution_cards.csv",
        "pre_publish_gate_sheet.csv",
        "metric_capture_rules.md",
        "decision_rules.md",
        "fail_fast_rules.md",
        "execution_scaffold_packet.json",
        "asset_manifest.json",
        "asset_manifest.csv",
    ]

    no_go_rules = [
        "Do not publish if any export is missing.",
        "Do not publish if any caption is missing.",
        "Do not publish if the transformation is not visible.",
        "Do not publish if the clip contains unsupported claims.",
        "Do not publish if any paid promotion is enabled.",
        "Do not publish if supplier commitment is required.",
        "Do not publish if metric files cannot be updated.",
        "Do not publish if publish record cannot be filled.",
        "Do not publish if the asset creates safety confusion.",
        "Do not buy inventory from this packet.",
    ]

    metric_trigger_rules = [
        "Record views as an integer.",
        "Record likes as an integer.",
        "Record comments as an integer.",
        "Record saves as an integer.",
        "Record shares as an integer.",
        "Record profile visits as an integer.",
        "Record link clicks as an integer.",
        "Record buy-intent comments separately.",
        "Record DMs separately.",
        "Set signal score from evidence only.",
    ]

    final_decision_options = [
        "PUBLISH_ZERO_SPEND",
        "FIX_ASSET_BEFORE_PUBLISH",
        "RECORD_MORE_CONTENT",
        "ADVANCE_TO_SUPPLIER_REVIEW",
        "REJECT_ANGLE",
        "REJECT_PRODUCT",
    ]

    operator_commands = [
        "explorer.exe <execution_root>",
        "Open asset_manifest.csv",
        "Open caption_bank.md",
        "Open pre_publish_gate_sheet.csv",
        "Open publish record JSON files after posting",
        "Open metric record JSON files after signal capture",
    ]

    output_files = [
        "publish_readiness_packet.json",
        "publish_readiness_packet.md",
        "publish_readiness_gates.csv",
        "platform_readiness_cards.csv",
        "no_go_rules.md",
        "metric_trigger_rules.md",
        "final_decision_options.md",
        "operator_publish_commands.md",
    ]

    next_actions = [
        "Open execution root.",
        "Confirm all readiness gates.",
        "Record or place raw clips.",
        "Export three vertical videos.",
        "Fill captions.",
        "Publish zero-spend only.",
        "Capture metrics.",
        "Apply decision rules before supplier review.",
    ]

    return PublishReadinessPacket(
        product=product,
        decision=decision,
        total_score=total_score,
        mode="LOCAL_PUBLISH_READINESS_ZERO_SPEND",
        launch_authorization="READY_FOR_ZERO_SPEND_MANUAL_PUBLISH_ONLY",
        zero_spend_policy="No ads, no supplier commitment, no inventory purchase, no paid tools before manual signal.",
        readiness_gates=readiness_gates,
        platform_cards=cards,
        required_files=required_files,
        no_go_rules=no_go_rules,
        metric_trigger_rules=metric_trigger_rules,
        final_decision_options=final_decision_options,
        operator_commands=operator_commands,
        output_files=output_files,
        next_actions=next_actions,
    )


def write_packet_markdown(packet: PublishReadinessPacket, path: Path) -> None:
    lines: list[str] = [
        "# A8-R42L Publish Readiness Packet",
        "",
        "## Product",
        "",
        f"`{packet.product}`",
        "",
        "## Mode",
        "",
        f"`{packet.mode}`",
        "",
        "## Launch authorization",
        "",
        f"`{packet.launch_authorization}`",
        "",
        "## Zero-spend policy",
        "",
        packet.zero_spend_policy,
        "",
        "## Cloud status",
        "",
        "CLOUD_AUDIT_DEFERRED=1",
        "",
        "## Readiness gates",
        "",
    ]

    for gate in packet.readiness_gates:
        hard = "true" if gate.hard_blocker else "false"
        lines.extend(
            [
                f"### {gate.gate_id} — {gate.category}",
                "",
                f"- requirement: {gate.requirement}",
                f"- pass_value: `{gate.pass_value}`",
                f"- evidence_file: `{gate.evidence_file}`",
                f"- hard_blocker: `{hard}`",
                "",
            ]
        )

    lines.extend(["## Platform cards", ""])
    for card in packet.platform_cards:
        lines.extend(
            [
                f"### {card.asset_id} — {card.platform}",
                "",
                f"- priority: {card.priority}",
                f"- required_export_file: `{card.required_export_file}`",
                f"- required_caption_file: `{card.required_caption_file}`",
                f"- required_publish_record_file: `{card.required_publish_record_file}`",
                f"- required_metric_record_file: `{card.required_metric_record_file}`",
                f"- publish_allowed: `{card.publish_allowed}`",
                f"- no_go_if: {card.no_go_if}",
                "",
            ]
        )

    sections = [
        ("Required files", packet.required_files),
        ("No-go rules", packet.no_go_rules),
        ("Metric trigger rules", packet.metric_trigger_rules),
        ("Final decision options", packet.final_decision_options),
        ("Operator commands", packet.operator_commands),
        ("Next actions", packet.next_actions),
    ]

    for title, items in sections:
        lines.extend(["", f"## {title}", ""])
        for item in items:
            lines.append(f"- {item}")

    _write_text(path, "\n".join(lines))


def write_outputs(packet: PublishReadinessPacket, out_dir: Path) -> None:
    _write_csv(
        out_dir / "publish_readiness_gates.csv",
        ["gate_id", "category", "requirement", "pass_value", "evidence_file", "hard_blocker"],
        [asdict(gate) for gate in packet.readiness_gates],
    )

    _write_csv(
        out_dir / "platform_readiness_cards.csv",
        [
            "asset_id",
            "platform",
            "priority",
            "required_export_file",
            "required_caption_file",
            "required_publish_record_file",
            "required_metric_record_file",
            "publish_allowed",
            "no_go_if",
        ],
        [asdict(card) for card in packet.platform_cards],
    )

    _write_text(out_dir / "no_go_rules.md", "\n".join(["# No-go rules", "", *[f"- {rule}" for rule in packet.no_go_rules]]))
    _write_text(out_dir / "metric_trigger_rules.md", "\n".join(["# Metric trigger rules", "", *[f"- {rule}" for rule in packet.metric_trigger_rules]]))
    _write_text(out_dir / "final_decision_options.md", "\n".join(["# Final decision options", "", *[f"- {rule}" for rule in packet.final_decision_options]]))
    _write_text(out_dir / "operator_publish_commands.md", "\n".join(["# Operator publish commands", "", *[f"- {cmd}" for cmd in packet.operator_commands]]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-packet", required=True)
    parser.add_argument("--tracker-packet", required=True)
    parser.add_argument("--supplier-packet", required=True)
    parser.add_argument("--scaffold-packet", required=True)
    parser.add_argument("--offline-packet", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    launch_packet = _load_json(Path(args.launch_packet).resolve())
    tracker_packet = _load_json(Path(args.tracker_packet).resolve())
    supplier_packet = _load_json(Path(args.supplier_packet).resolve())
    scaffold_packet = _load_json(Path(args.scaffold_packet).resolve())
    offline_packet = _load_json(Path(args.offline_packet).resolve())

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    packet = build_publish_readiness_packet(
        launch_packet=launch_packet,
        tracker_packet=tracker_packet,
        supplier_packet=supplier_packet,
        scaffold_packet=scaffold_packet,
        offline_packet=offline_packet,
    )

    packet_json = out_dir / "publish_readiness_packet.json"
    packet_md = out_dir / "publish_readiness_packet.md"

    packet_json.write_text(
        json.dumps(asdict(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_packet_markdown(packet, packet_md)
    write_outputs(packet, out_dir)

    output_files = [p for p in out_dir.rglob("*") if p.is_file()]
    hard_blockers = [gate for gate in packet.readiness_gates if gate.hard_blocker]

    print(f"PUBLISH_READINESS_JSON={packet_json}")
    print(f"PUBLISH_READINESS_MD={packet_md}")
    print(f"PRODUCT={packet.product}")
    print(f"DECISION={packet.decision}")
    print(f"TOTAL_SCORE={packet.total_score}")
    print(f"LAUNCH_AUTHORIZATION={packet.launch_authorization}")
    print(f"READINESS_GATE_COUNT={len(packet.readiness_gates)}")
    print(f"HARD_BLOCKER_GATE_COUNT={len(hard_blockers)}")
    print(f"PLATFORM_CARD_COUNT={len(packet.platform_cards)}")
    print(f"REQUIRED_FILE_COUNT={len(packet.required_files)}")
    print(f"NO_GO_RULE_COUNT={len(packet.no_go_rules)}")
    print(f"METRIC_TRIGGER_RULE_COUNT={len(packet.metric_trigger_rules)}")
    print(f"FINAL_DECISION_OPTION_COUNT={len(packet.final_decision_options)}")
    print(f"OPERATOR_COMMAND_COUNT={len(packet.operator_commands)}")
    print(f"OUTPUT_FILE_COUNT={len(output_files)}")
    print("CLOUD_AUDIT_DEFERRED=1")
    print("ZERO_SPEND_ONLY=1")
    print("A8_R42L_PUBLISH_READINESS_PACKET_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
