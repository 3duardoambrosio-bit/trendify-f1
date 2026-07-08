from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


VIDEO_SUFFIXES = [".mp4", ".mov", ".m4v", ".webm"]


@dataclass(frozen=True)
class CaptureSlot:
    slot_id: str
    asset_id: str
    platform: str
    priority: int
    expected_export_file: str
    dropzone_dir: str
    dropzone_instruction_file: str
    recommended_source_filename: str
    accepted_extensions: str
    minimum_bytes: int
    current_real_export_present: bool
    status: str


@dataclass(frozen=True)
class CapturePlacementGate:
    product: str
    decision: str
    total_score: int
    mode: str
    source_validation_json: str
    asset_capture_slot_count: int
    target_export_path_count: int
    source_dropzone_slot_count: int
    missing_real_asset_count: int
    real_asset_export_count: int
    ready_for_asset_capture_execution: int
    ready_for_first_manual_zero_spend_publish: int
    copy_plan_file: str
    next_action: str


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"JSON_MUST_BE_OBJECT={path}")
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


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _build_copy_plan(slots: list[CaptureSlot]) -> str:
    lines = [
        '$ErrorActionPreference = "Stop"',
        'Set-StrictMode -Version Latest',
        '',
        'Write-Host "A8-R42O REAL ASSET COPY PLAN"',
        '',
        '$slots = @(',
    ]

    for slot in slots:
        source = str(Path(slot.dropzone_dir) / slot.recommended_source_filename)
        target = slot.expected_export_file
        lines.extend(
            [
                "  @{",
                f"    SlotId = {_ps_quote(slot.slot_id)}",
                f"    Platform = {_ps_quote(slot.platform)}",
                f"    Source = {_ps_quote(source)}",
                f"    Target = {_ps_quote(target)}",
                "  }",
            ]
        )

    lines.extend(
        [
            ")",
            "",
            'foreach ($slot in $slots) {',
            '  Write-Host "VALIDATING_SLOT=$($slot.SlotId)"',
            '  if (-not (Test-Path $slot.Source)) { throw "SOURCE_VIDEO_MISSING=$($slot.Source)" }',
            '  $sourceItem = Get-Item $slot.Source',
            '  if ($sourceItem.Length -lt 1024) { throw "SOURCE_VIDEO_TOO_SMALL=$($slot.Source) bytes=$($sourceItem.Length)" }',
            '  $targetDir = Split-Path -Parent $slot.Target',
            '  if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }',
            '  Copy-Item -Path $slot.Source -Destination $slot.Target -Force',
            '  if (-not (Test-Path $slot.Target)) { throw "TARGET_COPY_FAILED=$($slot.Target)" }',
            '  $targetItem = Get-Item $slot.Target',
            '  if ($targetItem.Length -lt 1024) { throw "TARGET_VIDEO_TOO_SMALL=$($slot.Target) bytes=$($targetItem.Length)" }',
            '  Write-Host "COPIED_SLOT=$($slot.SlotId)"',
            '  Write-Host "TARGET=$($slot.Target)"',
            '}',
            '',
            'Write-Host "A8_R42O_COPY_PLAN_PASS=1"',
        ]
    )

    return "\n".join(lines)


