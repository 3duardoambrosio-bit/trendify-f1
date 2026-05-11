from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExecutionAsset:
    asset_id: str
    platform: str
    priority: int
    hook: str
    required_raw_folder: str
    required_export_file: str
    caption_file: str
    publish_record_file: str
    metric_record_file: str
    status: str


@dataclass(frozen=True)
class ExecutionScaffoldPacket:
    product: str
    decision: str
    total_score: int
    scaffold_mode: str
    root_folder_name: str
    directory_plan: list[str]
    execution_assets: list[ExecutionAsset]
    file_manifest: list[str]
    operator_checklist: list[str]
    quality_gates: list[str]
    publish_record_fields: list[str]
    metric_record_fields: list[str]
    evidence_rules: list[str]
    next_actions: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("INPUT_MUST_BE_OBJECT")
    return raw


def _slug(value: str) -> str:
    safe: list[str] = []
    for char in value.lower():
        if char.isalnum():
            safe.append(char)
        elif char in {" ", "-", "_"}:
            safe.append("_")
    collapsed = "_".join(part for part in "".join(safe).split("_") if part)
    return collapsed or "asset"


def _platform_slug(value: str) -> str:
    return _slug(value)


def _resolve_out_path(out_dir: Path, relative_path: str) -> Path:
    candidate = (out_dir / relative_path).resolve()
    out_root = out_dir.resolve()

    if out_root not in candidate.parents and candidate != out_root:
        raise ValueError(f"PATH_ESCAPES_OUT_DIR={candidate}")

    return candidate


