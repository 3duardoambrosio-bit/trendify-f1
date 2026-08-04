from __future__ import annotations

import copy
import csv
import hashlib
import html
import io
import json
import os
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

import pytest

import synapse.integration.system_checkpoint_e2e_local as checkpoint
from scripts.shopify_export_from_canonical import (
    SHOPIFY_DRAFT_SAFETY_TAGS,
    SHOPIFY_FIELDNAMES,
    ShopifyDraftExportError,
    build_shopify_draft_row,
    serialize_shopify_draft_export,
)
from synapse.financial.adapters import candidate_to_financial_input
from synapse.financial.evaluation import (
    FinancialAssumptions,
    evaluate_financials,
)
from synapse.integration.canonical_product_bridge import (
    APPROVAL_SCOPE,
    APPROVAL_STATUS,
    SCHEMA_VERSION as PROMOTION_SCHEMA_VERSION,
    canonicalize_local_product_candidate,
    local_product_candidate_sha256,
)
from synapse.integration.local_catalog_to_methodology import (
    enrich_local_catalog_fixture_with_methodology,
)
from synapse.ui.local_catalog_workspace import parse_catalog_csv
from synapse.ui.storefront_customer_copy import customer_copy_sha256


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_ID = "local-cable-001"
DESCRIPTION = "Organizes everyday desk cables in a compact holder."
FACT = "Keeps everyday desk cables grouped."
PROOF = "Operator-supplied local measurements and product photo."


@dataclass
class InputSet:
    value: checkpoint.SystemCheckpointInput
    paths: dict[str, Path]


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _catalog_text(*, duplicate: bool = False) -> str:
    row = (
        f"{PRODUCT_ID},Local Desk Cable Organizer,Local Supplier,"
        "office,250.00,10.00,999.00,5.00,,Operator sample\n"
    )
    return (
        "product_id,title,supplier,category,supplier_price_mxn,"
        "shipping_cost_mxn,sale_price_mxn,payment_fee_mxn,"
        "source_url,notes\n"
        + row
        + (row if duplicate else "")
    )


def _financial_contract(
    catalog_path: Path,
    financial_input_path: Path,
    methodology_path: Path,
) -> tuple[object, object, dict, dict]:
    fixture = dict(parse_catalog_csv(catalog_path).fixtures[0])
    operator_input = json.loads(
        financial_input_path.read_text(encoding="utf-8")
    )
    economics = fixture["economics"]
    financial_input = candidate_to_financial_input(
        {
            "product_id": fixture["product"]["product_id"],
            "name": fixture["product"]["name"],
            "price": economics["price_mxn"],
            "landed_cost": (
                Decimal(str(economics["product_cost_mxn"]))
                + Decimal(str(economics["shipping_cost_mxn"]))
            ),
            "estimated_cac": operator_input["estimated_cac"],
            "expected_units": operator_input.get("expected_units", 1),
        }
    )
    assumptions = FinancialAssumptions(
        payment_fee_pct=Decimal("0"),
        payment_fixed_fee=Decimal(str(economics["payment_fee_mxn"])),
    )
    financial_result = evaluate_financials(
        financial_input,
        assumptions=assumptions,
    )
    decision_record = checkpoint.build_checkpoint_decision_record(
        financial_result
    )
    methodology_context = json.loads(
        methodology_path.read_text(encoding="utf-8")
    )
    enriched_fixture = enrich_local_catalog_fixture_with_methodology(
        fixture,
        methodology_context,
    )
    snapshot = canonicalize_local_product_candidate(
        enriched_fixture,
        financial_input,
    )
    return enriched_fixture, financial_input, decision_record, snapshot


