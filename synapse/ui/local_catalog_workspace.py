"""A8-R110I2 local catalog intake -> operator workspace HTML.

Minimal operator flow, fully local and deterministic:

    real local CSV catalog
      -> explicit schema validation (per-row honest statuses)
      -> deterministic unit economics (Decimal; price - cost - shipping - fee)
      -> R109A-shaped candidate fixtures (adapter documented in
         docs/a8_r110/LOCAL_CATALOG_INTAKE.md)
      -> existing deterministic ViewModel + R109B workspace renderer
      -> workspace.html + candidates/*.json + intake_report.json

Honesty rules (hard):
- EVALUATING: all economics inputs present and valid; unit economics computed
  from the operator's own numbers. Never an engine verdict, never a
  recommendation: decision.outcome stays EVALUATING with gate REVIEW.
- INPUT_LOW: key economics inputs missing; the candidate renders WITHOUT
  economics. Nothing is invented.
- INVALID_INPUT: malformed/negative numbers, missing identity, duplicate
  product_id, or web-URL/forbidden tokens inside fixture-bound text fields.
  Invalid rows never reach the workspace; they are listed in
  intake_report.json with reasons.
- operator_input stays empty (the ViewModel classifies INPUT_LOW richness),
  so marketing/shopify packs remain disabled until the operator writes a real
  brief. No claims, no copy, no packs are generated here.
- source_url is recorded only in intake_report.json: the offline workspace
  HTML forbids absolute web URLs by contract (R109A forbidden-token scan).

Boundary: no network, no live Dropi/Shopify/Meta, no credentials, no spend,
no fulfillment. The only side effects are local files under --output-dir.
Same CSV bytes -> same output bytes (no timestamps, no uuids, no clock).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from synapse.ui.operator_workbench_renderer import scan_forbidden_tokens
from synapse.ui.operator_workbench_view_model import (
    WorkbenchViewModel,
    build_view_model,
)
from synapse.ui.operator_workbench_visual import render_workspace_html

INTAKE_SCHEMA_VERSION = "a8-r110.local_catalog_workspace.v1"
SOURCE_KIND = "operator_local_catalog_import"
DEFAULT_OUTPUT_DIR = Path("artifacts/a8_r110_local_catalog_workspace")

# Row statuses (honest, mutually exclusive).
STATUS_EVALUATING = "EVALUATING"
STATUS_INPUT_LOW = "INPUT_LOW"
STATUS_INVALID_INPUT = "INVALID_INPUT"

# Operator CSV contract (documented in docs/a8_r110/LOCAL_CATALOG_INTAKE.md).
# All REQUIRED_COLUMNS must exist as headers; economics values may be empty
# per row (-> INPUT_LOW). Identity values may not be empty (-> INVALID_INPUT).
REQUIRED_COLUMNS: tuple[str, ...] = (
    "product_id",
    "title",
    "supplier",
    "category",
    "supplier_price_mxn",
    "shipping_cost_mxn",
    "sale_price_mxn",
)
OPTIONAL_COLUMNS: tuple[str, ...] = ("payment_fee_mxn", "source_url", "notes")

_IDENTITY_COLUMNS: tuple[str, ...] = ("product_id", "title", "supplier")
_ECONOMICS_COLUMNS: tuple[str, ...] = (
    "supplier_price_mxn",
    "shipping_cost_mxn",
    "sale_price_mxn",
)
# Text fields that flow into the fixture (and therefore into offline HTML).
_FIXTURE_TEXT_COLUMNS: tuple[str, ...] = (
    "product_id",
    "title",
    "supplier",
    "category",
    "notes",
)

_MONEY = Decimal("0.01")
_PCT = Decimal("0.1")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class CatalogIntakeError(ValueError):
    """Raised when the CSV file itself cannot be used (not per-row issues)."""


@dataclass(frozen=True)
class CatalogRowResult:
    row_number: int
    product_id: str
    title: str
    status: str
    reasons: tuple[str, ...] = ()
    source_url: str = ""
    notes: str = ""
    fixture_id: str = ""
    economics: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class CatalogIntakeResult:
    csv_name: str
    rows: tuple[CatalogRowResult, ...]
    fixtures: tuple[Mapping[str, Any], ...]

    @property
    def counts(self) -> dict[str, int]:
        counts = {
            STATUS_EVALUATING: 0,
            STATUS_INPUT_LOW: 0,
            STATUS_INVALID_INPUT: 0,
        }
        for row in self.rows:
            counts[row.status] += 1
        return counts


def _slug(value: str) -> str:
    slug = _SLUG_RE.sub("_", value.strip().lower()).strip("_")
    return slug or "row"


def _money(value: str) -> Decimal:
    amount = Decimal(value.strip())
    return amount.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _parse_economics(raw: Mapping[str, str]) -> tuple[Optional[dict[str, Decimal]], list[str], list[str]]:
    """Return (economics-or-None, invalid_reasons, missing_fields)."""
    invalid: list[str] = []
    missing: list[str] = []
    values: dict[str, Decimal] = {}

    for column in _ECONOMICS_COLUMNS:
        text = (raw.get(column) or "").strip()
        if not text:
            missing.append(column)
            continue
        try:
            amount = _money(text)
        except (InvalidOperation, ValueError):
            invalid.append(f"non_numeric:{column}")
            continue
        if amount < 0:
            invalid.append(f"negative:{column}")
            continue
        values[column] = amount

    fee_text = (raw.get("payment_fee_mxn") or "").strip()
    fee = Decimal("0.00")
    if fee_text:
        try:
            fee = _money(fee_text)
        except (InvalidOperation, ValueError):
            invalid.append("non_numeric:payment_fee_mxn")
        else:
            if fee < 0:
                invalid.append("negative:payment_fee_mxn")

    if invalid:
        return None, invalid, missing
    if missing:
        return None, [], missing

    sale = values["sale_price_mxn"]
    if sale <= 0:
        return None, ["non_positive:sale_price_mxn"], []

    cost = values["supplier_price_mxn"]
    shipping = values["shipping_cost_mxn"]
    margin = (sale - cost - shipping - fee).quantize(_MONEY, rounding=ROUND_HALF_UP)
    margin_pct = (margin * Decimal("100") / sale).quantize(_PCT, rounding=ROUND_HALF_UP)

    return (
        {
            "price_mxn": sale,
            "product_cost_mxn": cost,
            "shipping_cost_mxn": shipping,
            "payment_fee_mxn": fee,
            "contribution_margin_mxn": margin,
            "contribution_margin_percent": margin_pct,
            "breakeven_cpa_mxn": margin,
        },
        [],
        [],
    )


def _decimal_to_number(value: Decimal) -> float | int:
    as_float = float(value)
    return int(as_float) if as_float.is_integer() else as_float


def _build_fixture(
    *,
    row_number: int,
    raw: Mapping[str, str],
    status: str,
    economics: Optional[Mapping[str, Decimal]],
    missing_fields: Sequence[str],
    csv_name: str,
) -> dict[str, Any]:
    """Adapter: operator CSV row -> minimal honest R109A-shaped fixture.

    Mapping (documented): sale_price_mxn -> economics.price_mxn,
    supplier_price_mxn -> economics.product_cost_mxn, shipping_cost_mxn ->
    economics.shipping_cost_mxn, payment_fee_mxn -> economics.payment_fee_mxn.
    operator_input stays empty on purpose: richness must classify INPUT_LOW
    until the operator writes a real brief.
    """
    product_id = raw["product_id"].strip()
    fixture_id = f"a8_r110_{_slug(product_id)}"

    if status == STATUS_EVALUATING:
        outcome = "EVALUATING"
        reason = (
            "Candidato importado del catalogo local: economia unitaria calculada"
            " desde los numeros del operador; sin brief todavia, sin veredicto"
            " del motor."
        )
        reason_codes = ["CATALOG_INTAKE", "NO_OPERATOR_BRIEF"]
        caveats = [
            "Sin brief del operador (operator_input vacio): completar antes del sell-prep.",
            "Economia unitaria local; no es forecast ni veredicto del motor.",
        ]
    else:
        outcome = "INPUT_LOW"
        reason = (
            "Candidato importado del catalogo local sin economia completa:"
            " faltan campos clave y no se inventan numeros."
        )
        reason_codes = ["CATALOG_INTAKE", "MISSING_ECONOMICS_INPUTS"]
        caveats = [
            "Campos faltantes en el CSV: " + ", ".join(missing_fields) + ".",
            "Sin brief del operador (operator_input vacio).",
        ]

    fixture: dict[str, Any] = {
        "fixture_id": fixture_id,
        "source_kind": SOURCE_KIND,
        "scenario": "catalog_intake",
        "product": {
            "product_id": product_id,
            "name": raw["title"].strip(),
            "category": (raw.get("category") or "").strip(),
            "supplier": raw["supplier"].strip(),
            "market": "MX",
            "status": "candidate",
        },
        "decision": {
            "outcome": outcome,
            "permission_gate": "REVIEW",
            "reason": reason,
            "reason_codes": reason_codes,
            "caveats": caveats,
        },
        "operator_input": {},
        "evidence": {
            "notes": [
                f"Importado del catalogo CSV local {csv_name} (fila {row_number}).",
                "Intake read-only: sin red, sin escrituras externas, sin credenciales.",
            ]
            + (
                [f"Nota del operador: {raw['notes'].strip()}"]
                if (raw.get("notes") or "").strip()
                else []
            ),
            "artifacts": [csv_name],
        },
    }
    if economics is not None:
        fixture["economics"] = {
            "currency": "MXN",
            **{key: _decimal_to_number(value) for key, value in economics.items()},
            "notes": "Economia unitaria derivada del CSV local del operador;"
            " sin datos de mercado y sin CAC estimado (no se inventa).",
        }
    return fixture


def parse_catalog_csv(csv_path: str | Path) -> CatalogIntakeResult:
    """Parse + validate the operator catalog CSV into honest row results."""
    path = Path(csv_path)
    if not path.is_file():
        raise CatalogIntakeError(f"CSV_NOT_FOUND={path.as_posix()}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        missing_headers = [c for c in REQUIRED_COLUMNS if c not in headers]
        if missing_headers:
            raise CatalogIntakeError(
                "CSV_MISSING_COLUMNS=" + ",".join(missing_headers)
            )
        raw_rows = [
            { (k or "").strip(): (v or "") for k, v in row.items() }
            for row in reader
        ]

    if not raw_rows:
        raise CatalogIntakeError("CSV_EMPTY=no_data_rows")

    rows: list[CatalogRowResult] = []
    fixtures: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    seen_fixture_ids: dict[str, str] = {}

    for index, raw in enumerate(raw_rows, start=2):  # row 1 is the header
        product_id = (raw.get("product_id") or "").strip()
        title = (raw.get("title") or "").strip()
        source_url = (raw.get("source_url") or "").strip()
        notes = (raw.get("notes") or "").strip()

        reasons: list[str] = []
        for column in _IDENTITY_COLUMNS:
            if not (raw.get(column) or "").strip():
                reasons.append(f"missing_identity:{column}")
        if product_id:
            if product_id in seen_ids:
                reasons.append("duplicate:product_id")
            seen_ids.add(product_id)

            fixture_id = f"a8_r110_{_slug(product_id)}"
            previous_product_id = seen_fixture_ids.get(fixture_id)
            if previous_product_id is not None and previous_product_id != product_id:
                reasons.append("duplicate:fixture_id_slug")
            else:
                seen_fixture_ids[fixture_id] = product_id

        economics, invalid_reasons, missing_fields = _parse_economics(raw)
        reasons.extend(invalid_reasons)

        # Fixture-bound text must survive the offline HTML forbidden-token
        # scan (no web URLs, no client tokens). URLs belong in source_url,
        # which only reaches intake_report.json.
        for column in _FIXTURE_TEXT_COLUMNS:
            text = raw.get(column) or ""
            if text and scan_forbidden_tokens(text):
                reasons.append(f"forbidden_token_in_field:{column}")

        if reasons:
            rows.append(
                CatalogRowResult(
                    row_number=index,
                    product_id=product_id,
                    title=title,
                    status=STATUS_INVALID_INPUT,
                    reasons=tuple(sorted(reasons)),
                    source_url=source_url,
                    notes=notes,
                )
            )
            continue

        status = STATUS_EVALUATING if economics is not None else STATUS_INPUT_LOW
        fixture = _build_fixture(
            row_number=index,
            raw=raw,
            status=status,
            economics=economics,
            missing_fields=missing_fields,
            csv_name=path.name,
        )
        fixtures.append(fixture)
        rows.append(
            CatalogRowResult(
                row_number=index,
                product_id=product_id,
                title=title,
                status=status,
                reasons=tuple(f"missing:{name}" for name in missing_fields),
                source_url=source_url,
                notes=notes,
                fixture_id=str(fixture["fixture_id"]),
                economics=fixture.get("economics"),
            )
        )

    return CatalogIntakeResult(csv_name=path.name, rows=tuple(rows), fixtures=tuple(fixtures))


def build_intake_report(result: CatalogIntakeResult) -> dict[str, Any]:
    """Deterministic intake report (no timestamps, no uuids)."""
    return {
        "schema_version": INTAKE_SCHEMA_VERSION,
        "source_kind": SOURCE_KIND,
        "csv_name": result.csv_name,
        "counts": {"rows_total": len(result.rows), **result.counts},
        "rows": [
            {
                "row_number": row.row_number,
                "product_id": row.product_id,
                "title": row.title,
                "status": row.status,
                "reasons": list(row.reasons),
                "fixture_id": row.fixture_id,
                "source_url": row.source_url,
                "notes": row.notes,
            }
            for row in result.rows
        ],
        "boundaries": {
            "no_network": True,
            "no_live_writes": True,
            "no_spend": True,
            "no_fulfillment": True,
            "no_credentials": True,
            "operator_in_control": True,
            "deterministic": True,
        },
    }


def build_view_models(result: CatalogIntakeResult) -> list[WorkbenchViewModel]:
    fixtures = sorted(result.fixtures, key=lambda f: str(f["fixture_id"]))
    return [
        build_view_model(
            fixture,
            source_fixture=f"{result.csv_name}#{fixture['fixture_id']}",
        )
        for fixture in fixtures
    ]


def _clear_generated_outputs(output_dir: Path) -> None:
    """Remove only A8-R110 generated workspace/candidate outputs.

    Reusing --output-dir must never leave stale workspace.html or old
    candidates/*.json when the current CSV produces no valid fixtures.
    Do not delete arbitrary operator files under output_dir.
    """
    workspace_path = output_dir / "workspace.html"
    if workspace_path.exists() or workspace_path.is_symlink():
        workspace_path.unlink()

    candidates_dir = output_dir / "candidates"
    if not candidates_dir.exists():
        return

    for candidate_path in sorted(candidates_dir.glob("*.json")):
        if candidate_path.is_file() or candidate_path.is_symlink():
            candidate_path.unlink()


def build_workspace_from_csv(
    csv_path: str | Path, output_dir: str | Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    """Full local pipeline. Returns a summary dict; writes files under output_dir."""
    result = parse_catalog_csv(csv_path)
    report = build_intake_report(result)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    _clear_generated_outputs(out)

    report_path = out / "intake_report.json"
    with report_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    candidates_dir = out / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    fixture_paths: list[Path] = []
    for fixture in sorted(result.fixtures, key=lambda f: str(f["fixture_id"])):
        target = candidates_dir / f"{fixture['fixture_id']}.json"
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(fixture, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        fixture_paths.append(target)

    workspace_path: Optional[Path] = None
    if result.fixtures:
        view_models = build_view_models(result)
        document = render_workspace_html(view_models)
        workspace_path = out / "workspace.html"
        with workspace_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(document)

    return {
        "counts": report["counts"],
        "report_path": report_path,
        "workspace_path": workspace_path,
        "fixture_paths": fixture_paths,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m synapse.ui.local_catalog_workspace",
        description="A8-R110I2: local operator catalog CSV -> deterministic"
        " workspace HTML (offline, dry-run, no live writes).",
    )
    parser.add_argument("--csv", required=True, help="Path to the local catalog CSV.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Local output directory (default: {DEFAULT_OUTPUT_DIR.as_posix()}).",
    )
    args = parser.parse_args(argv)

    try:
        summary = build_workspace_from_csv(args.csv, args.output_dir)
    except CatalogIntakeError as exc:
        print(f"intake_error={exc}")
        return 2

    counts = summary["counts"]
    print(f"rows_total={counts['rows_total']}")
    print(f"evaluating={counts[STATUS_EVALUATING]}")
    print(f"input_low={counts[STATUS_INPUT_LOW]}")
    print(f"invalid_input={counts[STATUS_INVALID_INPUT]}")
    print(f"report={Path(summary['report_path']).as_posix()}")
    if summary["workspace_path"] is None:
        print("workspace=NONE (sin candidatos evaluables; revisar intake_report.json)")
        return 3
    print(f"workspace={Path(summary['workspace_path']).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
