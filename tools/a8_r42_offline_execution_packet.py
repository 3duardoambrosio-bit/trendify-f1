from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OperatorStep:
    step_id: str
    phase: str
    action: str
    evidence_required: str
    pass_condition: str
    fail_condition: str


@dataclass(frozen=True)
class AssetExecutionCard:
    asset_id: str
    platform: str
    priority: int
    hook: str
    raw_folder: str
    export_file: str
    caption_file: str
    publish_record_file: str
    metric_record_file: str
    recording_prompt: str
    edit_rule: str
    publish_rule: str
    success_signal: str
    stop_signal: str


@dataclass(frozen=True)
class OfflineExecutionPacket:
    product: str
    decision: str
    total_score: int
    mode: str
    zero_spend_rule: str
    operator_steps: list[OperatorStep]
    asset_cards: list[AssetExecutionCard]
    pre_publish_gates: list[str]
    publish_gates: list[str]
    metric_capture_rules: list[str]
    decision_rules: list[str]
    fail_fast_rules: list[str]
    files_to_open: list[str]
    outputs_created: list[str]
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


def _asset_cards(scaffold_packet: dict[str, Any]) -> list[AssetExecutionCard]:
    raw_assets = scaffold_packet.get("execution_assets")
    if not isinstance(raw_assets, list) or len(raw_assets) != 3:
        raise ValueError("EXECUTION_ASSET_COUNT_BAD")

    cards: list[AssetExecutionCard] = []
    for asset in raw_assets:
        if not isinstance(asset, dict):
            raise ValueError("EXECUTION_ASSET_MUST_BE_OBJECT")

        asset_id = str(asset["asset_id"])
        platform = str(asset["platform"])
        priority = int(asset["priority"])
        hook = str(asset["hook"])

        cards.append(
            AssetExecutionCard(
                asset_id=asset_id,
                platform=platform,
                priority=priority,
                hook=hook,
                raw_folder=str(asset["required_raw_folder"]),
                export_file=str(asset["required_export_file"]),
                caption_file=str(asset["caption_file"]),
                publish_record_file=str(asset["publish_record_file"]),
                metric_record_file=str(asset["metric_record_file"]),
                recording_prompt=(
                    "Record one clear vertical clip that proves the hook without explaining too much. "
                    "Show the fabric problem, show the lint remover solving it, and keep the result visible."
                ),
                edit_rule="Cut dead air, keep before/after obvious, no overproduced claims, no fake urgency.",
                publish_rule="Publish zero-spend only. Do not run ads. Do not promise unavailable inventory.",
                success_signal="Buy-intent comment, DM, save/share, profile visit, or direct question about where to buy.",
                stop_signal="Confusion, safety concern, no visible transformation, or comments saying the product looks fake/cheap.",
            )
        )

    return cards