def _build_inputs(
    tmp_path: Path,
    *,
    output_name: str = "output",
    sample_input: bool = True,
) -> InputSet:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    catalog = inputs / "catalog.csv"
    catalog.write_text(
        _catalog_text(),
        encoding="utf-8",
        newline="\n",
    )

    financial = inputs / "financial_assumptions.json"
    _write_json(
        financial,
        {
            "product_id": PRODUCT_ID,
            "estimated_cac": "180.00",
            "expected_units": 1,
        },
    )
    methodology = inputs / "methodology_context.json"
    _write_json(
        methodology,
        {
            "product_facts": [FACT],
            "product_id": PRODUCT_ID,
            "buyer_state": "problem-aware",
            "proof_available": [PROOF],
            "claim_risk": "low",
            "channel": "local_preview",
            "margin_profile": "acceptable",
            "category": "office",
            "candidate_output": DESCRIPTION,
        },
    )
    customer_copy = inputs / "customer_copy.json"
    copy_value = {
        "product_id": PRODUCT_ID,
        "title": "Local Desk Cable Organizer",
        "description": DESCRIPTION,
        "facts": [FACT],
        "proof": [PROOF],
    }
    _write_json(customer_copy, copy_value)

    copy_approval = inputs / "copy_approval.json"
    _write_json(
        copy_approval,
        {
            "status": "APPROVED_FOR_LOCAL_PREVIEW",
            "scope": "LOCAL_PREVIEW_ONLY",
            "approved_copy_sha256": customer_copy_sha256(copy_value),
            "publication_authorized": False,
            "external_writes_authorized": False,
        },
    )

    fixture, financial_input, decision_record, snapshot = (
        _financial_contract(catalog, financial, methodology)
    )
    promotion_approval = inputs / "promotion_approval.json"
    _write_json(
        promotion_approval,
        {
            "schema_version": PROMOTION_SCHEMA_VERSION,
            "status": APPROVAL_STATUS,
            "scope": APPROVAL_SCOPE,
            "operator_id": "operator-local-test",
            "approval_record_id": "checkpoint-approval-local-001",
            "candidate_id": PRODUCT_ID,
            "candidate_sha256": local_product_candidate_sha256(
                fixture,
                financial_input,
            ),
            "decision_run_id": decision_record["run_id"],
            "financial_decision": decision_record[
                "financial_decision"
            ],
            "final_decision": decision_record["final_decision"],
            "publication_authorized": False,
            "external_writes_authorized": False,
            "spend_authorized": False,
            "fulfillment_authorized": False,
        },
    )

    paths = {
        "catalog": catalog,
        "financial": financial,
        "methodology": methodology,
        "customer_copy": customer_copy,
        "promotion_approval": promotion_approval,
        "copy_approval": copy_approval,
    }
    value = checkpoint.SystemCheckpointInput(
        catalog_csv=catalog,
        product_id=PRODUCT_ID,
        methodology_context_json=methodology,
        customer_copy_json=customer_copy,
        promotion_approval_json=promotion_approval,
        copy_approval_json=copy_approval,
        financial_assumptions_json=financial,
        output_dir=tmp_path / output_name,
        sample_input=sample_input,
    )
    assert snapshot["candidate_id"] == PRODUCT_ID
    return InputSet(value=value, paths=paths)


def _assert_no_output(value: checkpoint.SystemCheckpointInput) -> None:
    output = Path(value.output_dir)
    assert not output.exists() or list(output.iterdir()) == []


def _cli_args(value: checkpoint.SystemCheckpointInput) -> list[str]:
    args = [
        "--catalog-csv",
        str(value.catalog_csv),
        "--product-id",
        value.product_id,
        "--methodology-context-json",
        str(value.methodology_context_json),
        "--customer-copy-json",
        str(value.customer_copy_json),
        "--promotion-approval-json",
        str(value.promotion_approval_json),
        "--copy-approval-json",
        str(value.copy_approval_json),
        "--financial-assumptions-json",
        str(value.financial_assumptions_json),
        "--output-dir",
        str(value.output_dir),
    ]
    if value.sample_input:
        args.append("--sample-input")
    return args


