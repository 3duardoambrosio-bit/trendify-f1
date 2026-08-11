from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

from synapse.ui.operator_enrichment_cli import create_template, rebuild_workspace
from synapse.ui.operator_workbench_view_model import build_view_model
from synapse.ui.operator_workbench_visual import render_visual_html


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "a8_r115"

NOMINAL_ID = "a8_r110_r114_nominal"
ADVERSARIAL_ID = "a8_r110_r114_adversarial"
PRE_R115_COPY_PAYLOADS_SHA256 = (
    "0A256FE54DC4BDF398DA7BAD7B67C9CBBD7E8D6206C5BD944FCED2A1D9C74679"
)


def _write_catalog(path: Path) -> Path:
    path.write_text(
        "\n".join(
            (
                "product_id,title,supplier,category,supplier_price_mxn,"
                "shipping_cost_mxn,sale_price_mxn,payment_fee_mxn,source_url,notes",
                "r114-nominal,Producto Nominal,Proveedor MX,hogar_y_oficina,"
                "100,50,299,10,,caso nominal",
                "r114-adversarial,Producto Adversarial,Proveedor MX,salud,"
                "250,80,299,20,,caso adversarial",
            )
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _enrichment_payload(fixture_id: str, *, blocked: bool) -> dict[str, Any]:
    return {
        "schema_version": "a8-r111.operator_enrichment.v1",
        "fixture_id": fixture_id,
        "buyer_pain": "El desorden dificulta usar el espacio.",
        "buyer_state": "problem-aware",
        "target_audience": "Personas que buscan organizar su espacio.",
        "objections": ["Duda sobre el tamaño real del producto."],
        "proof_available": (
            ["Registro CSV local; no clinical proof"]
            if blocked
            else ["Registro CSV local del operador con identidad y costos completos"]
        ),
        "product_facts": (
            ["Producto declarado por el operador para organización personal."]
            if blocked
            else [
                "Identidad declarada por el operador: Producto Nominal",
                "Proveedor declarado por el operador: Proveedor MX",
            ]
        ),
        "claim_risk_hints": "medical" if blocked else "low",
        "channel": "Meta",
        "margin_profile": "tight" if blocked else "acceptable",
        "desires": ["Mantener el espacio ordenado."],
        "differentiators": ["Formato compacto declarado por el operador."],
        "market_context": "Uso doméstico y oficina local en México.",
        "customer_language": ["Quiero dejar de ver desorden."],
        "notes": "Preparación local; revisar antes de usar.",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _build_r114_cases(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    csv_path = _write_catalog(tmp_path / "catalogo.csv")
    workspace = tmp_path / "workspace"
    rebuild_workspace(csv_path, workspace)

    for fixture_id, blocked in (
        (NOMINAL_ID, False),
        (ADVERSARIAL_ID, True),
    ):
        template = create_template(workspace, fixture_id)
        _write_json(template, _enrichment_payload(fixture_id, blocked=blocked))

    rebuild_workspace(csv_path, workspace)

    def load(fixture_id: str) -> dict[str, Any]:
        return json.loads(
            (workspace / "candidates" / f"{fixture_id}.json").read_text(
                encoding="utf-8"
            )
        )

    return load(NOMINAL_ID), load(ADVERSARIAL_ID)


def _view_model(fixture: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    model = build_view_model(
        fixture,
        source_fixture=f"catalogo.csv#{fixture['fixture_id']}",
    )
    return model, model.to_dict()


def _state_vector(fixture: dict[str, Any]) -> dict[str, Any]:
    _model, data = _view_model(fixture)
    decision = fixture["decision"]
    economics = fixture["economics"]
    return {
        "state": fixture["enrichment"]["status"],
        "decision_outcome": decision["outcome"],
        "methodology_status": decision["methodology"]["status"],
        "contribution_margin_mxn": economics["contribution_margin_mxn"],
        "contribution_margin_percent": economics["contribution_margin_percent"],
        "permission_gate": decision["permission_gate"],
        "shopify_pack_enabled": data["shopify_pack"]["enabled"],
        "marketing_pack_enabled": data["marketing_pack"]["enabled"],
        "shopify_disabled_reason": data["shopify_pack"]["disabled_reason"],
        "marketing_disabled_reason": data["marketing_pack"]["disabled_reason"],
        "blocked_count": data["blocked_queue_summary"]["blocked_count"],
        "can_prepare": data["blocked_queue_summary"]["can_prepare"],
    }


def _canonical_bytes(value: Any, *, indent: int | None = None) -> bytes:
    separators = None if indent is not None else (",", ":")
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=indent,
            separators=separators,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def test_r114_complete_routing_state_vector_is_immutable(tmp_path: Path) -> None:
    nominal, adversarial = _build_r114_cases(tmp_path)

    assert _state_vector(nominal) == {
        "state": "ACCEPTED",
        "decision_outcome": "EVALUATING",
        "methodology_status": "accepted",
        "contribution_margin_mxn": 139,
        "contribution_margin_percent": 46.5,
        "permission_gate": "REVIEW",
        "shopify_pack_enabled": True,
        "marketing_pack_enabled": True,
        "shopify_disabled_reason": "",
        "marketing_disabled_reason": "",
        "blocked_count": 0,
        "can_prepare": False,
    }
    assert _state_vector(adversarial) == {
        "state": "BLOCKED",
        "decision_outcome": "BLOCKED",
        "methodology_status": "blocked",
        "contribution_margin_mxn": -51,
        "contribution_margin_percent": -17.1,
        "permission_gate": "REVIEW",
        "shopify_pack_enabled": False,
        "marketing_pack_enabled": False,
        "shopify_disabled_reason": "no_recommended_product_in_shortlist",
        "marketing_disabled_reason": "no_recommended_product_in_shortlist",
        "blocked_count": 1,
        "can_prepare": False,
    }


def test_sealed_methodology_bytes_match_pre_r115_goldens(tmp_path: Path) -> None:
    nominal, adversarial = _build_r114_cases(tmp_path)

    for fixture, golden_name in (
        (nominal, "nominal_methodology.json"),
        (adversarial, "adversarial_methodology.json"),
    ):
        before = _canonical_bytes(fixture["decision"]["methodology"], indent=2)
        assert before == (FIXTURE_ROOT / golden_name).read_bytes()

        model, data = _view_model(fixture)
        render_visual_html(model)
        after = _canonical_bytes(data["decision"]["methodology"], indent=2)
        assert after == before


def test_copy_payloads_keep_pre_r115_bytes_and_render_exactly(tmp_path: Path) -> None:
    nominal, _adversarial = _build_r114_cases(tmp_path)
    model, data = _view_model(nominal)
    before = _canonical_bytes(data["copy_payloads"])

    assert hashlib.sha256(before).hexdigest().upper() == PRE_R115_COPY_PAYLOADS_SHA256

    document = render_visual_html(model)
    after = _canonical_bytes(model.to_dict()["copy_payloads"])
    assert after == before

    copy_items = [
        item
        for item in data["copy_payloads"]["items"]
        if item["section"] in {"shopify_pack", "marketing_pack"}
    ]
    assert copy_items
    for item in copy_items:
        match = re.search(
            rf'<pre class="cb-body" id="payload_{re.escape(item["key"])}"[^>]*>'
            r"(.*?)</pre>",
            document,
            flags=re.DOTALL,
        )
        assert match is not None
        assert html.unescape(match.group(1)) == item["text"]


def test_negative_margin_orientation_is_quantified_and_economic_first(
    tmp_path: Path,
) -> None:
    _nominal, adversarial = _build_r114_cases(tmp_path)
    model, data = _view_model(adversarial)
    document = render_visual_html(model)

    guidance = data["operator_decision_guidance"]
    assert guidance["cpa_status"] == "NO_VIABLE_CPA"
    assert "Ningún CPA es viable, ni siquiera MXN 0.00" in document
    assert "tope de adquisicion por unidad" not in document
    assert "Punto de equilibrio contable, no precio viable" in document
    assert "MXN 350.01" in document
    assert "MXN 298.99" in document
    assert "MXN 466.67" in document
    assert "MXN 224.25" in document

    primary = next(item for item in data["action_queue"] if item["is_primary"])
    assert primary["target_module"] == "economics"
    assert primary["priority"] == 1
    assert "Reparar la economía" in primary["label"]
    assert primary["label"] in document

    assert "CALIDAD DEL BRIEF 8/10" in document
    assert "no mide viabilidad comercial" in document


def test_active_blockers_are_separate_from_informational_context(
    tmp_path: Path,
) -> None:
    _nominal, adversarial = _build_r114_cases(tmp_path)
    model, data = _view_model(adversarial)
    document = render_visual_html(model)
    guidance = data["operator_decision_guidance"]

    assert guidance["active_blockers"]
    assert guidance["informational_context"]
    assert "METHODOLOGY_BLOCKED" in guidance["active_blocker_codes"]
    assert "CATALOG_INTAKE" in guidance["informational_codes"]
    assert "NO_OPERATOR_BRIEF" in guidance["informational_codes"]
    assert 'data-orientation-group="active_blockers"' in document
    assert 'data-orientation-group="informational_context"' in document


def test_operator_orientation_is_spanish_without_touching_copy_payloads(
    tmp_path: Path,
) -> None:
    nominal, adversarial = _build_r114_cases(tmp_path)
    nominal_model, _nominal_data = _view_model(nominal)
    adversarial_model, _adversarial_data = _view_model(adversarial)
    nominal_html = render_visual_html(nominal_model)
    adversarial_html = render_visual_html(adversarial_model)

    methodology_start = nominal_html.index('<div class="card methodology-decision"')
    methodology_end = nominal_html.index(
        "<!-- methodology-decision:end -->", methodology_start
    )
    methodology_panel = nominal_html[methodology_start:methodology_end]
    assert "Resumen metodológico para el operador" in methodology_panel
    assert "safe_output" not in methodology_panel
    assert "selected_rule_id" not in methodology_panel
    assert "Hook: show" not in methodology_panel

    assert (
        "<th>promise_type</th><td>sealed_methodology_output</td>"
        not in nominal_html
    )
    for internal_or_english in (
        "Operator action:",
        "Primary reason:",
        "safe_output",
        "selected_rule_id",
        "<th>can_recover</th>",
        "<th>permission_gate</th>",
    ):
        assert internal_or_english not in adversarial_html

    assert "compare-at MXN None" not in nominal_html
    assert "compare-at MXN None" not in adversarial_html


def test_empty_decision_criteria_gain_operator_fallbacks_only(tmp_path: Path) -> None:
    nominal, adversarial = _build_r114_cases(tmp_path)

    for fixture in (nominal, adversarial):
        model, data = _view_model(fixture)
        document = render_visual_html(model)
        criteria = data["operator_decision_guidance"]["decision_criteria"]

        assert criteria["continue_if"]
        assert criteria["review_if"]
        assert criteria["kill_if"]
        assert criteria["source"] == "operator_orientation_fallback"
        for key in ("continue_if", "review_if", "kill_if"):
            assert all(item in document for item in criteria[key])

        raw_plan = data["marketing_pack"]["testing_plan_with_thresholds"]
        if fixture["enrichment"]["status"] == "ACCEPTED":
            assert raw_plan["continue_if"] == []
            assert raw_plan["review_if"] == []
            assert raw_plan["kill_if"] == []


def test_operator_runbook_separates_brief_quality_from_viability() -> None:
    runbook = (
        ROOT / "docs" / "operator" / "PHASE1_OPERATOR_RUNBOOK.md"
    ).read_text(encoding="utf-8")

    assert "brief completeness, not commercial viability" in runbook
    assert "sparse or\ngeneric context produces generic output" in runbook
    assert "evaluate unit economics separately" in runbook
