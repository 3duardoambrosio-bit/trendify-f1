from __future__ import annotations

import argparse
import csv
import json
import shutil
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HandoffManifestRow:
    section: str
    path: str
    purpose: str
    required: bool


@dataclass(frozen=True)
class OperatorAcceptanceRow:
    check_id: str
    check: str
    expected_value: str
    evidence_path: str
    hard_blocker: bool


@dataclass(frozen=True)
class ExecutionExportPackage:
    product: str
    decision: str
    total_score: int
    mode: str
    launch_authorization: str
    zero_spend_policy: str
    handoff_root: str
    handoff_zip: str
    scaffold_file_count: int
    copied_execution_file_count: int
    manifest_row_count: int
    acceptance_check_count: int
    hard_blocker_check_count: int
    packet_file_count: int
    handoff_file_count: int
    zip_entry_count: int
    start_here_file: str
    next_action: str


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


def _copy_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND={src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path) -> int:
    if not src.is_dir():
        raise FileNotFoundError(f"DIR_NOT_FOUND={src}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return len([p for p in dst.rglob("*") if p.is_file()])


def _zip_dir(src_dir: Path, zip_path: Path) -> int:
    if zip_path.exists():
        zip_path.unlink()

    entries = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(src_dir).as_posix())
                entries += 1
    return entries


def _assert_common_product(product: str, packets: dict[str, dict[str, Any]]) -> None:
    for label, packet in packets.items():
        actual = str(packet["product"])
        if actual != product:
            raise ValueError(f"{label.upper()}_PRODUCT_MISMATCH={actual}")


def _manifest_rows() -> list[HandoffManifestRow]:
    return [
        HandoffManifestRow("00_START_HERE", "00_START_HERE/START_HERE.md", "first file to open", True),
        HandoffManifestRow("00_START_HERE", "00_START_HERE/operator_acceptance_checklist.csv", "operator gate checklist", True),
        HandoffManifestRow("01_PACKETS", "01_PACKETS/local_launch_packet.json", "launch packet", True),
        HandoffManifestRow("01_PACKETS", "01_PACKETS/result_tracker_publish_log.json", "metric tracker packet", True),
        HandoffManifestRow("01_PACKETS", "01_PACKETS/supplier_validation_shell.json", "supplier shell, not commitment", True),
        HandoffManifestRow("01_PACKETS", "01_PACKETS/execution_scaffold_packet.json", "execution scaffold packet", True),
        HandoffManifestRow("01_PACKETS", "01_PACKETS/offline_execution_packet.json", "offline operator packet", True),
        HandoffManifestRow("01_PACKETS", "01_PACKETS/publish_readiness_packet.json", "publish readiness packet", True),
        HandoffManifestRow("02_EXECUTION_ROOT", "02_EXECUTION_ROOT/", "copied scaffold execution folder", True),
        HandoffManifestRow("03_GUIDES", "03_GUIDES/no_go_rules.md", "publish no-go rules", True),
        HandoffManifestRow("03_GUIDES", "03_GUIDES/metric_trigger_rules.md", "metric capture rules", True),
        HandoffManifestRow("03_GUIDES", "03_GUIDES/final_decision_options.md", "decision outcomes", True),
        HandoffManifestRow("04_INDEX", "04_INDEX/handoff_manifest.csv", "handoff manifest", True),
        HandoffManifestRow("04_INDEX", "04_INDEX/handoff_file_index.csv", "all handoff files", True),
    ]


def _acceptance_rows() -> list[OperatorAcceptanceRow]:
    return [
        OperatorAcceptanceRow("A01", "Open START_HERE before publishing.", "START_HERE_OPEN=1", "00_START_HERE/START_HERE.md", True),
        OperatorAcceptanceRow("A02", "Confirm zero-spend policy.", "ZERO_SPEND_ONLY=1", "01_PACKETS/publish_readiness_packet.json", True),
        OperatorAcceptanceRow("A03", "Confirm no supplier commitment.", "NO_SUPPLIER_COMMITMENT=1", "03_GUIDES/no_go_rules.md", True),
        OperatorAcceptanceRow("A04", "Confirm no inventory purchase.", "NO_INVENTORY_PURCHASE=1", "03_GUIDES/no_go_rules.md", True),
        OperatorAcceptanceRow("A05", "Confirm three asset cards exist.", "PLATFORM_CARD_COUNT=3", "01_PACKETS/publish_readiness_packet.json", True),
        OperatorAcceptanceRow("A06", "Confirm three publish records exist.", "PUBLISH_RECORD_COUNT=3", "02_EXECUTION_ROOT/06_publish_records", True),
        OperatorAcceptanceRow("A07", "Confirm three metric records exist.", "METRIC_RECORD_COUNT=3", "02_EXECUTION_ROOT/07_metrics", True),
        OperatorAcceptanceRow("A08", "Confirm captions are ready before posting.", "CAPTION_READY_COUNT=3", "02_EXECUTION_ROOT/05_captions", True),
        OperatorAcceptanceRow("A09", "Confirm before/after transformation is visible.", "BEFORE_AFTER_VISIBLE=1", "00_START_HERE/operator_acceptance_checklist.csv", True),
        OperatorAcceptanceRow("A10", "Confirm no unsupported claims.", "NO_UNSUPPORTED_CLAIMS=1", "03_GUIDES/no_go_rules.md", True),
        OperatorAcceptanceRow("A11", "Fill publish record after each post.", "PUBLISH_RECORD_FILLED=1", "02_EXECUTION_ROOT/06_publish_records", True),
        OperatorAcceptanceRow("A12", "Fill metrics after signal capture.", "METRIC_RECORD_FILLED=1", "02_EXECUTION_ROOT/07_metrics", True),
        OperatorAcceptanceRow("A13", "Apply decision rules before supplier review.", "DECISION_RULES_APPLIED=1", "03_GUIDES/final_decision_options.md", True),
    ]