def test_nominal_flow_writes_exactly_eleven_truthful_artifacts(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)

    result = checkpoint.run_system_checkpoint(prepared.value)

    assert result.status == "PASS"
    assert result.final_decision == "READY_FOR_REVIEW"
    assert result.fixture_used is False
    assert result.network_used is False
    assert result.external_write is False
    assert result.live_action is False
    assert result.shopify_api_called is False
    assert result.published is False

    output = Path(prepared.value.output_dir)
    assert sorted(path.name for path in output.iterdir()) == sorted(
        checkpoint.ARTIFACT_FILENAMES
    )
    assert set(result.artifact_sha256) == set(
        checkpoint.ARTIFACT_FILENAMES
    )
    checkpoint_result = json.loads(
        (output / "checkpoint_result.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (output / "evidence_manifest.json").read_text(encoding="utf-8")
    )
    trace = json.loads(
        (output / "execution_trace.json").read_text(encoding="utf-8")
    )
    methodology = json.loads(
        (output / "methodology_result.json").read_text(encoding="utf-8")
    )
    shopify = (output / "shopify_draft_export.csv").read_text(
        encoding="utf-8"
    )
    report = (output / "checkpoint_report.html").read_text(
        encoding="utf-8"
    )
    workspace = (output / "workspace.html").read_text(encoding="utf-8")
    financial = json.loads(
        (output / "financial_result.json").read_text(encoding="utf-8")
    )
    decision = json.loads(
        (output / "decision_record.json").read_text(encoding="utf-8")
    )
    canonical = json.loads(
        (output / "canonical_product.json").read_text(encoding="utf-8")
    )
    storefront = json.loads(
        (output / "storefront_read_model.json").read_text(encoding="utf-8")
    )

    assert len(checkpoint.ARTIFACT_FILENAMES) == 11
    assert checkpoint_result["sample_input"] is True
    assert checkpoint_result["commercial_evidence"] is False
    assert checkpoint_result["fixture_used"] is False
    assert manifest["network_used"] is False
    assert manifest["external_write"] is False
    assert manifest["live_action"] is False
    assert manifest["publication_authorized"] is False
    assert len(manifest["input_files"]) == 6
    assert len(manifest["output_files"]) == 10
    assert manifest["code_identity"][
        "execution_identity_requires_source_hashes"
    ] is True
    assert set(manifest["code_identity"]["source_file_sha256"]) == set(
        checkpoint.SOURCE_IDENTITY_RELATIVE_PATHS
    )
    for relative, digest in manifest["code_identity"][
        "source_file_sha256"
    ].items():
        assert hashlib.sha256(
            (REPO_ROOT / relative).read_bytes()
        ).hexdigest() == digest
    assert manifest["contracts"]["operator_workbench"] == (
        checkpoint.WORKBENCH_SCHEMA_VERSION
    )
    assert manifest["authorities"]["operator_workbench"] == (
        "synapse.ui.operator_workbench_visual.render_workspace_html"
    )
    assert manifest["authorities"]["operator_workbench_view_model"] == (
        "synapse.ui.operator_workbench_view_model.build_view_model"
    )
    assert "workspace.html" in manifest["output_files"]
    for filename, record in manifest["output_files"].items():
        assert hashlib.sha256(
            (output / filename).read_bytes()
        ).hexdigest() == record["sha256"]
    manifest_basis = manifest.pop("manifest_basis_sha256")
    expected_basis = hashlib.sha256(
        (
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    assert manifest_basis == expected_basis

    expected_trace_steps = [
        "catalog_input",
        "strict_product_normalization",
        "financial_operator_input",
        "financial_evaluation",
        "checkpoint_decision",
        "methodology_context",
        "methodology_enrichment",
        "customer_copy",
        "customer_copy_validation",
        "customer_copy_methodology_binding",
        "promotion_approval",
        "promotion_approval_validation",
        "customer_copy_approval",
        "customer_copy_approval_validation",
        "canonical_product_promotion",
        "storefront_read_model",
        "shopify_draft_export",
        "operator_workbench",
        "evidence_manifest",
        "operator_html_report",
    ]
    assert [
        step["step_name"] for step in trace["steps"]
    ] == expected_trace_steps
    required_trace_fields = {
        "step_name",
        "input_contract",
        "output_contract",
        "source_file_symbol",
        "status",
        "execution",
        "fixture_used",
        "external_write",
        "input_sha256",
        "output_sha256",
        "digest_reason",
        "blocking_reason",
    }
    assert all(
        set(step) == required_trace_fields
        and step["status"] == "PASS"
        and step["fixture_used"] is False
        and step["external_write"] is False
        for step in trace["steps"]
    )
    workbench_trace = next(
        step for step in trace["steps"]
        if step["step_name"] == "operator_workbench"
    )
    assert workbench_trace["output_contract"] == checkpoint.WORKBENCH_SCHEMA_VERSION
    assert workbench_trace["source_file_symbol"] == (
        "synapse.ui.operator_workbench_visual.render_workspace_html"
    )
    assert workbench_trace["output_sha256"] == hashlib.sha256(
        (output / "workspace.html").read_bytes()
    ).hexdigest()

    for marker in (
        'data-renderer="operator_workbench_visual"',
        'data-mode="workspace_mode"',
        "operator_session_gate",
        "command_center",
        "decision_center",
        "product_lab",
        "economics",
        "shopify_studio",
        "marketing_engine",
        "safety_claim_guard",
        "evidence",
        "learning_feedback",
        "blocked_queue",
    ):
        assert marker in workspace

    assert PRODUCT_ID in workspace
    assert "Local Desk Cable Organizer" in workspace
    assert "operator_local_catalog_import" in workspace
    assert "REVIEW_REQUIRED" in workspace
    assert "READY_FOR_REVIEW" in workspace
    assert decision["run_id"] in workspace
    assert canonical["source_kind"] in workspace
    assert storefront["products"][0]["public_content"]["title"] in workspace
    assert DESCRIPTION in workspace

    # A8-R113.2 functional-truth projection: current adapter custody, truthful
    # local context, real primary action target, and boundary/gap separation.
    assert checkpoint._git_head() in workspace
    assert "system_checkpoint_projection_adapter" in workspace
    assert "checkpoint_local_pending_external_audit" in workspace
    assert "A8-R113.2" in workspace
    assert "Contexto local del operador" in workspace
    assert "No es un inicio de sesion ni autenticacion" in workspace
    assert (
        'data-cta="next_action" data-nav-module="evidence">'
        "Siguiente accion - Revisar la evidencia del checkpoint."
    ) in workspace
    assert "1 GAP / SIN PUBLICAR" in workspace
    assert "Boundary deliberado" in workspace
    assert "2 FALTAN" not in workspace

    drivers_start = workspace.index('data-drivers="top_drivers"')
    blockers_start = workspace.index('data-blockers="top_blockers"', drivers_start)
    blockers_end = workspace.index('class="sc-next"', blockers_start)
    assert "PASS_HEALTHY_UNIT_ECONOMICS" in workspace[drivers_start:blockers_start]
    assert "PASS_HEALTHY_UNIT_ECONOMICS" not in workspace[blockers_start:blockers_end]

    base = financial["scenarios"]["base"]
    canonical_economics = canonical["economics"]
    product_cost = Decimal(
        str(canonical_economics["product_cost_mxn"])
    )
    shipping_cost = Decimal(
        str(canonical_economics["shipping_cost_mxn"])
    )
    payment_fee = Decimal(
        str(canonical_economics["payment_fee_mxn"])
    )
    assert Decimal(str(base["landed_cost"])) == (
        product_cost + shipping_cost
    )
    for amount in (
        base["price"],
        product_cost,
        shipping_cost,
        payment_fee,
        base["contribution_margin"],
        base["break_even_cac"],
    ):
        assert f"MXN {Decimal(str(amount)):.2f}" in workspace

    for value in (
        methodology["decision"]["selected_rule_id"],
        methodology["decision"]["selected_framework"],
    ):
        assert str(value) in workspace
    escaped_safe_output = html.escape(
        str(methodology["decision"]["safe_output"]),
        quote=True,
    )
    assert escaped_safe_output in workspace

    workspace_lower = workspace.casefold()
    for marker in (
        "network_used=false",
        "external_write=false",
        "live_action=false",
        "publication_authorized=false",
        "shopify_api_called=false",
        "commercial_evidence=false",
        "operator_in_control",
    ):
        assert marker in workspace_lower
    for forbidden_claim in (
        "published=true",
        "publication_authorized=true",
        "product-market fit confirmed",
        "market validated",
        "commercial readiness confirmed",
        "guaranteed sales",
    ):
        assert forbidden_claim not in workspace_lower

    assert (output / "checkpoint_report.html").is_file()
    assert (output / "workspace.html").is_file()

    for marker in (
        "shopify_mode=draft_export",
        "published=false",
        "external_write=false",
        "shopify_api_called=false",
        "operator_publication_approval=false",
    ):
        assert marker in shopify
    assert ",FALSE," in shopify
    assert shopify.rstrip().endswith(",draft")
    assert "SAMPLE INPUT" in report
    assert "NOT COMMERCIAL EVIDENCE" in report
    assert "<script" not in report.casefold()
    assert "not_explicitly_supplied" in report
    assert "not_modeled_in_storefront_read_model" in report
    trigger_marker = report.index("methodology_triggers")
    for trigger in methodology["decision"]["triggers"]:
        assert report.index(trigger) > trigger_marker


def test_same_inputs_produce_byte_identical_outputs(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path, output_name="output-one")
    second = replace(
        prepared.value,
        output_dir=tmp_path / "output-two",
    )

    checkpoint.run_system_checkpoint(prepared.value)
    checkpoint.run_system_checkpoint(second)

    first_root = Path(prepared.value.output_dir)
    second_root = Path(second.output_dir)
    for filename in checkpoint.ARTIFACT_FILENAMES:
        assert (first_root / filename).read_bytes() == (
            second_root / filename
        ).read_bytes()


def test_shopify_strict_draft_is_parseable_escaped_and_lf_only() -> None:
    row = build_shopify_draft_row(
        product_id=PRODUCT_ID,
        expected_product_id=PRODUCT_ID,
        title="Cable <Organizer>",
        price_mxn="999.00",
        description='Safe & bounded "copy" <local>',
        category="office",
        handle="local-cable-001",
        tags=("operator-reviewed",),
    )

    rendered = serialize_shopify_draft_export(row)
    parsed = list(csv.DictReader(io.StringIO(rendered, newline="")))

    assert tuple(parsed[0]) == SHOPIFY_FIELDNAMES
    assert parsed[0]["Body (HTML)"] == (
        "Safe &amp; bounded &quot;copy&quot; &lt;local&gt;"
    )
    assert parsed[0]["Published"] == "FALSE"
    assert parsed[0]["Status"] == "draft"
    assert "\r" not in rendered
    for marker in SHOPIFY_DRAFT_SAFETY_TAGS:
        assert parsed[0]["Tags"].split(", ").count(marker) == 1


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    (
        ("product_id", "=CMD()"),
        ("title", "+SUM(1,1)"),
        ("description", "@danger"),
        ("category", "-2+3"),
        ("vendor", "\ufeff=hidden"),
    ),
)
def test_shopify_strict_draft_rejects_formula_cells(
    field: str,
    unsafe_value: str,
) -> None:
    kwargs: dict[str, object] = {
        "product_id": PRODUCT_ID,
        "expected_product_id": PRODUCT_ID,
        "title": "Cable Organizer",
        "price_mxn": "999.00",
        "description": "Bounded copy",
        "category": "office",
        "handle": "local-cable-001",
        "vendor": "TrendifyHub",
        "tags": (),
    }
    kwargs[field] = unsafe_value
    if field == "product_id":
        kwargs["expected_product_id"] = unsafe_value

    with pytest.raises(
        ShopifyDraftExportError,
        match="spreadsheet formula prefix",
    ):
        build_shopify_draft_row(**kwargs)


@pytest.mark.parametrize(
    "description",
    ("line\rbreak", "line\nbreak", "nul\x00byte"),
)
def test_shopify_strict_draft_rejects_control_characters(
    description: str,
) -> None:
    with pytest.raises(
        ShopifyDraftExportError,
        match="control characters",
    ):
        build_shopify_draft_row(
            product_id=PRODUCT_ID,
            expected_product_id=PRODUCT_ID,
            title="Cable Organizer",
            price_mxn="999.00",
            description=description,
            category="office",
            handle="local-cable-001",
        )


@pytest.mark.parametrize(
    "conflicting_tag",
    (
        "Published=False",
        "published=true",
        "published =true",
        "shopify_mode=live",
        "@formula-tag",
    ),
)
def test_shopify_strict_draft_rejects_marker_conflicts(
    conflicting_tag: str,
) -> None:
    with pytest.raises(ShopifyDraftExportError):
        build_shopify_draft_row(
            product_id=PRODUCT_ID,
            expected_product_id=PRODUCT_ID,
            title="Cable Organizer",
            price_mxn="999.00",
            description="Bounded copy",
            category="office",
            handle="local-cable-001",
            tags=(conflicting_tag,),
        )


def test_missing_catalog_file_fails_without_output(tmp_path: Path) -> None:
    prepared = _build_inputs(tmp_path)
    prepared.paths["catalog"].unlink()

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="CATALOG_FILE_NOT_FOUND",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_missing_product_id_fails_without_output(tmp_path: Path) -> None:
    prepared = _build_inputs(tmp_path)
    value = replace(prepared.value, product_id="")

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="PRODUCT_ID_REQUIRED",
    ):
        checkpoint.run_system_checkpoint(value)

    _assert_no_output(value)


def test_duplicate_matching_product_ids_fail_closed(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)
    prepared.paths["catalog"].write_text(
        _catalog_text(duplicate=True),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="PRODUCT_ID_AMBIGUOUS",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_invalid_decimal_input_fails_closed(tmp_path: Path) -> None:
    prepared = _build_inputs(tmp_path)
    financial = json.loads(
        prepared.paths["financial"].read_text(encoding="utf-8")
    )
    financial["estimated_cac"] = "NaN"
    _write_json(prepared.paths["financial"], financial)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="FINANCIAL_INPUT_INVALID",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_nonfinite_catalog_decimal_fails_with_controlled_error(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)
    prepared.paths["catalog"].write_text(
        _catalog_text().replace("250.00", "NaN", 1),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="CATALOG_INVALID",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_financial_rejection_stops_before_downstream_outputs(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)
    financial = json.loads(
        prepared.paths["financial"].read_text(encoding="utf-8")
    )
    financial["estimated_cac"] = "900.00"
    _write_json(prepared.paths["financial"], financial)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="FINANCIAL_DECISION_BLOCKED=REJECT",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


@pytest.mark.parametrize(
    ("field", "label"),
    (
        ("methodology_context_json", "METHODOLOGY_CONTEXT"),
        ("customer_copy_json", "CUSTOMER_COPY"),
        ("promotion_approval_json", "PROMOTION_APPROVAL"),
        ("copy_approval_json", "COPY_APPROVAL"),
    ),
)
def test_missing_required_operator_file_fails_closed(
    tmp_path: Path,
    field: str,
    label: str,
) -> None:
    prepared = _build_inputs(tmp_path)
    missing = Path(getattr(prepared.value, field))
    missing.unlink()

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match=f"{label}_FILE_NOT_FOUND",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_invalid_methodology_context_fails_closed(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)
    context = json.loads(
        prepared.paths["methodology"].read_text(encoding="utf-8")
    )
    context["product_id"] = "wrong-product"
    _write_json(prepared.paths["methodology"], context)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="METHODOLOGY_INVALID",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_high_risk_claim_is_blocked_by_methodology(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)
    context = json.loads(
        prepared.paths["methodology"].read_text(encoding="utf-8")
    )
    context["claim_risk"] = "high"
    _write_json(prepared.paths["methodology"], context)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="METHODOLOGY_BLOCKED",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


@pytest.mark.parametrize(
    ("unsafe_description", "blocked_category"),
    (
        ("Cura la diabetes.", "health_claims,medical"),
        ("Resultados garantizados siempre.", "guarantees"),
    ),
)
def test_low_risk_label_cannot_bypass_existing_compliance_authority(
    tmp_path: Path,
    unsafe_description: str,
    blocked_category: str,
) -> None:
    prepared = _build_inputs(tmp_path)
    context = json.loads(
        prepared.paths["methodology"].read_text(encoding="utf-8")
    )
    assert context["claim_risk"] == "low"
    context["candidate_output"] = unsafe_description
    _write_json(prepared.paths["methodology"], context)
    copy_value = json.loads(
        prepared.paths["customer_copy"].read_text(encoding="utf-8")
    )
    copy_value["description"] = unsafe_description
    _write_json(prepared.paths["customer_copy"], copy_value)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match=(
            "CUSTOMER_COPY_COMPLIANCE_BLOCKED="
            + blocked_category
        ),
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_invalid_unsafe_customer_copy_fails_closed(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)
    copy_value = json.loads(
        prepared.paths["customer_copy"].read_text(encoding="utf-8")
    )
    copy_value["description"] = "Unsafe https://example.invalid claim"
    _write_json(prepared.paths["customer_copy"], copy_value)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="CUSTOMER_COPY_INVALID",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


@pytest.mark.parametrize(
    ("field", "unsafe_value", "error"),
    (
        (
            "description",
            "Different but locally valid description.",
            "CUSTOMER_COPY_DESCRIPTION_NOT_BOUND_TO_METHODOLOGY",
        ),
        (
            "facts",
            ["Unbound product fact."],
            "CUSTOMER_COPY_FACTS_NOT_BOUND_TO_METHODOLOGY",
        ),
        (
            "proof",
            ["Unbound proof statement."],
            "CUSTOMER_COPY_PROOF_NOT_BOUND_TO_METHODOLOGY",
        ),
    ),
)
def test_copy_methodology_binding_v1_fails_closed(
    tmp_path: Path,
    field: str,
    unsafe_value: object,
    error: str,
) -> None:
    prepared = _build_inputs(tmp_path)
    copy_value = json.loads(
        prepared.paths["customer_copy"].read_text(encoding="utf-8")
    )
    copy_value[field] = unsafe_value
    _write_json(prepared.paths["customer_copy"], copy_value)

    with pytest.raises(checkpoint.SystemCheckpointError, match=error):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_promotion_approval_digest_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)
    approval = json.loads(
        prepared.paths["promotion_approval"].read_text(encoding="utf-8")
    )
    approval["candidate_sha256"] = "0" * 64
    _write_json(prepared.paths["promotion_approval"], approval)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="PROMOTION_APPROVAL_INVALID=.*mismatch",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_copy_approval_digest_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)
    approval = json.loads(
        prepared.paths["copy_approval"].read_text(encoding="utf-8")
    )
    approval["approved_copy_sha256"] = "0" * 64
    _write_json(prepared.paths["copy_approval"], approval)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="COPY_APPROVAL_INVALID=.*mismatch",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_custody_tamper_is_detected_before_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _build_inputs(tmp_path)
    real_promote = checkpoint.promote_local_product_to_canonical_fixture

    def tampered_promote(**kwargs: object) -> dict:
        promoted = real_promote(**kwargs)
        tampered = copy.deepcopy(promoted)
        tampered["product"]["name"] = "Tampered title"
        return tampered

    monkeypatch.setattr(
        checkpoint,
        "promote_local_product_to_canonical_fixture",
        tampered_promote,
    )

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="CANONICAL_PROMOTION_INVALID",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_custody_methodology_tamper_is_detected_before_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _build_inputs(tmp_path)
    real_promote = checkpoint.promote_local_product_to_canonical_fixture

    def tampered_promote(**kwargs: object) -> dict:
        promoted = real_promote(**kwargs)
        tampered = copy.deepcopy(promoted)
        tampered["decision"]["methodology"]["selected_rule_id"] = (
            "tampered-rule"
        )
        return tampered

    monkeypatch.setattr(
        checkpoint,
        "promote_local_product_to_canonical_fixture",
        tampered_promote,
    )

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="CANONICAL_PROMOTION_INVALID",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_custody_reason_codes_tamper_is_detected_before_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _build_inputs(tmp_path)
    real_promote = checkpoint.promote_local_product_to_canonical_fixture

    def tampered_promote(**kwargs: object) -> dict:
        promoted = real_promote(**kwargs)
        tampered = copy.deepcopy(promoted)
        tampered["decision"]["reason_codes"] = ["TAMPERED_REASON_CODE"]
        return tampered

    monkeypatch.setattr(
        checkpoint,
        "promote_local_product_to_canonical_fixture",
        tampered_promote,
    )

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="CANONICAL_PROMOTION_INVALID",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


def test_cli_missing_output_dir_argument_fails_before_execution(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)
    args = _cli_args(prepared.value)
    output_index = args.index("--output-dir")
    del args[output_index : output_index + 2]

    with pytest.raises(SystemExit) as exc_info:
        checkpoint.main(args)

    assert exc_info.value.code == 2
    _assert_no_output(prepared.value)


def test_optional_financial_path_omission_fails_as_missing_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared = _build_inputs(tmp_path)
    args = _cli_args(prepared.value)
    index = args.index("--financial-assumptions-json")
    del args[index : index + 2]

    rc = checkpoint.main(args)

    assert rc == 2
    assert (
        "FINANCIAL_ASSUMPTIONS_REQUIRED="
        "explicit_product_bound_estimated_cac"
        in capsys.readouterr().err
    )
    _assert_no_output(prepared.value)


def test_output_inside_repository_is_prohibited(tmp_path: Path) -> None:
    prepared = _build_inputs(tmp_path)
    value = replace(
        prepared.value,
        output_dir=REPO_ROOT / "artifacts" / "forbidden-checkpoint-output",
    )

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="OUTPUT_DIR_INSIDE_REPOSITORY_FORBIDDEN",
    ):
        checkpoint.run_system_checkpoint(value)