def build_offline_execution_packet(
    *,
    launch_packet: dict[str, Any],
    tracker_packet: dict[str, Any],
    supplier_packet: dict[str, Any],
    scaffold_packet: dict[str, Any],
) -> OfflineExecutionPacket:
    product = str(launch_packet["product"])
    decision = str(launch_packet["decision"])
    total_score = int(launch_packet["total_score"])

    for label, packet in {
        "tracker": tracker_packet,
        "supplier": supplier_packet,
        "scaffold": scaffold_packet,
    }.items():
        if str(packet["product"]) != product:
            raise ValueError(f"{label.upper()}_PRODUCT_MISMATCH={packet['product']}")

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"UNEXPECTED_PRODUCT={product}")

    cards = _asset_cards(scaffold_packet)

    operator_steps = [
        OperatorStep("S01", "setup", "Open the execution root folder.", "execution root visible", "EXECUTION_ROOT_OPEN=1", "folder missing"),
        OperatorStep("S02", "setup", "Open asset manifest and caption bank.", "manifest and caption bank visible", "MANIFEST_OPEN=1", "missing asset manifest"),
        OperatorStep("S03", "recording", "Record raw clip for priority asset 1.", "raw clip saved", "RAW_CLIP_1_EXISTS=1", "raw clip missing"),
        OperatorStep("S04", "recording", "Record raw clip for priority asset 2.", "raw clip saved", "RAW_CLIP_2_EXISTS=1", "raw clip missing"),
        OperatorStep("S05", "recording", "Record raw clip for priority asset 3.", "raw clip saved", "RAW_CLIP_3_EXISTS=1", "raw clip missing"),
        OperatorStep("S06", "editing", "Export all three vertical videos.", "three exports saved", "EXPORT_COUNT=3", "less than three exports"),
        OperatorStep("S07", "copy", "Copy final captions into caption files.", "three caption files updated", "CAPTION_READY_COUNT=3", "caption missing"),
        OperatorStep("S08", "pre_publish", "Run pre-publish quality gates.", "quality gate sheet filled", "PRE_PUBLISH_GATE_PASS=1", "any hard gate fails"),
        OperatorStep("S09", "publish", "Publish zero-spend posts.", "publish record files filled", "PUBLISH_RECORD_COUNT=3", "paid ads or missing records"),
        OperatorStep("S10", "metrics", "Capture initial metrics.", "metric files filled", "METRIC_RECORD_COUNT=3", "metrics missing"),
        OperatorStep("S11", "decision", "Apply decision rules.", "decision log updated", "DECISION_LOG_UPDATED=1", "decision not recorded"),
        OperatorStep("S12", "supplier", "Only inspect supplier evidence after signal.", "supplier evidence folder updated only if signal exists", "SUPPLIER_GATE_RESPECTED=1", "supplier commitment before signal"),
    ]

    pre_publish_gates = [
        "RAW_CLIP_COUNT=3",
        "EXPORT_COUNT=3",
        "CAPTION_READY_COUNT=3",
        "NO_PAID_ADS=1",
        "NO_SUPPLIER_COMMITMENT=1",
        "NO_INVENTORY_PURCHASE=1",
        "BEFORE_AFTER_VISIBLE=1",
        "NO_UNSUPPORTED_CLAIMS=1",
        "SAFETY_RISK_LANGUAGE_CLEAN=1",
    ]

    publish_gates = [
        "PUBLISH_STATUS_RECORDED=1",
        "PLATFORM_RECORDED=1",
        "CAPTION_USED_RECORDED=1",
        "CTA_USED_RECORDED=1",
        "PUBLISH_URL_OR_LOCAL_ID_RECORDED=1",
        "ZERO_SPEND_CONFIRMED=1",
    ]

    metric_capture_rules = [
        "All numeric metrics default to 0, never blank.",
        "Signal score must be calculated from recorded evidence.",
        "Buy-intent comments are counted separately from generic comments.",
        "DMs count only if they ask about buying, price, link, availability, or product details.",
        "Negative safety comments trigger review even if views are high.",
        "Weak post performance is evidence, not failure.",
        "No supplier action is allowed without manual signal.",
    ]

    decision_rules = [
        "ADVANCE_TO_SUPPLIER_REVIEW if buy_intent_comments + DMs >= 2.",
        "RECORD_MORE_CONTENT if views are weak but comments are neutral or positive.",
        "REJECT_ANGLE if hook creates confusion or no visible transformation.",
        "REJECT_PRODUCT if safety concern appears repeatedly.",
        "KEEP_ZERO_SPEND if signal is unclear.",
        "DO_NOT_BUY_INVENTORY from this packet alone.",
    ]

    fail_fast_rules = [
        "Stop if any asset makes an unsupported medical, safety, or guaranteed-result claim.",
        "Stop if the product cannot be shown solving the fabric problem clearly.",
        "Stop if the clip depends on fake scarcity or fake discount.",
        "Stop if the platform record is missing.",
        "Stop if the metric record is not numeric.",
        "Stop if supplier commitment is attempted before signal.",
        "Stop if evidence files are overwritten instead of versioned.",
        "Stop if any paid promotion is introduced.",
    ]

    files_to_open = [
        "asset_manifest.json",
        "asset_manifest.csv",
        "05_captions/caption_bank.md",
        "06_publish_records/publish_log_template.csv",
        "07_metrics/metrics_template.csv",
        "09_decision_notes/decision_log.md",
    ]

    outputs_created = [
        "offline_execution_packet.json",
        "offline_execution_packet.md",
        "operator_runbook.md",
        "operator_steps.csv",
        "asset_execution_cards.csv",
        "pre_publish_gate_sheet.csv",
        "metric_capture_rules.md",
        "decision_rules.md",
        "fail_fast_rules.md",
    ]

    next_actions = [
        "Open the execution root folder.",
        "Use the three asset cards as the recording queue.",
        "Fill captions and publish records after each post.",
        "Capture metrics into metric records.",
        "Apply decision rules before supplier review.",
        "Keep cloud audit deferred until cloud access is available.",
    ]

    return OfflineExecutionPacket(
        product=product,
        decision=decision,
        total_score=total_score,
        mode="LOCAL_OFFLINE_OPERATOR_PACKET_ZERO_SPEND",
        zero_spend_rule="No ads, no supplier commitment, no inventory, no paid tools before manual signal.",
        operator_steps=operator_steps,
        asset_cards=cards,
        pre_publish_gates=pre_publish_gates,
        publish_gates=publish_gates,
        metric_capture_rules=metric_capture_rules,
        decision_rules=decision_rules,
        fail_fast_rules=fail_fast_rules,
        files_to_open=files_to_open,
        outputs_created=outputs_created,
        next_actions=next_actions,
    )