def _write_start_here(
    *,
    path: Path,
    product: str,
    launch_authorization: str,
    zero_spend_policy: str,
    readiness_gate_count: int,
    hard_blocker_count: int,
) -> None:
    _write_text(
        path,
        "\n".join(
            [
                "# START HERE — A8-R42M Operator Handoff",
                "",
                f"Product: `{product}`",
                "",
                f"Launch authorization: `{launch_authorization}`",
                "",
                "## Non-negotiable policy",
                "",
                zero_spend_policy,
                "",
                "## Execution order",
                "",
                "1. Open `00_START_HERE/operator_acceptance_checklist.csv`.",
                "2. Open `01_PACKETS/publish_readiness_packet.json`.",
                "3. Open `02_EXECUTION_ROOT/asset_manifest.csv`.",
                "4. Prepare the three priority assets.",
                "5. Fill captions before publishing.",
                "6. Publish zero-spend only.",
                "7. Fill publish records.",
                "8. Fill metric records.",
                "9. Apply decision rules before supplier review.",
                "",
                "## Counts",
                "",
                f"- READINESS_GATE_COUNT={readiness_gate_count}",
                f"- HARD_BLOCKER_GATE_COUNT={hard_blocker_count}",
                "- ZERO_SPEND_ONLY=1",
                "- CLOUD_AUDIT_DEFERRED=1",
                "",
                "## Do not do",
                "",
                "- Do not run ads.",
                "- Do not buy inventory.",
                "- Do not commit to a supplier.",
                "- Do not publish unsupported claims.",
                "- Do not skip metrics.",
            ]
        ),
    )