def test_unc_input_is_rejected_before_filesystem_probe(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)
    value = replace(
        prepared.value,
        catalog_csv=Path(r"\\server.invalid\share\catalog.csv"),
    )

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="CATALOG_REMOTE_PATH_FORBIDDEN",
    ):
        checkpoint.run_system_checkpoint(value)

    _assert_no_output(value)


def test_unc_output_is_rejected_before_filesystem_probe() -> None:
    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="OUTPUT_DIR_REMOTE_PATH_FORBIDDEN",
    ):
        checkpoint._prepare_output_dir(
            Path(r"\\server.invalid\share\checkpoint-output")
        )


def test_reparse_component_is_rejected_before_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReparseMetadata:
        st_mode = 0
        st_file_attributes = 0x400

    monkeypatch.setattr(
        checkpoint.os,
        "lstat",
        lambda _path: ReparseMetadata(),
    )

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="CATALOG_REPARSE_PATH_FORBIDDEN",
    ):
        checkpoint._explicit_file(
            Path("operator-link") / "catalog.csv",
            "CATALOG",
        )


def test_artifact_write_failure_cleans_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "atomic-output"
    artifacts = {
        filename: f"{filename}\n".encode("utf-8")
        for filename in checkpoint.ARTIFACT_FILENAMES
    }
    real_open = Path.open
    calls = 0

    def fail_second_temporary_open(
        self: Path,
        *args: object,
        **kwargs: object,
    ):
        nonlocal calls
        if self.parent.name.startswith(
            ".atomic-output.checkpoint-"
        ):
            calls += 1
            if calls == 2:
                raise OSError("injected write failure")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_second_temporary_open)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="OUTPUT_WRITE_FAILED",
    ):
        checkpoint._write_artifacts(output, artifacts)

    assert not output.exists()
    assert not list(tmp_path.glob(".atomic-output.checkpoint-*"))