def write_markdown(packet: OfflineExecutionPacket, path: Path) -> None:
    lines: list[str] = [
        "# A8-R42K Offline Execution Packet",
        "",
        "## Product",
        "",
        f"`{packet.product}`",
        "",
        "## Mode",
        "",
        f"`{packet.mode}`",
        "",
        "## Zero-spend rule",
        "",
        packet.zero_spend_rule,
        "",
        "## Operator steps",
        "",
    ]

    for step in packet.operator_steps:
        lines.extend(
            [
                f"### {step.step_id} — {step.phase}",
                "",
                f"- action: {step.action}",
                f"- evidence_required: {step.evidence_required}",
                f"- pass_condition: `{step.pass_condition}`",
                f"- fail_condition: {step.fail_condition}",
                "",
            ]
        )

    lines.extend(["## Asset cards", ""])
    for asset in packet.asset_cards:
        lines.extend(
            [
                f"### {asset.asset_id} — {asset.platform}",
                "",
                f"- priority: {asset.priority}",
                f"- hook: {asset.hook}",
                f"- raw_folder: `{asset.raw_folder}`",
                f"- export_file: `{asset.export_file}`",
                f"- caption_file: `{asset.caption_file}`",
                f"- publish_record_file: `{asset.publish_record_file}`",
                f"- metric_record_file: `{asset.metric_record_file}`",
                f"- recording_prompt: {asset.recording_prompt}",
                f"- edit_rule: {asset.edit_rule}",
                f"- publish_rule: {asset.publish_rule}",
                f"- success_signal: {asset.success_signal}",
                f"- stop_signal: {asset.stop_signal}",
                "",
            ]
        )

    sections = [
        ("Pre-publish gates", packet.pre_publish_gates),
        ("Publish gates", packet.publish_gates),
        ("Metric capture rules", packet.metric_capture_rules),
        ("Decision rules", packet.decision_rules),
        ("Fail-fast rules", packet.fail_fast_rules),
        ("Files to open", packet.files_to_open),
        ("Next actions", packet.next_actions),
    ]

    for title, items in sections:
        lines.extend(["", f"## {title}", ""])
        for item in items:
            lines.append(f"- {item}")

    _write_text(path, "\n".join(lines))