def build_gate(validation_json: Path, out_dir: Path) -> CapturePlacementGate:
    packet = _load_json(validation_json)
    validation = packet.get("validation")
    raw_slots = packet.get("asset_slots")

    if not isinstance(validation, dict):
        raise ValueError("VALIDATION_BLOCK_MISSING")
    if not isinstance(raw_slots, list):
        raise ValueError("ASSET_SLOTS_MISSING")

    product = str(validation["product"])
    decision = str(validation["decision"])
    total_score = int(validation["total_score"])

    if product != "Rechargeable Electric Lint Remover":
        raise ValueError(f"PRODUCT_BAD={product}")
    if decision != "ADVANCE":
        raise ValueError(f"DECISION_BAD={decision}")
    if total_score != 59:
        raise ValueError(f"TOTAL_SCORE_BAD={total_score}")
    if len(raw_slots) != 3:
        raise ValueError(f"ASSET_SLOT_COUNT_BAD={len(raw_slots)}")

    dropzone_root = out_dir / "source_dropzone"
    dropzone_root.mkdir(parents=True, exist_ok=True)

    slots: list[CaptureSlot] = []

    for idx, raw in enumerate(raw_slots, start=1):
        if not isinstance(raw, dict):
            raise ValueError("ASSET_SLOT_MUST_BE_OBJECT")

        slot_id = str(raw["slot_id"])
        asset_id = str(raw["asset_id"])
        platform = str(raw["platform"])
        priority = int(raw["priority"])
        expected_export_file = str(raw["expected_export_file"])
        real_export_present = bool(raw["real_export_present"])

        dropzone_dir = dropzone_root / slot_id
        dropzone_dir.mkdir(parents=True, exist_ok=True)

        recommended_source_filename = f"{slot_id}_{platform.lower()}_real_export.mp4"
        instruction_file = dropzone_dir / "DROP_VIDEO_HERE.txt"

        _write_text(
            instruction_file,
            "\n".join(
                [
                    f"SLOT={slot_id}",
                    f"ASSET_ID={asset_id}",
                    f"PLATFORM={platform}",
                    f"PRIORITY={priority}",
                    f"EXPECTED_SOURCE_FILENAME={recommended_source_filename}",
                    f"TARGET_EXPORT_FILE={expected_export_file}",
                    "MINIMUM_BYTES=1024",
                    "ACCEPTED_EXTENSIONS=.mp4,.mov,.m4v,.webm",
                    "",
                    "HAZ ESTO:",
                    f"1. Exporta el video real para {platform}.",
                    f"2. Renómbralo como {recommended_source_filename}.",
                    f"3. Colócalo dentro de esta carpeta.",
                    "4. No publiques todavía.",
                    "5. Ejecuta el copy plan cuando estén los tres videos.",
                ]
            ),
        )

        slots.append(
            CaptureSlot(
                slot_id=slot_id,
                asset_id=asset_id,
                platform=platform,
                priority=priority,
                expected_export_file=expected_export_file,
                dropzone_dir=str(dropzone_dir),
                dropzone_instruction_file=str(instruction_file),
                recommended_source_filename=recommended_source_filename,
                accepted_extensions=",".join(VIDEO_SUFFIXES),
                minimum_bytes=1024,
                current_real_export_present=real_export_present,
                status="WAITING_FOR_REAL_EXPORT",
            )
        )

    missing_real_asset_count = int(validation["missing_real_asset_count"])
    real_asset_export_count = int(validation["real_asset_export_count"])

    if missing_real_asset_count != 3:
        raise ValueError(f"MISSING_REAL_ASSET_COUNT_BAD={missing_real_asset_count}")
    if real_asset_export_count != 0:
        raise ValueError(f"REAL_ASSET_EXPORT_COUNT_BAD={real_asset_export_count}")

    copy_plan = out_dir / "copy_real_assets_to_handoff_slots.ps1"
    _write_text(copy_plan, _build_copy_plan(slots))

    _write_csv(
        out_dir / "real_asset_capture_slots.csv",
        [
            "slot_id",
            "asset_id",
            "platform",
            "priority",
            "expected_export_file",
            "dropzone_dir",
            "dropzone_instruction_file",
            "recommended_source_filename",
            "accepted_extensions",
            "minimum_bytes",
            "current_real_export_present",
            "status",
        ],
        [asdict(slot) for slot in slots],
    )

    gate = CapturePlacementGate(
        product=product,
        decision=decision,
        total_score=total_score,
        mode="LOCAL_REAL_ASSET_CAPTURE_PLACEMENT_GATE",
        source_validation_json=str(validation_json),
        asset_capture_slot_count=len(slots),
        target_export_path_count=len({slot.expected_export_file for slot in slots}),
        source_dropzone_slot_count=len([slot for slot in slots if Path(slot.dropzone_dir).is_dir()]),
        missing_real_asset_count=missing_real_asset_count,
        real_asset_export_count=real_asset_export_count,
        ready_for_asset_capture_execution=1,
        ready_for_first_manual_zero_spend_publish=0,
        copy_plan_file=str(copy_plan),
        next_action="Create or export three real videos, place them into source_dropzone, then run copy_real_assets_to_handoff_slots.ps1.",
    )

    (out_dir / "real_asset_capture_placement_gate.json").write_text(
        json.dumps(
            {
                "gate": asdict(gate),
                "capture_slots": [asdict(slot) for slot in slots],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )

    md_lines = [
        "# A8-R42O Real Asset Capture Placement Gate",
        "",
        f"Product: `{product}`",
        "",
        "## Status",
        "",
        f"- READY_FOR_ASSET_CAPTURE_EXECUTION={gate.ready_for_asset_capture_execution}",
        f"- READY_FOR_FIRST_MANUAL_ZERO_SPEND_PUBLISH={gate.ready_for_first_manual_zero_spend_publish}",
        f"- MISSING_REAL_ASSET_COUNT={gate.missing_real_asset_count}",
        f"- REAL_ASSET_EXPORT_COUNT={gate.real_asset_export_count}",
        "",
        "## Next action",
        "",
        gate.next_action,
        "",
        "## Slots",
        "",
    ]

    for slot in slots:
        md_lines.extend(
            [
                f"### {slot.slot_id} — {slot.platform}",
                "",
                f"- recommended_source_filename: `{slot.recommended_source_filename}`",
                f"- dropzone_dir: `{slot.dropzone_dir}`",
                f"- expected_export_file: `{slot.expected_export_file}`",
                "",
            ]
        )

    _write_text(out_dir / "real_asset_capture_placement_gate.md", "\n".join(md_lines))

    return gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-json", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    validation_json = Path(args.validation_json).resolve()
    out_dir = Path(args.out_dir).resolve()

    gate = build_gate(validation_json, out_dir)
    output_files = [path for path in out_dir.rglob("*") if path.is_file()]

    print(f"REAL_ASSET_CAPTURE_GATE_JSON={out_dir / 'real_asset_capture_placement_gate.json'}")
    print(f"REAL_ASSET_CAPTURE_GATE_MD={out_dir / 'real_asset_capture_placement_gate.md'}")
    print(f"REAL_ASSET_CAPTURE_SLOTS_CSV={out_dir / 'real_asset_capture_slots.csv'}")
    print(f"COPY_PLAN_FILE={gate.copy_plan_file}")
    print(f"PRODUCT={gate.product}")
    print(f"DECISION={gate.decision}")
    print(f"TOTAL_SCORE={gate.total_score}")
    print(f"ASSET_CAPTURE_SLOT_COUNT={gate.asset_capture_slot_count}")
    print(f"TARGET_EXPORT_PATH_COUNT={gate.target_export_path_count}")
    print(f"SOURCE_DROPZONE_SLOT_COUNT={gate.source_dropzone_slot_count}")
    print(f"MISSING_REAL_ASSET_COUNT={gate.missing_real_asset_count}")
    print(f"REAL_ASSET_EXPORT_COUNT={gate.real_asset_export_count}")
    print(f"READY_FOR_ASSET_CAPTURE_EXECUTION={gate.ready_for_asset_capture_execution}")
    print(f"READY_FOR_FIRST_MANUAL_ZERO_SPEND_PUBLISH={gate.ready_for_first_manual_zero_spend_publish}")
    print(f"OUTPUT_FILE_COUNT={len(output_files)}")
    print("A8_R42O_REAL_ASSET_CAPTURE_PLACEMENT_GATE_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