@pytest.mark.parametrize(
    ("failure", "expected_exception"),
    (
        (OSError("injected fsync failure"), checkpoint.SystemCheckpointError),
        (KeyboardInterrupt(), KeyboardInterrupt),
    ),
)
def test_artifact_fsync_interruption_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
    expected_exception: type[BaseException],
) -> None:
    output = tmp_path / "atomic-fsync"
    artifacts = {
        filename: f"{filename}\n".encode("utf-8")
        for filename in checkpoint.ARTIFACT_FILENAMES
    }

    def fail_fsync(_fileno: int) -> None:
        raise failure

    monkeypatch.setattr(checkpoint.os, "fsync", fail_fsync)

    with pytest.raises(expected_exception):
        checkpoint._write_artifacts(output, artifacts)

    assert not output.exists()
    assert not list(tmp_path.glob(".atomic-fsync.checkpoint-*"))


def test_atomic_publish_does_not_delete_raced_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "atomic-race"
    artifacts = {
        filename: f"{filename}\n".encode("utf-8")
        for filename in checkpoint.ARTIFACT_FILENAMES
    }

    def inject_raced_destination(
        _staging: Path,
        target: Path,
    ) -> None:
        target.mkdir()
        raise FileExistsError("injected destination race")

    monkeypatch.setattr(Path, "rename", inject_raced_destination)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="OUTPUT_WRITE_FAILED",
    ):
        checkpoint._write_artifacts(output, artifacts)

    assert output.is_dir()
    assert list(output.iterdir()) == []
    assert not list(tmp_path.glob(".atomic-race.checkpoint-*"))