def build_execution_scaffold_packet(
    launch_packet: dict[str, Any],
    tracker_packet: dict[str, Any],
    supplier_packet: dict[str, Any],
) -> ExecutionScaffoldPacket:
    product = str(launch_packet["product"])
    tracker_product = str(tracker_packet["product"])
    supplier_product = str(supplier_packet["product"])
    decision = str(launch_packet["decision"])
    total_score = int(launch_packet["total_score"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"UNEXPECTED_PRODUCT={product}")
    if tracker_product != product:
        raise ValueError(f"TRACKER_PRODUCT_MISMATCH={tracker_product}")
    if supplier_product != product:
        raise ValueError(f"SUPPLIER_PRODUCT_MISMATCH={supplier_product}")

    first_assets = launch_packet.get("first_publish_assets")
    if not isinstance(first_assets, list) or len(first_assets) != 3:
        raise ValueError("FIRST_PUBLISH_ASSET_COUNT_BAD")

    root_folder_name = "A8_R42_EXECUTION_RECHARGEABLE_LINT_REMOVER"

    directory_plan = [
        root_folder_name,
        f"{root_folder_name}/00_brief",
        f"{root_folder_name}/01_raw_video",
        f"{root_folder_name}/01_raw_video/V01_before_after_satisfying",
        f"{root_folder_name}/01_raw_video/V02_outfit_looks_cheap",
        f"{root_folder_name}/01_raw_video/V03_almost_threw_it_away",
        f"{root_folder_name}/02_selected_clips",
        f"{root_folder_name}/03_edit_projects",
        f"{root_folder_name}/04_exports",
        f"{root_folder_name}/05_captions",
        f"{root_folder_name}/06_publish_records",
        f"{root_folder_name}/07_metrics",
        f"{root_folder_name}/08_supplier_evidence",
        f"{root_folder_name}/09_decision_notes",
    ]

    execution_assets: list[ExecutionAsset] = []
    for raw_asset in first_assets:
        if not isinstance(raw_asset, dict):
            raise ValueError("FIRST_ASSET_MUST_BE_OBJECT")

        asset_id = str(raw_asset["asset_id"])
        platform = str(raw_asset["platform"])
        priority = int(raw_asset["priority"])
        hook = str(raw_asset["hook"])
        asset_slug = _slug(asset_id)
        platform_slug = _platform_slug(platform)

        execution_assets.append(
            ExecutionAsset(
                asset_id=asset_id,
                platform=platform,
                priority=priority,
                hook=hook,
                required_raw_folder=f"{root_folder_name}/01_raw_video/{asset_id}",
                required_export_file=f"{root_folder_name}/04_exports/{asset_slug}_{platform_slug}.mp4",
                caption_file=f"{root_folder_name}/05_captions/{asset_slug}_{platform_slug}.txt",
                publish_record_file=f"{root_folder_name}/06_publish_records/{asset_slug}_{platform_slug}.json",
                metric_record_file=f"{root_folder_name}/07_metrics/{asset_slug}_{platform_slug}.json",
                status="NOT_RECORDED",
            )
        )

    file_manifest = [
        f"{root_folder_name}/00_brief/README.md",
        f"{root_folder_name}/00_brief/local_launch_packet.copy.json",
        f"{root_folder_name}/00_brief/result_tracker_publish_log.copy.csv",
        f"{root_folder_name}/00_brief/supplier_validation_shell.copy.json",
        f"{root_folder_name}/05_captions/caption_bank.md",
        f"{root_folder_name}/06_publish_records/publish_log_template.csv",
        f"{root_folder_name}/07_metrics/metrics_template.csv",
        f"{root_folder_name}/08_supplier_evidence/supplier_evidence_README.md",
        f"{root_folder_name}/09_decision_notes/decision_log.md",
        f"{root_folder_name}/asset_manifest.json",
        f"{root_folder_name}/asset_manifest.csv",
    ]

    for asset in execution_assets:
        file_manifest.extend(
            [
                asset.caption_file,
                asset.publish_record_file,
                asset.metric_record_file,
            ]
        )

    publish_record_fields = [
        "asset_id",
        "platform",
        "publish_status",
        "publish_url_or_local_id",
        "published_at_local",
        "caption_used",
        "cta_used",
        "notes",
    ]

    metric_record_fields = [
        "asset_id",
        "platform",
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

    operator_checklist = [
        "Create the scaffold folder before recording.",
        "Place each raw clip inside the matching asset folder.",
        "Do not mix raw clips from different hooks.",
        "Export only vertical 9:16 videos.",
        "Save final captions as .txt before posting.",
        "Create publish record immediately after posting.",
        "Log metrics into the tracker after publish.",
        "Keep supplier screenshots under supplier evidence only.",
    ]

    quality_gates = [
        "RAW_FOLDER_EXISTS=1 for each first publish asset.",
        "CAPTION_FILE_EXISTS=1 before posting.",
        "EXPORT_FILE_EXISTS=1 before posting.",
        "PUBLISH_RECORD_EXISTS=1 after posting.",
        "METRIC_RECORD_EXISTS=1 after result capture.",
        "ZERO_SPEND_CONFIRMED=1 before supplier or ad work.",
        "NO_SUPPLIER_COMMITMENT=1 until evidence passes.",
    ]

    evidence_rules = [
        "Every raw clip must be traceable to one asset_id.",
        "Every export must map to one platform and one asset_id.",
        "Every publish URL or local post id must be recorded.",
        "Metrics must be numeric; unknown values remain zero.",
        "Supplier screenshots must be named by supplier slot.",
        "Do not overwrite raw files after selection.",
        "Do not delete weak assets; weak evidence still matters.",
    ]

    next_actions = [
        "Generate the local scaffold into C:/Temp first.",
        "Copy the scaffold folder to the operator workspace if needed.",
        "Record the first three priority assets.",
        "Export each asset using the required filename.",
        "Publish zero-spend posts.",
        "Fill publish records and metrics.",
        "Only then evaluate supplier evidence.",
    ]

    return ExecutionScaffoldPacket(
        product=product,
        decision=decision,
        total_score=total_score,
        scaffold_mode="LOCAL_EXECUTION_FOLDER_SCAFFOLD_ZERO_SPEND",
        root_folder_name=root_folder_name,
        directory_plan=directory_plan,
        execution_assets=execution_assets,
        file_manifest=file_manifest,
        operator_checklist=operator_checklist,
        quality_gates=quality_gates,
        publish_record_fields=publish_record_fields,
        metric_record_fields=metric_record_fields,
        evidence_rules=evidence_rules,
        next_actions=next_actions,
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def write_manifest_csv(packet: ExecutionScaffoldPacket, path: Path) -> None:
    fieldnames = [
        "asset_id",
        "platform",
        "priority",
        "hook",
        "required_raw_folder",
        "required_export_file",
        "caption_file",
        "publish_record_file",
        "metric_record_file",
        "status",
    ]

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for asset in packet.execution_assets:
            writer.writerow(asdict(asset))


def write_template_csv(fieldnames: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()


def create_scaffold_files(
    *,
    packet: ExecutionScaffoldPacket,
    out_dir: Path,
    launch_packet: dict[str, Any],
    tracker_csv_text: str,
    supplier_packet: dict[str, Any],
) -> dict[str, int]:
    root = _resolve_out_path(out_dir, packet.root_folder_name)
    root.mkdir(parents=True, exist_ok=True)

    for folder in packet.directory_plan:
        _resolve_out_path(out_dir, folder).mkdir(parents=True, exist_ok=True)

    _write_text(
        root / "00_brief" / "README.md",
        "\n".join(
            [
                "# Local execution scaffold",
                "",
                f"Product: {packet.product}",
                f"Decision: {packet.decision}",
                f"Total score: {packet.total_score}",
                "",
                "Rule: no ads, no inventory, no supplier commitment before manual signal and supplier evidence.",
            ]
        ),
    )

    _write_text(
        root / "00_brief" / "local_launch_packet.copy.json",
        json.dumps(launch_packet, ensure_ascii=False, indent=2),
    )
    _write_text(root / "00_brief" / "result_tracker_publish_log.copy.csv", tracker_csv_text)
    _write_text(
        root / "00_brief" / "supplier_validation_shell.copy.json",
        json.dumps(supplier_packet, ensure_ascii=False, indent=2),
    )

    caption_lines = ["# Caption bank", ""]
    for asset in packet.execution_assets:
        caption_lines.extend(
            [
                f"## {asset.asset_id} — {asset.platform}",
                "",
                asset.hook,
                "",
            ]
        )
        _write_text(
            _resolve_out_path(out_dir, asset.caption_file),
            f"{asset.hook}\n\nCTA: check if people ask where to buy.",
        )

    _write_text(root / "05_captions" / "caption_bank.md", "\n".join(caption_lines))

    write_template_csv(packet.publish_record_fields, root / "06_publish_records" / "publish_log_template.csv")
    write_template_csv(packet.metric_record_fields, root / "07_metrics" / "metrics_template.csv")

    _write_text(
        root / "08_supplier_evidence" / "supplier_evidence_README.md",
        "\n".join(
            [
                "# Supplier evidence",
                "",
                "Store supplier screenshots here only after manual signal exists.",
                "",
                "Required naming format:",
                "",
                "`SUPPLIER_A_real_photos_01.png`",
                "`SUPPLIER_A_landed_cost_01.png`",
                "`SUPPLIER_A_return_policy_01.png`",
            ]
        ),
    )

    _write_text(
        root / "09_decision_notes" / "decision_log.md",
        "\n".join(
            [
                "# Decision log",
                "",
                "## First review",
                "",
                "- signal_score_total: 0",
                "- buy_intent_comments_total: 0",
                "- dms_total: 0",
                "- decision: PENDING",
                "- notes:",
            ]
        ),
    )

    packet_json = root / "asset_manifest.json"
    packet_json.write_text(
        json.dumps(asdict(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_manifest_csv(packet, root / "asset_manifest.csv")

    for asset in packet.execution_assets:
        publish_record = {
            "asset_id": asset.asset_id,
            "platform": asset.platform,
            "publish_status": "NOT_POSTED",
            "publish_url_or_local_id": "",
            "published_at_local": "",
            "caption_used": "",
            "cta_used": "",
            "notes": "",
        }
        metric_record = {
            "asset_id": asset.asset_id,
            "platform": asset.platform,
            "views": 0,
            "likes": 0,
            "comments": 0,
            "saves": 0,
            "shares": 0,
            "profile_visits": 0,
            "link_clicks": 0,
            "buy_intent_comments": 0,
            "dms": 0,
            "signal_score": 0,
            "decision": "PENDING",
            "notes": "",
        }

        _write_text(_resolve_out_path(out_dir, asset.publish_record_file), json.dumps(publish_record, ensure_ascii=False, indent=2))
        _write_text(_resolve_out_path(out_dir, asset.metric_record_file), json.dumps(metric_record, ensure_ascii=False, indent=2))

    all_files = [p for p in root.rglob("*") if p.is_file()]
    all_dirs = [p for p in root.rglob("*") if p.is_dir()]
    return {
        "root_exists": int(root.exists()),
        "directory_count": len(all_dirs) + 1,
        "file_count": len(all_files),
    }


def write_markdown(packet: ExecutionScaffoldPacket, path: Path) -> None:
    lines: list[str] = [
        "# A8-R42J Execution Folder Scaffold",
        "",
        "## Product",
        "",
        f"`{packet.product}`",
        "",
        "## Scaffold mode",
        "",
        f"`{packet.scaffold_mode}`",
        "",
        "## Root folder",
        "",
        f"`{packet.root_folder_name}`",
        "",
        "## Directory plan",
        "",
    ]

    for folder in packet.directory_plan:
        lines.append(f"- `{folder}`")

    lines.extend(["", "## Execution assets", ""])
    for asset in packet.execution_assets:
        lines.extend(
            [
                f"### Priority {asset.priority}: {asset.asset_id}",
                "",
                f"- platform: {asset.platform}",
                f"- hook: {asset.hook}",
                f"- raw folder: `{asset.required_raw_folder}`",
                f"- export file: `{asset.required_export_file}`",
                f"- caption file: `{asset.caption_file}`",
                f"- publish record: `{asset.publish_record_file}`",
                f"- metric record: `{asset.metric_record_file}`",
                f"- status: {asset.status}",
                "",
            ]
        )

    sections = [
        ("Operator checklist", packet.operator_checklist),
        ("Quality gates", packet.quality_gates),
        ("Publish record fields", packet.publish_record_fields),
        ("Metric record fields", packet.metric_record_fields),
        ("Evidence rules", packet.evidence_rules),
        ("Next actions", packet.next_actions),
    ]

    for title, items in sections:
        lines.extend(["", f"## {title}", ""])
        for item in items:
            lines.append(f"- {item}")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-packet", required=True)
    parser.add_argument("--tracker-packet", required=True)
    parser.add_argument("--tracker-csv", required=True)
    parser.add_argument("--supplier-packet", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    launch_packet = _load_json(Path(args.launch_packet).resolve())
    tracker_packet = _load_json(Path(args.tracker_packet).resolve())
    supplier_packet = _load_json(Path(args.supplier_packet).resolve())
    tracker_csv_text = Path(args.tracker_csv).resolve().read_text(encoding="utf-8")

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    packet = build_execution_scaffold_packet(launch_packet, tracker_packet, supplier_packet)

    packet_json = out_dir / "execution_scaffold_packet.json"
    packet_md = out_dir / "execution_scaffold_packet.md"

    packet_json.write_text(
        json.dumps(asdict(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_markdown(packet, packet_md)

    counts = create_scaffold_files(
        packet=packet,
        out_dir=out_dir,
        launch_packet=launch_packet,
        tracker_csv_text=tracker_csv_text,
        supplier_packet=supplier_packet,
    )

    print(f"EXECUTION_SCAFFOLD_JSON={packet_json}")
    print(f"EXECUTION_SCAFFOLD_MD={packet_md}")
    print(f"EXECUTION_ROOT={out_dir / packet.root_folder_name}")
    print(f"PRODUCT={packet.product}")
    print(f"DECISION={packet.decision}")
    print(f"TOTAL_SCORE={packet.total_score}")
    print(f"DIRECTORY_PLAN_COUNT={len(packet.directory_plan)}")
    print(f"EXECUTION_ASSET_COUNT={len(packet.execution_assets)}")
    print(f"FILE_MANIFEST_COUNT={len(packet.file_manifest)}")
    print(f"OPERATOR_CHECKLIST_COUNT={len(packet.operator_checklist)}")
    print(f"QUALITY_GATE_COUNT={len(packet.quality_gates)}")
    print(f"PUBLISH_RECORD_FIELD_COUNT={len(packet.publish_record_fields)}")
    print(f"METRIC_RECORD_FIELD_COUNT={len(packet.metric_record_fields)}")
    print(f"EVIDENCE_RULE_COUNT={len(packet.evidence_rules)}")
    print(f"SCAFFOLD_ROOT_EXISTS={counts['root_exists']}")
    print(f"SCAFFOLD_DIRECTORY_COUNT={counts['directory_count']}")
    print(f"SCAFFOLD_FILE_COUNT={counts['file_count']}")
    print("A8_R42J_EXECUTION_SCAFFOLD_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
