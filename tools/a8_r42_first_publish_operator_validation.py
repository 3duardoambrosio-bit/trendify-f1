from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}


@dataclass(frozen=True)
class ValidationGate:
    gate_id: str
    category: str
    check: str
    expected: str
    actual: str
    passed: bool
    hard_blocker: bool
    evidence_path: str


@dataclass(frozen=True)
class RealAssetSlot:
    slot_id: str
    asset_id: str
    platform: str
    priority: int
    expected_export_file: str
    expected_caption_file: str
    expected_publish_record_file: str
    expected_metric_record_file: str
    real_export_present: bool
    publish_record_present: bool
    metric_record_present: bool
    caption_slot_present: bool
    status: str


@dataclass(frozen=True)
class FirstPublishOperatorValidation:
    product: str
    decision: str
    total_score: int
    mode: str
    handoff_root: str
    asset_slot_count: int
    validation_gate_count: int
    hard_blocker_gate_count: int
    passed_gate_count: int
    failed_gate_count: int
    structural_blocker_count: int
    missing_real_asset_count: int
    real_asset_export_count: int
    zero_spend_marker_count: int
    cloud_deferred_marker_count: int
    ready_for_real_asset_slot_preparation: int
    ready_for_first_manual_zero_spend_publish: int
    next_action: str


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"JSON_MUST_BE_OBJECT={path}")
    return raw


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


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


def _normalize_expected_path(handoff_root: Path, path_value: str) -> Path:
    value = path_value.replace("\\", "/")
    parts = value.split("/")

    if "A8_R42_EXECUTION_RECHARGEABLE_LINT_REMOVER" in parts:
        idx = parts.index("A8_R42_EXECUTION_RECHARGEABLE_LINT_REMOVER")
        return handoff_root / "02_EXECUTION_ROOT" / Path(*parts[idx + 1 :])

    if value.startswith("02_EXECUTION_ROOT/"):
        return handoff_root / Path(value)

    return handoff_root / "02_EXECUTION_ROOT" / Path(value)


def _find_real_exports(execution_root: Path) -> list[Path]:
    if not execution_root.exists():
        return []

    exports: list[Path] = []
    for path in execution_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in VIDEO_SUFFIXES:
            continue
        if path.stat().st_size < 1024:
            continue
        exports.append(path)

    return sorted(exports)


def _build_slots(handoff_root: Path, readiness_packet: dict[str, Any]) -> list[RealAssetSlot]:
    cards = readiness_packet.get("platform_cards")
    if not isinstance(cards, list) or len(cards) != 3:
        raise ValueError("PLATFORM_CARD_COUNT_BAD")

    slots: list[RealAssetSlot] = []
    for index, card in enumerate(cards, start=1):
        if not isinstance(card, dict):
            raise ValueError("PLATFORM_CARD_MUST_BE_OBJECT")

        export_path = _normalize_expected_path(handoff_root, str(card["required_export_file"]))
        caption_path = _normalize_expected_path(handoff_root, str(card["required_caption_file"]))
        publish_record_path = _normalize_expected_path(handoff_root, str(card["required_publish_record_file"]))
        metric_record_path = _normalize_expected_path(handoff_root, str(card["required_metric_record_file"]))

        real_export_present = (
            export_path.exists()
            and export_path.is_file()
            and export_path.suffix.lower() in VIDEO_SUFFIXES
            and export_path.stat().st_size >= 1024
        )

        caption_slot_present = caption_path.exists()
        publish_record_present = publish_record_path.exists()
        metric_record_present = metric_record_path.exists()

        status = "READY_TO_PUBLISH" if real_export_present and caption_slot_present and publish_record_present and metric_record_present else "ASSET_PREP_REQUIRED"

        slots.append(
            RealAssetSlot(
                slot_id=f"SLOT_{index:02d}",
                asset_id=str(card["asset_id"]),
                platform=str(card["platform"]),
                priority=int(card["priority"]),
                expected_export_file=str(export_path),
                expected_caption_file=str(caption_path),
                expected_publish_record_file=str(publish_record_path),
                expected_metric_record_file=str(metric_record_path),
                real_export_present=real_export_present,
                publish_record_present=publish_record_present,
                metric_record_present=metric_record_present,
                caption_slot_present=caption_slot_present,
                status=status,
            )
        )

    return slots