def test_input_mutation_is_detected_before_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _build_inputs(tmp_path)
    target = prepared.paths["customer_copy"].resolve()
    real_read_bytes = Path.read_bytes
    reads = 0

    def mutate_second_read(self: Path) -> bytes:
        nonlocal reads
        value = real_read_bytes(self)
        if self.resolve() == target:
            reads += 1
            if reads >= 2:
                return value + b" "
        return value

    monkeypatch.setattr(Path, "read_bytes", mutate_second_read)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="INPUT_CHANGED_DURING_RUN=customer_copy_json",
    ):
        checkpoint.run_system_checkpoint(prepared.value)

    _assert_no_output(prepared.value)


@pytest.mark.skipif(
    os.name != "nt",
    reason="The official checkpoint runtime uses the Windows file lock.",
)
def test_catalog_parser_cannot_mutate_or_swap_locked_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _build_inputs(tmp_path)
    original_bytes = prepared.paths["catalog"].read_bytes()
    real_select = checkpoint._select_catalog_fixture

    def attempt_swap(path: Path, product_id: str) -> dict:
        with pytest.raises(OSError):
            path.write_bytes(
                original_bytes.replace(b"250.00", b"251.00", 1)
            )
        return real_select(path, product_id)

    monkeypatch.setattr(
        checkpoint,
        "_select_catalog_fixture",
        attempt_swap,
    )

    result = checkpoint.run_system_checkpoint(prepared.value)

    assert result.status == "PASS"
    assert prepared.paths["catalog"].read_bytes() == original_bytes