def build_export(
    *,
    launch_packet_path: Path,
    tracker_packet_path: Path,
    supplier_packet_path: Path,
    scaffold_packet_path: Path,
    offline_packet_path: Path,
    readiness_packet_path: Path,
    execution_root: Path,
    out_dir: Path,
) -> ExecutionExportPackage:
    launch_packet = _load_json(launch_packet_path)
    tracker_packet = _load_json(tracker_packet_path)
    supplier_packet = _load_json(supplier_packet_path)
    scaffold_packet = _load_json(scaffold_packet_path)
    offline_packet = _load_json(offline_packet_path)
    readiness_packet = _load_json(readiness_packet_path)

    product = str(launch_packet["product"])
    decision = str(launch_packet["decision"])
    total_score = int(launch_packet["total_score"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"UNEXPECTED_PRODUCT={product}")
    if decision != "ADVANCE":
        raise ValueError(f"UNEXPECTED_DECISION={decision}")
    if total_score != 59:
        raise ValueError(f"UNEXPECTED_TOTAL_SCORE={total_score}")

    _assert_common_product(
        product,
        {
            "tracker": tracker_packet,
            "supplier": supplier_packet,
            "scaffold": scaffold_packet,
            "offline": offline_packet,
            "readiness": readiness_packet,
        },
    )

    launch_authorization = str(readiness_packet["launch_authorization"])
    if launch_authorization != "READY_FOR_ZERO_SPEND_MANUAL_PUBLISH_ONLY":
        raise ValueError(f"LAUNCH_AUTHORIZATION_BAD={launch_authorization}")

    readiness_gates = readiness_packet.get("readiness_gates")
    platform_cards = readiness_packet.get("platform_cards")
    if not isinstance(readiness_gates, list) or len(readiness_gates) != 15:
        raise ValueError("READINESS_GATE_COUNT_BAD")
    if not isinstance(platform_cards, list) or len(platform_cards) != 3:
        raise ValueError("PLATFORM_CARD_COUNT_BAD")

    hard_blocker_count = len([gate for gate in readiness_gates if bool(gate.get("hard_blocker"))])
    if hard_blocker_count != 13:
        raise ValueError(f"HARD_BLOCKER_GATE_COUNT_BAD={hard_blocker_count}")

    scaffold_file_count = len([p for p in execution_root.rglob("*") if p.is_file()])
    if scaffold_file_count != 20:
        raise ValueError(f"SCAFFOLD_FILE_COUNT_BAD={scaffold_file_count}")

    handoff_root = out_dir / "A8_R42M_OPERATOR_HANDOFF_RECHARGEABLE_LINT_REMOVER"
    if handoff_root.exists():
        shutil.rmtree(handoff_root)

    start_here_dir = handoff_root / "00_START_HERE"
    packets_dir = handoff_root / "01_PACKETS"
    copied_execution_dir = handoff_root / "02_EXECUTION_ROOT"
    guides_dir = handoff_root / "03_GUIDES"
    index_dir = handoff_root / "04_INDEX"

    for directory in [start_here_dir, packets_dir, copied_execution_dir, guides_dir, index_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    _copy_file(launch_packet_path, packets_dir / "local_launch_packet.json")
    _copy_file(tracker_packet_path, packets_dir / "result_tracker_publish_log.json")
    _copy_file(supplier_packet_path, packets_dir / "supplier_validation_shell.json")
    _copy_file(scaffold_packet_path, packets_dir / "execution_scaffold_packet.json")
    _copy_file(offline_packet_path, packets_dir / "offline_execution_packet.json")
    _copy_file(readiness_packet_path, packets_dir / "publish_readiness_packet.json")

    copied_execution_file_count = _copy_tree(execution_root, copied_execution_dir)
    if copied_execution_file_count != 20:
        raise ValueError(f"COPIED_EXECUTION_FILE_COUNT_BAD={copied_execution_file_count}")

    zero_spend_policy = str(readiness_packet["zero_spend_policy"])
    _write_start_here(
        path=start_here_dir / "START_HERE.md",
        product=product,
        launch_authorization=launch_authorization,
        zero_spend_policy=zero_spend_policy,
        readiness_gate_count=len(readiness_gates),
        hard_blocker_count=hard_blocker_count,
    )

    acceptance_rows = _acceptance_rows()
    _write_csv(
        start_here_dir / "operator_acceptance_checklist.csv",
        ["check_id", "check", "expected_value", "evidence_path", "hard_blocker"],
        [asdict(row) for row in acceptance_rows],
    )

    no_go_rules = readiness_packet.get("no_go_rules")
    metric_trigger_rules = readiness_packet.get("metric_trigger_rules")
    final_decision_options = readiness_packet.get("final_decision_options")

    if not isinstance(no_go_rules, list) or len(no_go_rules) != 10:
        raise ValueError("NO_GO_RULE_COUNT_BAD")
    if not isinstance(metric_trigger_rules, list) or len(metric_trigger_rules) != 10:
        raise ValueError("METRIC_TRIGGER_RULE_COUNT_BAD")
    if not isinstance(final_decision_options, list) or len(final_decision_options) != 6:
        raise ValueError("FINAL_DECISION_OPTION_COUNT_BAD")

    _write_text(guides_dir / "no_go_rules.md", "\n".join(["# No-go rules", "", *[f"- {rule}" for rule in no_go_rules]]))
    _write_text(guides_dir / "metric_trigger_rules.md", "\n".join(["# Metric trigger rules", "", *[f"- {rule}" for rule in metric_trigger_rules]]))
    _write_text(guides_dir / "final_decision_options.md", "\n".join(["# Final decision options", "", *[f"- {rule}" for rule in final_decision_options]]))

    manifest_rows = _manifest_rows()
    _write_csv(
        index_dir / "handoff_manifest.csv",
        ["section", "path", "purpose", "required"],
        [asdict(row) for row in manifest_rows],
    )

    file_index_rows = []
    for path in sorted(handoff_root.rglob("*")):
        if path.is_file():
            file_index_rows.append(
                {
                    "relative_path": path.relative_to(handoff_root).as_posix(),
                    "size_bytes": path.stat().st_size,
                }
            )

    _write_csv(index_dir / "handoff_file_index.csv", ["relative_path", "size_bytes"], file_index_rows)

    handoff_zip = out_dir / "A8_R42M_OPERATOR_HANDOFF_RECHARGEABLE_LINT_REMOVER.zip"
    zip_entry_count = _zip_dir(handoff_root, handoff_zip)

    handoff_file_count = len([p for p in handoff_root.rglob("*") if p.is_file()])
    packet_file_count = len([p for p in packets_dir.rglob("*") if p.is_file()])

    package = ExecutionExportPackage(
        product=product,
        decision=decision,
        total_score=total_score,
        mode="LOCAL_EXECUTION_EXPORT_OPERATOR_HANDOFF",
        launch_authorization=launch_authorization,
        zero_spend_policy=zero_spend_policy,
        handoff_root=str(handoff_root),
        handoff_zip=str(handoff_zip),
        scaffold_file_count=scaffold_file_count,
        copied_execution_file_count=copied_execution_file_count,
        manifest_row_count=len(manifest_rows),
        acceptance_check_count=len(acceptance_rows),
        hard_blocker_check_count=len([row for row in acceptance_rows if row.hard_blocker]),
        packet_file_count=packet_file_count,
        handoff_file_count=handoff_file_count,
        zip_entry_count=zip_entry_count,
        start_here_file=str(start_here_dir / "START_HERE.md"),
        next_action="Open START_HERE.md and execute zero-spend manual publish gates.",
    )

    package_json = out_dir / "execution_export_package.json"
    package_md = out_dir / "execution_export_package.md"

    package_json.write_text(
        json.dumps(asdict(package), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    _write_text(
        package_md,
        "\n".join(
            [
                "# A8-R42M Execution Export Package",
                "",
                f"Product: `{package.product}`",
                "",
                f"Mode: `{package.mode}`",
                "",
                f"Launch authorization: `{package.launch_authorization}`",
                "",
                "## Handoff",
                "",
                f"- handoff_root: `{package.handoff_root}`",
                f"- handoff_zip: `{package.handoff_zip}`",
                f"- start_here_file: `{package.start_here_file}`",
                "",
                "## Counts",
                "",
                f"- SCAFFOLD_FILE_COUNT={package.scaffold_file_count}",
                f"- COPIED_EXECUTION_FILE_COUNT={package.copied_execution_file_count}",
                f"- MANIFEST_ROW_COUNT={package.manifest_row_count}",
                f"- ACCEPTANCE_CHECK_COUNT={package.acceptance_check_count}",
                f"- HARD_BLOCKER_CHECK_COUNT={package.hard_blocker_check_count}",
                f"- PACKET_FILE_COUNT={package.packet_file_count}",
                f"- HANDOFF_FILE_COUNT={package.handoff_file_count}",
                f"- ZIP_ENTRY_COUNT={package.zip_entry_count}",
                "",
                "## Policy",
                "",
                package.zero_spend_policy,
                "",
                "CLOUD_AUDIT_DEFERRED=1",
                "ZERO_SPEND_ONLY=1",
            ]
        ),
    )

    return package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-packet", required=True)
    parser.add_argument("--tracker-packet", required=True)
    parser.add_argument("--supplier-packet", required=True)
    parser.add_argument("--scaffold-packet", required=True)
    parser.add_argument("--offline-packet", required=True)
    parser.add_argument("--readiness-packet", required=True)
    parser.add_argument("--execution-root", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    package = build_export(
        launch_packet_path=Path(args.launch_packet).resolve(),
        tracker_packet_path=Path(args.tracker_packet).resolve(),
        supplier_packet_path=Path(args.supplier_packet).resolve(),
        scaffold_packet_path=Path(args.scaffold_packet).resolve(),
        offline_packet_path=Path(args.offline_packet).resolve(),
        readiness_packet_path=Path(args.readiness_packet).resolve(),
        execution_root=Path(args.execution_root).resolve(),
        out_dir=Path(args.out_dir).resolve(),
    )

    print(f"EXECUTION_EXPORT_JSON={Path(args.out_dir).resolve() / 'execution_export_package.json'}")
    print(f"EXECUTION_EXPORT_MD={Path(args.out_dir).resolve() / 'execution_export_package.md'}")
    print(f"OPERATOR_HANDOFF_ROOT={package.handoff_root}")
    print(f"OPERATOR_HANDOFF_ZIP={package.handoff_zip}")
    print(f"PRODUCT={package.product}")
    print(f"DECISION={package.decision}")
    print(f"TOTAL_SCORE={package.total_score}")
    print(f"LAUNCH_AUTHORIZATION={package.launch_authorization}")
    print(f"SCAFFOLD_FILE_COUNT={package.scaffold_file_count}")
    print(f"COPIED_EXECUTION_FILE_COUNT={package.copied_execution_file_count}")
    print(f"MANIFEST_ROW_COUNT={package.manifest_row_count}")
    print(f"ACCEPTANCE_CHECK_COUNT={package.acceptance_check_count}")
    print(f"HARD_BLOCKER_CHECK_COUNT={package.hard_blocker_check_count}")
    print(f"PACKET_FILE_COUNT={package.packet_file_count}")
    print(f"HANDOFF_FILE_COUNT={package.handoff_file_count}")
    print(f"HANDOFF_ZIP_ENTRY_COUNT={package.zip_entry_count}")
    print("CLOUD_AUDIT_DEFERRED=1")
    print("ZERO_SPEND_ONLY=1")
    print("A8_R42M_EXECUTION_EXPORT_PACKAGE_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