def validate_handoff(handoff_root: Path) -> tuple[FirstPublishOperatorValidation, list[ValidationGate], list[RealAssetSlot]]:
    start_here = handoff_root / "00_START_HERE" / "START_HERE.md"
    acceptance_csv = handoff_root / "00_START_HERE" / "operator_acceptance_checklist.csv"
    readiness_json = handoff_root / "01_PACKETS" / "publish_readiness_packet.json"
    offline_json = handoff_root / "01_PACKETS" / "offline_execution_packet.json"
    execution_root = handoff_root / "02_EXECUTION_ROOT"
    manifest_csv = handoff_root / "04_INDEX" / "handoff_manifest.csv"
    file_index_csv = handoff_root / "04_INDEX" / "handoff_file_index.csv"

    for path in [start_here, acceptance_csv, readiness_json, offline_json, execution_root, manifest_csv, file_index_csv]:
        if not path.exists():
            raise FileNotFoundError(f"REQUIRED_HANDOFF_PATH_MISSING={path}")

    start_text = start_here.read_text(encoding="utf-8")
    acceptance_rows = _read_csv(acceptance_csv)
    manifest_rows = _read_csv(manifest_csv)
    file_index_rows = _read_csv(file_index_csv)
    readiness_packet = _load_json(readiness_json)
    offline_packet = _load_json(offline_json)

    product = str(readiness_packet["product"])
    decision = str(readiness_packet["decision"])
    total_score = int(readiness_packet["total_score"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"PRODUCT_BAD={product}")
    if decision != "ADVANCE":
        raise ValueError(f"DECISION_BAD={decision}")
    if total_score != 59:
        raise ValueError(f"TOTAL_SCORE_BAD={total_score}")
    if str(offline_packet["product"]) != product:
        raise ValueError("OFFLINE_PACKET_PRODUCT_MISMATCH")

    slots = _build_slots(handoff_root, readiness_packet)
    real_exports = _find_real_exports(execution_root)

    zero_markers = sum(
        marker in start_text
        for marker in [
            "Do not run ads",
            "Do not buy inventory",
            "Do not commit to a supplier",
            "ZERO_SPEND_ONLY=1",
        ]
    )

    cloud_markers = start_text.count("CLOUD_AUDIT_DEFERRED=1")

    gates = [
        ValidationGate("G01", "handoff", "START_HERE exists", "1", str(int(start_here.exists())), start_here.exists(), True, str(start_here)),
        ValidationGate("G02", "handoff", "acceptance checklist rows", "13", str(len(acceptance_rows)), len(acceptance_rows) == 13, True, str(acceptance_csv)),
        ValidationGate("G03", "handoff", "manifest rows", "14", str(len(manifest_rows)), len(manifest_rows) == 14, True, str(manifest_csv)),
        ValidationGate("G04", "handoff", "file index rows", "32", str(len(file_index_rows)), len(file_index_rows) == 32, True, str(file_index_csv)),
        ValidationGate("G05", "readiness", "platform cards", "3", str(len(slots)), len(slots) == 3, True, str(readiness_json)),
        ValidationGate("G06", "policy", "zero spend markers", ">=4", str(zero_markers), zero_markers >= 4, True, str(start_here)),
        ValidationGate("G07", "policy", "cloud deferred marker", ">=1", str(cloud_markers), cloud_markers >= 1, False, str(start_here)),
        ValidationGate("G08", "assets", "caption slots present", "3", str(sum(slot.caption_slot_present for slot in slots)), sum(slot.caption_slot_present for slot in slots) == 3, True, str(execution_root)),
        ValidationGate("G09", "assets", "publish records present", "3", str(sum(slot.publish_record_present for slot in slots)), sum(slot.publish_record_present for slot in slots) == 3, True, str(execution_root)),
        ValidationGate("G10", "assets", "metric records present", "3", str(sum(slot.metric_record_present for slot in slots)), sum(slot.metric_record_present for slot in slots) == 3, True, str(execution_root)),
        ValidationGate("G11", "assets", "real export videos present", "3", str(len(real_exports)), len(real_exports) == 3, True, str(execution_root)),
    ]

    failed_gates = [gate for gate in gates if not gate.passed]
    structural_failed = [
        gate for gate in failed_gates
        if gate.gate_id != "G11"
    ]

    missing_real_assets = len([slot for slot in slots if not slot.real_export_present])

    ready_for_slot_prep = 1 if len(structural_failed) == 0 and len(slots) == 3 else 0
    ready_for_publish = 1 if ready_for_slot_prep == 1 and missing_real_assets == 0 else 0

    validation = FirstPublishOperatorValidation(
        product=product,
        decision=decision,
        total_score=total_score,
        mode="LOCAL_FIRST_PUBLISH_OPERATOR_VALIDATION",
        handoff_root=str(handoff_root),
        asset_slot_count=len(slots),
        validation_gate_count=len(gates),
        hard_blocker_gate_count=len([gate for gate in gates if gate.hard_blocker]),
        passed_gate_count=len([gate for gate in gates if gate.passed]),
        failed_gate_count=len(failed_gates),
        structural_blocker_count=len(structural_failed),
        missing_real_asset_count=missing_real_assets,
        real_asset_export_count=len(real_exports),
        zero_spend_marker_count=zero_markers,
        cloud_deferred_marker_count=cloud_markers,
        ready_for_real_asset_slot_preparation=ready_for_slot_prep,
        ready_for_first_manual_zero_spend_publish=ready_for_publish,
        next_action=(
            "Place three real exported videos into the expected export slots."
            if ready_for_publish == 0
            else "Proceed to first manual zero-spend publish."
        ),
    )

    return validation, gates, slots


def write_outputs(validation: FirstPublishOperatorValidation, gates: list[ValidationGate], slots: list[RealAssetSlot], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "first_publish_operator_validation.json").write_text(
        json.dumps(
            {
                "validation": asdict(validation),
                "gates": [asdict(gate) for gate in gates],
                "asset_slots": [asdict(slot) for slot in slots],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )

    _write_csv(
        out_dir / "first_publish_validation_gates.csv",
        ["gate_id", "category", "check", "expected", "actual", "passed", "hard_blocker", "evidence_path"],
        [asdict(gate) for gate in gates],
    )

    _write_csv(
        out_dir / "real_asset_slot_sheet.csv",
        [
            "slot_id",
            "asset_id",
            "platform",
            "priority",
            "expected_export_file",
            "expected_caption_file",
            "expected_publish_record_file",
            "expected_metric_record_file",
            "real_export_present",
            "publish_record_present",
            "metric_record_present",
            "caption_slot_present",
            "status",
        ],
        [asdict(slot) for slot in slots],
    )

    blockers = [gate for gate in gates if not gate.passed and gate.hard_blocker]
    _write_csv(
        out_dir / "blocking_gates.csv",
        ["gate_id", "category", "check", "expected", "actual", "evidence_path"],
        [
            {
                "gate_id": gate.gate_id,
                "category": gate.category,
                "check": gate.check,
                "expected": gate.expected,
                "actual": gate.actual,
                "evidence_path": gate.evidence_path,
            }
            for gate in blockers
        ],
    )

    lines = [
        "# A8-R42N First-Publish Operator Validation",
        "",
        f"Product: `{validation.product}`",
        "",
        f"Mode: `{validation.mode}`",
        "",
        "## Readiness",
        "",
        f"- READY_FOR_REAL_ASSET_SLOT_PREPARATION={validation.ready_for_real_asset_slot_preparation}",
        f"- READY_FOR_FIRST_MANUAL_ZERO_SPEND_PUBLISH={validation.ready_for_first_manual_zero_spend_publish}",
        f"- MISSING_REAL_ASSET_COUNT={validation.missing_real_asset_count}",
        f"- REAL_ASSET_EXPORT_COUNT={validation.real_asset_export_count}",
        "",
        "## Next action",
        "",
        validation.next_action,
        "",
        "## Asset slots",
        "",
    ]

    for slot in slots:
        lines.extend(
            [
                f"### {slot.slot_id} — {slot.platform}",
                "",
                f"- asset_id: `{slot.asset_id}`",
                f"- status: `{slot.status}`",
                f"- expected_export_file: `{slot.expected_export_file}`",
                f"- caption_slot_present: `{int(slot.caption_slot_present)}`",
                f"- publish_record_present: `{int(slot.publish_record_present)}`",
                f"- metric_record_present: `{int(slot.metric_record_present)}`",
                f"- real_export_present: `{int(slot.real_export_present)}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Gates",
            "",
            *[
                f"- {gate.gate_id}: {gate.check} | expected `{gate.expected}` | actual `{gate.actual}` | passed `{int(gate.passed)}`"
                for gate in gates
            ],
        ]
    )

    _write_text(out_dir / "first_publish_operator_validation.md", "\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff-root", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    handoff_root = Path(args.handoff_root).resolve()
    out_dir = Path(args.out_dir).resolve()

    validation, gates, slots = validate_handoff(handoff_root)
    write_outputs(validation, gates, slots, out_dir)

    output_files = [p for p in out_dir.rglob("*") if p.is_file()]

    print(f"FIRST_PUBLISH_VALIDATION_JSON={out_dir / 'first_publish_operator_validation.json'}")
    print(f"FIRST_PUBLISH_VALIDATION_MD={out_dir / 'first_publish_operator_validation.md'}")
    print(f"PRODUCT={validation.product}")
    print(f"DECISION={validation.decision}")
    print(f"TOTAL_SCORE={validation.total_score}")
    print(f"ASSET_SLOT_COUNT={validation.asset_slot_count}")
    print(f"VALIDATION_GATE_COUNT={validation.validation_gate_count}")
    print(f"HARD_BLOCKER_GATE_COUNT={validation.hard_blocker_gate_count}")
    print(f"PASSED_GATE_COUNT={validation.passed_gate_count}")
    print(f"FAILED_GATE_COUNT={validation.failed_gate_count}")
    print(f"STRUCTURAL_BLOCKER_COUNT={validation.structural_blocker_count}")
    print(f"MISSING_REAL_ASSET_COUNT={validation.missing_real_asset_count}")
    print(f"REAL_ASSET_EXPORT_COUNT={validation.real_asset_export_count}")
    print(f"ZERO_SPEND_MARKER_COUNT={validation.zero_spend_marker_count}")
    print(f"CLOUD_DEFERRED_MARKER_COUNT={validation.cloud_deferred_marker_count}")
    print(f"OUTPUT_FILE_COUNT={len(output_files)}")
    print(f"READY_FOR_REAL_ASSET_SLOT_PREPARATION={validation.ready_for_real_asset_slot_preparation}")
    print(f"READY_FOR_FIRST_MANUAL_ZERO_SPEND_PUBLISH={validation.ready_for_first_manual_zero_spend_publish}")
    print("A8_R42N_FIRST_PUBLISH_OPERATOR_VALIDATION_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