def test_live_network_or_publish_flag_is_not_a_cli_surface(
    tmp_path: Path,
) -> None:
    prepared = _build_inputs(tmp_path)

    for flag in ("--live", "--network", "--publish"):
        with pytest.raises(SystemExit) as exc_info:
            checkpoint.main(_cli_args(prepared.value) + [flag])
        assert exc_info.value.code == 2

    _assert_no_output(prepared.value)


def test_shopify_writer_bomb_is_never_constructed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from synapse.shopify.shopify_writer import ShopifyWriter

    prepared = _build_inputs(tmp_path)

    def bomb(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ShopifyWriter must never be constructed")

    monkeypatch.setattr(ShopifyWriter, "__init__", bomb)

    result = checkpoint.run_system_checkpoint(prepared.value)

    assert result.status == "PASS"


def test_meta_dropi_and_urlopen_bombs_are_never_called(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.request

    from synapse.integrations.dropi.order_forwarder import (
        DropiOrderForwarder,
    )
    from synapse.meta.safe_client import MetaSafeClient

    prepared = _build_inputs(tmp_path)

    def bomb(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("external transport boundary was touched")

    monkeypatch.setattr(urllib.request, "urlopen", bomb)
    monkeypatch.setattr(DropiOrderForwarder, "__init__", bomb)
    monkeypatch.setattr(MetaSafeClient, "__init__", bomb)

    result = checkpoint.run_system_checkpoint(prepared.value)

    assert result.status == "PASS"


def test_hidden_fixture_fallback_is_forbidden(tmp_path: Path) -> None:
    prepared = _build_inputs(tmp_path)
    fixture_catalog = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "a8_r110_catalog"
        / "catalog_nominal.csv"
    )
    value = replace(prepared.value, catalog_csv=fixture_catalog)

    with pytest.raises(
        checkpoint.SystemCheckpointError,
        match="CATALOG_FIXTURE_PATH_FORBIDDEN",
    ):
        checkpoint.run_system_checkpoint(value)

    _assert_no_output(value)


def test_entrypoint_main_is_callable_and_cli_nominal_passes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared = _build_inputs(tmp_path)

    assert callable(checkpoint.main)
    rc = checkpoint.main(_cli_args(prepared.value))

    assert rc == 0
    stdout = capsys.readouterr().out
    assert "SYSTEM_CHECKPOINT_STATUS=PASS" in stdout
    assert "NETWORK_USED=false" in stdout
    assert "PUBLISHED=false" in stdout
