"""A8-R110I2 — local catalog intake -> workspace HTML tests.

Covers: valid CSV produces financially evaluated candidates; incomplete rows
degrade to INPUT_LOW without inventing numbers; invalid rows never reach the
workspace; the rendered HTML carries no network/write tokens; the whole
pipeline is deterministic; and the frozen R109A/R109B fixtures keep rendering
untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synapse.ui import local_catalog_workspace as intake
from synapse.ui import operator_workbench_renderer as wb_renderer
from synapse.ui import operator_workbench_view_model as wb_vm
from synapse.ui import operator_workbench_visual as wb_visual

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = REPO_ROOT / "tests" / "fixtures" / "a8_r110_catalog"
NOMINAL_CSV = CATALOG_DIR / "catalog_nominal.csv"
MIXED_CSV = CATALOG_DIR / "catalog_mixed.csv"
R109A_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "a8_r109a"

R110_FILES = (
    REPO_ROOT / "synapse" / "ui" / "local_catalog_workspace.py",
    Path(__file__).resolve(),
    REPO_ROOT / "docs" / "a8_r110" / "LOCAL_CATALOG_INTAKE.md",
)


def _forbidden_tokens() -> tuple[str, ...]:
    halves = (
        ("fetch", "("),
        ("XMLHttp", "Request"),
        ("<script ", "src="),
        ("<link ", "rel="),
        ("http", "://"),
        ("https", "://"),
        ("<form ", "action="),
        ("requests", ".post"),
        ("httpx", ".post"),
        ("create_product", "("),
        ("publish_campaign", "("),
        ("forward_shopify_order", "("),
    )
    return tuple(left + right for left, right in halves)


# --- 1. valid CSV -> financially evaluated candidates -------------------------


def test_nominal_csv_produces_evaluated_candidates(tmp_path: Path) -> None:
    summary = intake.build_workspace_from_csv(NOMINAL_CSV, tmp_path)

    assert summary["counts"] == {
        "rows_total": 3,
        "EVALUATING": 3,
        "INPUT_LOW": 0,
        "INVALID_INPUT": 0,
    }
    assert summary["workspace_path"] is not None
    assert Path(summary["workspace_path"]).is_file()
    assert len(summary["fixture_paths"]) == 3

    # Unit economics come from the operator's own numbers, Decimal-exact.
    by_id = {
        json.loads(p.read_text(encoding="utf-8"))["product"]["product_id"]: json.loads(
            p.read_text(encoding="utf-8")
        )
        for p in summary["fixture_paths"]
    }
    row1 = by_id["cat-001"]["economics"]
    assert row1["price_mxn"] == 349.0
    assert row1["product_cost_mxn"] == 128.0
    assert row1["shipping_cost_mxn"] == 55.0
    assert row1["payment_fee_mxn"] == 14.0
    assert row1["contribution_margin_mxn"] == 152.0  # 349-128-55-14
    assert row1["contribution_margin_percent"] == 43.6
    assert row1["breakeven_cpa_mxn"] == 152.0
    # Empty fee column defaults to 0.00 (documented; never invented > 0).
    assert by_id["cat-002"]["economics"]["payment_fee_mxn"] == 0.0

    document = Path(summary["workspace_path"]).read_text(encoding="utf-8")
    assert 'data-mode="workspace_mode"' in document
    for name in (
        "Organizador de Cables Compacto",
        "Soporte Plegable de Laptop",
        "Lampara LED de Escritorio",
    ):
        assert name in document, f"candidate missing from workspace: {name}"
    assert "MXN 152.00" in document


def test_intake_candidates_stay_honest_in_workspace(tmp_path: Path) -> None:
    summary = intake.build_workspace_from_csv(NOMINAL_CSV, tmp_path)
    document = Path(summary["workspace_path"]).read_text(encoding="utf-8")

    # No brief yet -> INPUT_LOW richness; never a sell-prep surface.
    assert "INPUT_LOW" in document
    assert 'data-cta="prepare"' not in document
    assert "selling_packet_export" not in document
    # No commercial copy payloads may exist (packs disabled). The only
    # payload allowed is the canonical empty learning snapshot machinery.
    assert 'data-copy-target="payload_shopify_' not in document
    assert 'data-copy-target="payload_marketing_' not in document
    assert "executive_operating_brief" not in document
    # Marketing/Shopify packs stay disabled: no invented claims or copy.
    assert 'data-shopify-disabled="true"' in document
    assert 'data-marketing-disabled="true"' in document
    # Honest provenance: operator catalog, not a frozen test fixture.
    assert intake.SOURCE_KIND in document
    # The decision stays EVALUATING with gate REVIEW (no engine verdict).
    fixtures = [
        json.loads(p.read_text(encoding="utf-8")) for p in summary["fixture_paths"]
    ]
    for fixture in fixtures:
        assert fixture["decision"]["outcome"] == "EVALUATING"
        assert fixture["decision"]["permission_gate"] == "REVIEW"
        assert fixture["operator_input"] == {}
        assert "marketing" not in fixture
        assert "shopify" not in fixture
        assert "claim_guard" not in fixture


# --- 1b. provenance copy: CSV local, never frozen fixture ----------------------

# Copy the local-catalog workspace must NOT inherit from the R109B fixture flow.
_FIXTURE_COPY_FORBIDDEN = (
    "FIXTURE LOCAL - OFFLINE",
    "Datos de fixture congelado",
    "fixture: a8_r110",
    "Pipeline de candidatos (solo fixture)",
    "Candidatos embebidos del fixture congelado",
    "mismo fixture, mismo output",
)

# Copy the local-catalog workspace MUST communicate instead.
_CSV_LOCAL_COPY_REQUIRED = (
    "CSV LOCAL - OFFLINE",
    "operator_local_catalog_import",
    "Datos importados desde CSV local",
    "Candidatos importados desde CSV local",
    "sin discovery en vivo",
    "sin escrituras",
    "sin red",
)


def test_local_catalog_workspace_speaks_csv_local_not_fixture(tmp_path: Path) -> None:
    summary = intake.build_workspace_from_csv(NOMINAL_CSV, tmp_path)
    document = Path(summary["workspace_path"]).read_text(encoding="utf-8")

    for bad in _FIXTURE_COPY_FORBIDDEN:
        assert bad not in document, f"leftover fixture copy in R110 workspace: {bad!r}"

    for required in _CSV_LOCAL_COPY_REQUIRED:
        assert required in document, f"missing CSV-local copy in R110 workspace: {required!r}"

    # At least one accented/plain "catalogo CSV local" chain label must survive.
    assert ("Catálogo CSV local" in document) or ("catalogo CSV local" in document)


def test_frozen_fixtures_keep_fixture_copy() -> None:
    """The conditional switch must not bleed into the R109A/R109B fixtures:
    a non-catalog source_kind still renders the frozen-fixture wording."""
    view_model = wb_vm.build_view_model_from_path(
        R109A_FIXTURE_DIR / "recommended.json"
    )
    document = wb_visual.render_visual_html(view_model)
    assert "FIXTURE LOCAL - OFFLINE" in document
    assert "CSV LOCAL - OFFLINE" not in document
    assert "Pipeline de candidatos (solo fixture)" in document


# --- 2. incomplete rows -> INPUT_LOW, nothing invented -------------------------


def test_mixed_csv_statuses_are_honest(tmp_path: Path) -> None:
    summary = intake.build_workspace_from_csv(MIXED_CSV, tmp_path)

    assert summary["counts"] == {
        "rows_total": 6,
        "EVALUATING": 1,
        "INPUT_LOW": 1,
        "INVALID_INPUT": 4,
    }

    report = json.loads(Path(summary["report_path"]).read_text(encoding="utf-8"))
    by_row = {row["row_number"]: row for row in report["rows"]}

    assert by_row[2]["status"] == "EVALUATING"
    assert by_row[3]["status"] == "INPUT_LOW"
    assert by_row[3]["reasons"] == ["missing:sale_price_mxn"]
    assert by_row[4]["status"] == "INVALID_INPUT"
    assert "negative:supplier_price_mxn" in by_row[4]["reasons"]
    assert by_row[5]["status"] == "INVALID_INPUT"
    assert "missing_identity:title" in by_row[5]["reasons"]
    assert by_row[6]["status"] == "INVALID_INPUT"
    assert "duplicate:product_id" in by_row[6]["reasons"]
    assert by_row[7]["status"] == "INVALID_INPUT"
    assert "forbidden_token_in_field:title" in by_row[7]["reasons"]

    # INPUT_LOW candidate renders WITHOUT economics: nothing invented.
    input_low_fixture = next(
        json.loads(p.read_text(encoding="utf-8"))
        for p in summary["fixture_paths"]
        if json.loads(p.read_text(encoding="utf-8"))["product"]["product_id"] == "cat-101"
    )
    assert "economics" not in input_low_fixture
    assert input_low_fixture["decision"]["outcome"] == "INPUT_LOW"

    document = Path(summary["workspace_path"]).read_text(encoding="utf-8")
    # Invalid rows never reach the workspace.
    assert "Cargador Triple Invalido" not in document
    assert "Difusor Duplicado" not in document
    assert "Sospechoso" not in document
    # The INPUT_LOW candidate shows honest empty money metrics.
    assert "Mini Aspiradora de Escritorio" in document
    assert "Sin metricas de dinero" in document
    # source_url content stays in the report, never in the offline HTML.
    assert "URLMARKER_dropi_producto_101" not in document
    assert by_row[3]["source_url"] == "URLMARKER_dropi_producto_101"


def test_csv_file_level_errors_are_explicit(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"
    with pytest.raises(intake.CatalogIntakeError, match="CSV_NOT_FOUND"):
        intake.parse_catalog_csv(missing)

    bad_header = tmp_path / "bad_header.csv"
    bad_header.write_text("product_id,title\nx,y\n", encoding="utf-8")
    with pytest.raises(intake.CatalogIntakeError, match="CSV_MISSING_COLUMNS"):
        intake.parse_catalog_csv(bad_header)

    empty = tmp_path / "empty.csv"
    empty.write_text(
        "product_id,title,supplier,category,supplier_price_mxn,"
        "shipping_cost_mxn,sale_price_mxn\n",
        encoding="utf-8",
    )
    with pytest.raises(intake.CatalogIntakeError, match="CSV_EMPTY"):
        intake.parse_catalog_csv(empty)


# --- 3. no network/write tokens in output or R110 sources ----------------------


def test_workspace_html_has_no_forbidden_tokens(tmp_path: Path) -> None:
    summary = intake.build_workspace_from_csv(MIXED_CSV, tmp_path)
    document = Path(summary["workspace_path"]).read_text(encoding="utf-8")

    for token in _forbidden_tokens():
        assert token not in document, f"forbidden token in workspace HTML: {token}"
    assert wb_renderer.scan_forbidden_tokens(document) == []

    # The report (local JSON evidence, never HTML) faithfully records the
    # rejected row's offending text for traceability — the row itself was
    # kept out of the workspace.
    report = json.loads(Path(summary["report_path"]).read_text(encoding="utf-8"))
    rejected = next(r for r in report["rows"] if r["row_number"] == 7)
    assert rejected["status"] == "INVALID_INPUT"
    assert "forbidden_token_in_field:title" in rejected["reasons"]


@pytest.mark.parametrize("path", R110_FILES, ids=lambda p: p.name)
def test_r110_files_have_no_forbidden_tokens(path: Path) -> None:
    assert path.is_file(), f"missing R110 file: {path}"
    content = path.read_text(encoding="utf-8")
    for token in _forbidden_tokens():
        assert token not in content, f"forbidden token {token!r} in {path.name}"


# --- 4. determinism -------------------------------------------------------------


def test_pipeline_is_deterministic(tmp_path: Path) -> None:
    first = intake.build_workspace_from_csv(NOMINAL_CSV, tmp_path / "run1")
    second = intake.build_workspace_from_csv(NOMINAL_CSV, tmp_path / "run2")

    html1 = Path(first["workspace_path"]).read_bytes()
    html2 = Path(second["workspace_path"]).read_bytes()
    assert html1 == html2, "workspace HTML must be byte-identical per CSV"

    report1 = Path(first["report_path"]).read_bytes()
    report2 = Path(second["report_path"]).read_bytes()
    assert report1 == report2, "intake report must be byte-identical per CSV"

    for p1, p2 in zip(first["fixture_paths"], second["fixture_paths"]):
        assert Path(p1).read_bytes() == Path(p2).read_bytes()


# --- 5. frozen R109A/R109B fixtures keep rendering untouched --------------------


@pytest.mark.parametrize(
    "name", ("recommended", "blocked", "low_input", "empty_shortlist")
)
def test_frozen_r109a_fixtures_still_render(name: str) -> None:
    view_model = wb_vm.build_view_model_from_path(R109A_FIXTURE_DIR / f"{name}.json")
    document = wb_visual.render_visual_html(view_model)
    assert document.startswith("<!DOCTYPE html>")
    assert wb_renderer.scan_forbidden_tokens(document) == []


# --- 6. CLI ----------------------------------------------------------------------


def test_cli_nominal_exit_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = intake.main(
        ["--csv", str(NOMINAL_CSV), "--output-dir", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "rows_total=3" in out
    assert "evaluating=3" in out
    assert "workspace=" in out
    assert (tmp_path / "workspace.html").is_file()
    assert (tmp_path / "intake_report.json").is_file()


def test_cli_error_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = intake.main(
        ["--csv", str(tmp_path / "nope.csv"), "--output-dir", str(tmp_path)]
    )
    assert exit_code == 2
    assert "intake_error=" in capsys.readouterr().out

    all_invalid = tmp_path / "all_invalid.csv"
    all_invalid.write_text(
        "product_id,title,supplier,category,supplier_price_mxn,"
        "shipping_cost_mxn,sale_price_mxn\n"
        "x1,,Prov,cat,10,5,100\n",
        encoding="utf-8",
    )
    exit_code = intake.main(
        ["--csv", str(all_invalid), "--output-dir", str(tmp_path / "inv")]
    )
    out = capsys.readouterr().out
    assert exit_code == 3
    assert "invalid_input=1" in out
    assert "workspace=NONE" in out
    assert not (tmp_path / "inv" / "workspace.html").exists()
    # The report still exists so the operator can see why.
    assert (tmp_path / "inv" / "intake_report.json").is_file()

def _write_a8_r110i3_catalog(path, rows):
    import csv

    fieldnames = [
        "product_id",
        "title",
        "supplier",
        "category",
        "supplier_price_mxn",
        "shipping_cost_mxn",
        "sale_price_mxn",
        "payment_fee_mxn",
        "source_url",
        "notes",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_a8_r110_rejects_colliding_fixture_slugs(tmp_path):
    import json

    from synapse.ui.local_catalog_workspace import (
        STATUS_EVALUATING,
        STATUS_INVALID_INPUT,
        build_workspace_from_csv,
        parse_catalog_csv,
    )

    csv_path = tmp_path / "colliding_slugs.csv"
    rows = [
        {
            "product_id": "cat-1",
            "title": "Producto Uno",
            "supplier": "Proveedor A",
            "category": "hogar",
            "supplier_price_mxn": "100.00",
            "shipping_cost_mxn": "20.00",
            "sale_price_mxn": "250.00",
            "payment_fee_mxn": "5.00",
            "source_url": "",
            "notes": "",
        },
        {
            "product_id": "cat 1",
            "title": "Producto Dos",
            "supplier": "Proveedor B",
            "category": "hogar",
            "supplier_price_mxn": "110.00",
            "shipping_cost_mxn": "22.00",
            "sale_price_mxn": "260.00",
            "payment_fee_mxn": "6.00",
            "source_url": "",
            "notes": "",
        },
    ]
    _write_a8_r110i3_catalog(csv_path, rows)

    result = parse_catalog_csv(csv_path)
    assert result.counts[STATUS_EVALUATING] == 1
    assert result.counts[STATUS_INVALID_INPUT] == 1
    assert len(result.fixtures) == 1

    invalid_rows = [row for row in result.rows if row.status == STATUS_INVALID_INPUT]
    assert len(invalid_rows) == 1
    assert "duplicate:fixture_id_slug" in invalid_rows[0].reasons

    out_dir = tmp_path / "workspace"
    summary = build_workspace_from_csv(csv_path, out_dir)
    candidate_files = sorted(path.name for path in (out_dir / "candidates").glob("*.json"))
    assert candidate_files == ["a8_r110_cat_1.json"]
    assert len(summary["fixture_paths"]) == 1

    report = json.loads((out_dir / "intake_report.json").read_text(encoding="utf-8"))
    assert report["counts"][STATUS_EVALUATING] == 1
    assert report["counts"][STATUS_INVALID_INPUT] == 1
    assert any(
        "duplicate:fixture_id_slug" in row["reasons"]
        for row in report["rows"]
        if row["status"] == STATUS_INVALID_INPUT
    )


def test_a8_r110_reused_output_dir_clears_stale_workspace_for_all_invalid_csv(tmp_path):
    import json

    from synapse.ui.local_catalog_workspace import (
        STATUS_EVALUATING,
        STATUS_INVALID_INPUT,
        build_workspace_from_csv,
    )

    out_dir = tmp_path / "reused_output"

    valid_csv = tmp_path / "valid.csv"
    _write_a8_r110i3_catalog(
        valid_csv,
        [
            {
                "product_id": "cat-valid",
                "title": "Producto Valido",
                "supplier": "Proveedor A",
                "category": "hogar",
                "supplier_price_mxn": "100.00",
                "shipping_cost_mxn": "20.00",
                "sale_price_mxn": "250.00",
                "payment_fee_mxn": "5.00",
                "source_url": "",
                "notes": "",
            }
        ],
    )

    first_summary = build_workspace_from_csv(valid_csv, out_dir)
    assert first_summary["workspace_path"] == out_dir / "workspace.html"
    assert (out_dir / "workspace.html").exists()
    assert sorted(path.name for path in (out_dir / "candidates").glob("*.json")) == [
        "a8_r110_cat_valid.json"
    ]

    invalid_csv = tmp_path / "all_invalid.csv"
    _write_a8_r110i3_catalog(
        invalid_csv,
        [
            {
                "product_id": "",
                "title": "",
                "supplier": "",
                "category": "hogar",
                "supplier_price_mxn": "not-a-number",
                "shipping_cost_mxn": "20.00",
                "sale_price_mxn": "250.00",
                "payment_fee_mxn": "5.00",
                "source_url": "",
                "notes": "",
            }
        ],
    )

    second_summary = build_workspace_from_csv(invalid_csv, out_dir)
    assert second_summary["workspace_path"] is None
    assert second_summary["fixture_paths"] == []
    assert not (out_dir / "workspace.html").exists()
    assert sorted((out_dir / "candidates").glob("*.json")) == []

    report = json.loads((out_dir / "intake_report.json").read_text(encoding="utf-8"))
    assert report["counts"][STATUS_EVALUATING] == 0
    assert report["counts"][STATUS_INVALID_INPUT] == 1