def write_csv_outputs(packet: OfflineExecutionPacket, out_dir: Path) -> None:
    _write_csv(
        out_dir / "operator_steps.csv",
        ["step_id", "phase", "action", "evidence_required", "pass_condition", "fail_condition"],
        [asdict(step) for step in packet.operator_steps],
    )

    _write_csv(
        out_dir / "asset_execution_cards.csv",
        [
            "asset_id",
            "platform",
            "priority",
            "hook",
            "raw_folder",
            "export_file",
            "caption_file",
            "publish_record_file",
            "metric_record_file",
            "recording_prompt",
            "edit_rule",
            "publish_rule",
            "success_signal",
            "stop_signal",
        ],
        [asdict(asset) for asset in packet.asset_cards],
    )

    _write_csv(
        out_dir / "pre_publish_gate_sheet.csv",
        ["gate_id", "gate", "status", "evidence_note"],
        [
            {"gate_id": f"G{i + 1:02d}", "gate": gate, "status": "PENDING", "evidence_note": ""}
            for i, gate in enumerate(packet.pre_publish_gates)
        ],
    )


def write_supporting_markdown(packet: OfflineExecutionPacket, out_dir: Path) -> None:
    _write_text(
        out_dir / "operator_runbook.md",
        "\n".join(
            [
                "# Operator runbook",
                "",
                "Use this packet as the offline operating checklist.",
                "",
                "## Rule",
                "",
                packet.zero_spend_rule,
                "",
                "## Sequence",
                "",
                *[f"- {step.step_id}: {step.action}" for step in packet.operator_steps],
            ]
        ),
    )

    _write_text(
        out_dir / "metric_capture_rules.md",
        "\n".join(["# Metric capture rules", "", *[f"- {item}" for item in packet.metric_capture_rules]]),
    )

    _write_text(
        out_dir / "decision_rules.md",
        "\n".join(["# Decision rules", "", *[f"- {item}" for item in packet.decision_rules]]),
    )

    _write_text(
        out_dir / "fail_fast_rules.md",
        "\n".join(["# Fail-fast rules", "", *[f"- {item}" for item in packet.fail_fast_rules]]),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-packet", required=True)
    parser.add_argument("--tracker-packet", required=True)
    parser.add_argument("--supplier-packet", required=True)
    parser.add_argument("--scaffold-packet", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    launch_packet = _load_json(Path(args.launch_packet).resolve())
    tracker_packet = _load_json(Path(args.tracker_packet).resolve())
    supplier_packet = _load_json(Path(args.supplier_packet).resolve())
    scaffold_packet = _load_json(Path(args.scaffold_packet).resolve())

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    packet = build_offline_execution_packet(
        launch_packet=launch_packet,
        tracker_packet=tracker_packet,
        supplier_packet=supplier_packet,
        scaffold_packet=scaffold_packet,
    )

    packet_json = out_dir / "offline_execution_packet.json"
    packet_md = out_dir / "offline_execution_packet.md"

    packet_json.write_text(
        json.dumps(asdict(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_markdown(packet, packet_md)
    write_csv_outputs(packet, out_dir)
    write_supporting_markdown(packet, out_dir)

    output_files = [p for p in out_dir.rglob("*") if p.is_file()]

    print(f"OFFLINE_EXECUTION_JSON={packet_json}")
    print(f"OFFLINE_EXECUTION_MD={packet_md}")
    print(f"PRODUCT={packet.product}")
    print(f"DECISION={packet.decision}")
    print(f"TOTAL_SCORE={packet.total_score}")
    print(f"OPERATOR_STEP_COUNT={len(packet.operator_steps)}")
    print(f"ASSET_CARD_COUNT={len(packet.asset_cards)}")
    print(f"PRE_PUBLISH_GATE_COUNT={len(packet.pre_publish_gates)}")
    print(f"PUBLISH_GATE_COUNT={len(packet.publish_gates)}")
    print(f"METRIC_CAPTURE_RULE_COUNT={len(packet.metric_capture_rules)}")
    print(f"DECISION_RULE_COUNT={len(packet.decision_rules)}")
    print(f"FAIL_FAST_RULE_COUNT={len(packet.fail_fast_rules)}")
    print(f"FILES_TO_OPEN_COUNT={len(packet.files_to_open)}")
    print(f"OUTPUTS_CREATED_COUNT={len(packet.outputs_created)}")
    print(f"OFFLINE_OUTPUT_FILE_COUNT={len(output_files)}")
    print("A8_R42K_OFFLINE_EXECUTION_PACKET_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
