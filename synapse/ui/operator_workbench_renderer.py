"""A8-R109A deterministic offline HTML renderer for the Workbench ViewModel.

Scope (R109A, mechanical audit artifact only):
- Pure function ViewModel -> self-contained HTML string, openable via file://.
- No server, no Streamlit, no network clients, no external assets, no scripts.
- Minimal inline CSS for readability only; visual polish belongs to R109B.
- The only side effect lives in the CLI: writing the rendered HTML locally.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path
from typing import Any, Mapping, Sequence

from synapse.ui.operator_workbench_view_model import (
    INPUT_LOW,
    WorkbenchViewModel,
    build_view_model_from_path,
)

RENDERER_VERSION = "a8-r109a.workbench_renderer.v2"

SECTION_ORDER: tuple[str, ...] = (
    "provenance-seal",
    "module-status-summary",
    "candidate-pipeline",
    "action-queue",
    "product-decision",
    "input-richness",
    "economics-scores",
    "shopify-pack",
    "marketing-pack",
    "learning-plan",
    "blocked-queue-summary",
    "blocked-queue",
    "operator-actions",
    "system-health-board",
    "safety-boundary",
    "capability-surface-map",
    "evidence-notes",
    "copy-payload-registry",
)


def forbidden_output_tokens() -> tuple[str, ...]:
    """Network/client tokens that must never appear in rendered output.

    Assembled from halves so this module never contains the literal tokens.
    """
    halves = (
        ("fetch", "("),
        ("XMLHttp", "Request"),
        ("<script ", "src="),
        ("<link ", "rel="),
        ("http", "://"),
        ("https", "://"),
        ("<form ", "action="),
    )
    return tuple(left + right for left, right in halves)


def scan_forbidden_tokens(text: str) -> list[str]:
    return [token for token in forbidden_output_tokens() if token in text]


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _ul(items: Sequence[Any]) -> str:
    materialized = [str(item) for item in items if str(item).strip()]
    if not materialized:
        return '<p class="empty">(vacio)</p>'
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in materialized) + "</ul>"


def _kv_table(mapping: Mapping[str, Any]) -> str:
    if not mapping:
        return '<p class="empty">(vacio)</p>'
    rows = "".join(
        f"<tr><th>{_e(key)}</th><td>{_e(value)}</td></tr>" for key, value in mapping.items()
    )
    return f"<table>{rows}</table>"


def _pre(text: str) -> str:
    return f"<pre>{_e(text)}</pre>"


def _section(section_id: str, title: str, body: str, contract_key: str = "") -> str:
    stable_contract_key = contract_key or section_id.replace("-", "_")
    marker = f'<code class="contract-marker">{_e(stable_contract_key)}</code>'
    return (
        f'<section id="{_e(section_id)}" data-contract-section="{_e(stable_contract_key)}">'
        f"<h2>{_e(title)}</h2>\n{marker}\n{body}\n</section>"
    )

def _claim_guard_adjacent(claim_guard: Mapping[str, Any], surface: str) -> str:
    parts = [
        f'<div class="claim-guard-adjacent" data-adjacent-to="{_e(surface)}">',
        "<h3>Claim Guard (adyacente)</h3>",
        f"<p><strong>Resumen:</strong> {_e(claim_guard.get('summary', ''))}</p>",
        "<h4>Claims permitidos</h4>",
        _ul(claim_guard.get("allowed_claims") or []),
        "<h4>Claims riesgosos</h4>",
        _ul(claim_guard.get("risky_claims") or []),
        "<h4>Claims prohibidos</h4>",
        _ul(claim_guard.get("prohibited_claims") or []),
        "<h4>Redaccion segura</h4>",
        _ul(claim_guard.get("safe_wording") or []),
        "</div>",
    ]
    return "\n".join(parts)


def _actions_list(actions: Sequence[Mapping[str, Any]]) -> str:
    if not actions:
        return '<p class="empty">(sin acciones)</p>'
    rows = []
    for action in actions:
        rows.append(
            "<li>"
            f"<strong>{_e(action.get('label', ''))}</strong>"
            f" <code>kind={_e(action.get('kind', ''))}</code>"
            f" <code>target={_e(action.get('target', ''))}</code>"
            f"<br>{_e(action.get('notes', ''))}"
            "</li>"
        )
    return "<ul>" + "".join(rows) + "</ul>"


def _render_module_status_summary(data: Mapping[str, Any]) -> str:
    parts = []
    for entry in data.get("module_status_summary") or []:
        parts.append(
            f'<div class="module-status" data-module-id="{_e(entry.get("module_id", ""))}"'
            f' data-module-status="{_e(entry.get("status", ""))}">'
        )
        parts.append(f"<h3>{_e(entry.get('label', ''))}</h3>")
        parts.append(
            _kv_table(
                {
                    "module_id": entry.get("module_id", ""),
                    "status": entry.get("status", ""),
                    "badge_text": entry.get("badge_text", ""),
                    "summary": entry.get("summary", ""),
                    "operator_action": entry.get("operator_action", ""),
                    "source_fields": ", ".join(entry.get("source_fields") or []),
                    "is_real_now": entry.get("is_real_now", False),
                    "is_future_placeholder": entry.get("is_future_placeholder", False),
                }
            )
        )
        parts.append("</div>")
    return _section("module-status-summary", "Module Status Summary", "\n".join(parts))


def _render_candidate_pipeline(data: Mapping[str, Any]) -> str:
    pipeline = dict(data.get("candidate_pipeline") or {})
    source_fields = pipeline.pop("source_fields", [])
    body = (
        _kv_table(pipeline)
        + "<h4>Source fields</h4>"
        + _ul(source_fields)
        + '<p class="warning">Conteos solo del fixture congelado; discovery en vivo NO conectado.</p>'
    )
    return _section("candidate-pipeline", "Candidate Pipeline (fixture-only)", body)


def _render_action_queue(data: Mapping[str, Any]) -> str:
    queue = data.get("action_queue") or []
    if not queue:
        return _section("action-queue", "Action Queue", '<p class="empty">(sin acciones)</p>')
    rows = []
    for action in queue:
        primary = " [PRIMARIA]" if action.get("is_primary") else ""
        rows.append(
            "<li>"
            f"<strong>#{_e(action.get('priority', ''))} {_e(action.get('label', ''))}{primary}</strong>"
            f" <code>target_module={_e(action.get('target_module', ''))}</code>"
            f" <code>action_id={_e(action.get('action_id', ''))}</code>"
            f"<br>{_e(action.get('reason', ''))}"
            f"<br><small>source: {_e(', '.join(action.get('source_fields') or []))}</small>"
            "</li>"
        )
    return _section("action-queue", "Action Queue", "<ol>" + "".join(rows) + "</ol>")


def _render_blocked_queue_summary(data: Mapping[str, Any]) -> str:
    summary = data.get("blocked_queue_summary") or {}
    item_rows = [
        f"{item.get('product_name', '')} | severidad: {item.get('severity', '')} | "
        f"recuperable: {item.get('can_recover', False)} | {item.get('reason', '')}"
        for item in summary.get("blocked_items") or []
    ]
    body = (
        _kv_table(
            {
                "blocked_count": summary.get("blocked_count", 0),
                "can_prepare": summary.get("can_prepare", False),
                "source_fields": ", ".join(summary.get("source_fields") or []),
            }
        )
        + "<h4>Items bloqueados</h4>"
        + _ul(item_rows)
        + "<h4>Reason codes</h4>"
        + _ul(summary.get("reason_codes") or [])
        + "<h4>Acciones requeridas del operador</h4>"
        + _ul(summary.get("required_operator_actions") or [])
    )
    return _section("blocked-queue-summary", "Blocked Queue Summary", body)


def _render_system_health_board(data: Mapping[str, Any]) -> str:
    board = dict(data.get("system_health_board") or {})
    source_fields = board.pop("source_fields", [])
    body = _kv_table(board) + "<h4>Source fields</h4>" + _ul(source_fields)
    return _section("system-health-board", "System Health Board", body)


def _render_capability_surface_map(data: Mapping[str, Any]) -> str:
    surface = data.get("capability_surface_map") or {}
    parts = []
    for title, key in (
        ("Real hoy", "real_now"),
        ("Solo fixture", "fixture_only"),
        ("Futuro / no conectado", "future_or_not_connected"),
        ("Prohibido reclamar", "forbidden_to_claim"),
    ):
        parts.append(f'<h4 data-capability-tier="{_e(key)}">{_e(title)}</h4>')
        parts.append(_ul(surface.get(key) or []))
    return _section("capability-surface-map", "Capability Surface Map", "\n".join(parts))


def _render_provenance(data: Mapping[str, Any]) -> str:
    provenance = data["provenance"]
    body = (
        '<div class="provenance-seal">'
        "<p><strong>SELLO DE PROVENANCE — SYNAPSE Fase 1 (solo lectura, sin red, sin reloj)</strong></p>"
        + _kv_table(provenance)
        + "</div>"
    )
    return _section("provenance-seal", "Provenance Seal", body)


def _render_product_decision(data: Mapping[str, Any]) -> str:
    product = data.get("product") or {}
    decision = data.get("decision") or {}
    if product:
        product_block = _kv_table(product)
    else:
        product_block = '<p class="empty">Sin producto: la shortlist esta vacia.</p>'
    body = (
        "<h3>Producto</h3>"
        + product_block
        + "<h3>Decision</h3>"
        + _kv_table(
            {
                "outcome": decision.get("outcome", ""),
                "permission_gate": decision.get("permission_gate", ""),
                "reason": decision.get("reason", ""),
            }
        )
        + "<h4>Reason codes</h4>"
        + _ul(decision.get("reason_codes") or [])
        + "<h4>Caveats</h4>"
        + _ul(decision.get("caveats") or [])
    )
    return _section("product-decision", "Product / Decision", body)


def _render_input_richness(data: Mapping[str, Any]) -> str:
    richness = data["input_richness"]
    parts = [
        _kv_table(
            {
                "classification": richness.get("classification", ""),
                "policy": richness.get("policy", ""),
                "filled_count": richness.get("filled_count", 0),
                "total_fields": richness.get("total_fields", 0),
            }
        ),
        "<h4>Campos llenos</h4>",
        _ul(richness.get("filled_fields") or []),
        "<h4>Campos faltantes</h4>",
        _ul(richness.get("missing_fields") or []),
    ]
    if richness.get("classification") == INPUT_LOW and richness.get("warning"):
        parts.insert(0, f'<p class="warning">{_e(richness["warning"])}</p>')
    return _section("input-richness", "Input Richness", "\n".join(parts))


def _render_economics_scores(data: Mapping[str, Any]) -> str:
    body = (
        "<h3>Economia</h3>"
        + _kv_table(data.get("economics") or {})
        + "<h3>Scores</h3>"
        + _kv_table(data.get("scores") or {})
    )
    return _section("economics-scores", "Economics / Scores", body)


def _render_shopify_pack(data: Mapping[str, Any]) -> str:
    pack = data["shopify_pack"]
    if not pack.get("enabled"):
        body = (
            f'<p class="disabled">Shopify pack deshabilitado: '
            f"{_e(pack.get('disabled_reason', ''))}</p>"
            + _claim_guard_adjacent(pack.get("claim_guard_notes") or {}, "shopify_pack")
        )
        return _section("shopify-pack", "Shopify Pack", body)

    scalar_keys = (
        "title",
        "subtitle",
        "short_description",
        "long_description",
        "seo_title",
        "seo_meta_description",
        "handle",
        "category",
        "price",
        "compare_at_price",
        "shipping_note",
        "refund_claim_note",
        "claim_safe_disclaimer",
    )
    spec_rows = {item["name"]: item["value"] for item in pack.get("specifications") or []}
    faq_rows = [f"P: {item['q']} / R: {item['a']}" for item in pack.get("faq") or []]
    body = (
        _kv_table({key: pack.get(key, "") for key in scalar_keys})
        + "<h4>Tags</h4>"
        + _ul(pack.get("tags") or [])
        + "<h4>Bullets</h4>"
        + _ul(pack.get("bullets") or [])
        + "<h4>Beneficios</h4>"
        + _ul(pack.get("benefits") or [])
        + "<h4>Especificaciones</h4>"
        + _kv_table(spec_rows)
        + "<h4>FAQ</h4>"
        + _ul(faq_rows)
        + "<h4>Checklist de imagenes</h4>"
        + _ul(pack.get("image_checklist") or [])
        + "<h4>Checklist de publicacion</h4>"
        + _ul(pack.get("publish_checklist") or [])
        + "<h4>Inputs faltantes</h4>"
        + _ul(pack.get("missing_inputs") or [])
        + _claim_guard_adjacent(pack.get("claim_guard_notes") or {}, "shopify_pack")
    )
    return _section("shopify-pack", "Shopify Pack", body)


def _render_marketing_pack(data: Mapping[str, Any]) -> str:
    pack = data["marketing_pack"]
    if not pack.get("enabled"):
        body = (
            f'<p class="disabled">Marketing pack deshabilitado: '
            f"{_e(pack.get('disabled_reason', ''))}</p>"
            + _claim_guard_adjacent(pack.get("claim_guard") or {}, "marketing_pack")
        )
        return _section("marketing-pack", "Marketing Pack", body)

    parts = []
    if pack.get("input_richness_warning"):
        parts.append(f'<p class="warning">{_e(pack["input_richness_warning"])}</p>')
    parts.append(
        _kv_table(
            {
                "strategy_summary": pack.get("strategy_summary", ""),
                "core_angle": pack.get("core_angle", ""),
                "why_this_angle": pack.get("why_this_angle", ""),
                "buyer_profile": pack.get("buyer_profile", ""),
            }
        )
    )
    for title, key in (
        ("Audiencias", "audience"),
        ("Dolores", "pain_points"),
        ("Deseos", "desire"),
        ("Objeciones", "objections"),
        ("Hooks", "hooks"),
        ("Headlines", "headlines"),
        ("Textos primarios", "primary_texts"),
        ("Anuncios cortos", "short_ads"),
        ("Anuncios largos", "long_ads"),
        ("Captions", "captions"),
        ("Guiones UGC", "ugc_scripts"),
        ("Guiones de video", "video_scripts"),
        ("Conceptos de imagen", "image_ad_concepts"),
    ):
        parts.append(f"<h4>{_e(title)}</h4>")
        parts.append(_ul(pack.get(key) or []))
    channel_rows = [
        f"{item.get('channel', '')} | {item.get('objective', '')} | {item.get('notes', '')}"
        for item in pack.get("channel_packs") or []
    ]
    parts.append("<h4>Channel packs</h4>")
    parts.append(_ul(channel_rows))
    parts.append("<h4>Plan de pruebas</h4>")
    parts.append(_kv_table(pack.get("testing_plan") or {}))

    parts.append('<h3 id="angle-matrix">Matriz de angulos</h3>')
    angles = pack.get("angle_matrix") or []
    if not angles:
        parts.append('<p class="empty">(sin angulos definidos)</p>')
    for angle in angles:
        parts.append('<div class="angle-item">')
        parts.append(f"<h4>[{_e(angle.get('angle_id', ''))}] {_e(angle.get('angle_name', ''))}</h4>")
        parts.append(_kv_table({key: angle.get(key, "") for key in angle if key not in ("angle_id", "angle_name")}))
        parts.append("</div>")

    parts.append('<h3 id="creative-hypotheses">Hipotesis creativas</h3>')
    hypotheses = pack.get("creative_hypotheses") or []
    if not hypotheses:
        parts.append('<p class="empty">(sin hipotesis definidas)</p>')
    for hypothesis in hypotheses:
        parts.append('<div class="hypothesis-item">')
        parts.append(
            f"<h4>[{_e(hypothesis.get('hypothesis_id', ''))}] {_e(hypothesis.get('hypothesis', ''))}</h4>"
        )
        parts.append(
            _kv_table(
                {key: hypothesis.get(key, "") for key in hypothesis if key not in ("hypothesis_id", "hypothesis")}
            )
        )
        parts.append("</div>")

    parts.append('<h3 id="claim-risk-by-copy">Riesgo de claims por copy</h3>')
    risk_entries = pack.get("claim_risk_by_copy") or []
    if not risk_entries:
        parts.append('<p class="empty">(sin analisis de riesgo por copy)</p>')
    for entry in risk_entries:
        parts.append('<div class="copy-risk-item">')
        parts.append(
            _kv_table(
                {
                    "copy_key": entry.get("copy_key", ""),
                    "risk_level": entry.get("risk_level", ""),
                    "risky_terms": ", ".join(entry.get("risky_terms") or []) or "(ninguno)",
                    "prohibited_terms": ", ".join(entry.get("prohibited_terms") or []) or "(ninguno)",
                    "safe_rewrite": entry.get("safe_rewrite", ""),
                    "reason": entry.get("reason", ""),
                }
            )
        )
        parts.append("</div>")

    parts.append('<h3 id="input-support-map">Mapa de soporte de inputs</h3>')
    support_rows = [
        f"{entry.get('output_key', '')} <- "
        + (", ".join(entry.get("support_fields") or []) or "(sin soporte)")
        + (" [soportado]" if entry.get("supported") else " [NO SOPORTADO: fallback generico]")
        + (f" {entry.get('notes', '')}" if entry.get("notes") else "")
        for entry in pack.get("input_support_map") or []
    ]
    parts.append(_ul(support_rows))

    parts.append('<h3 id="missing-marketing-inputs">Inputs de marketing faltantes</h3>')
    parts.append(_ul(pack.get("missing_marketing_inputs") or []))

    parts.append('<h3 id="confidence-by-section">Confianza por seccion</h3>')
    confidence_rows = {
        section: f"{entry.get('level', '')} ({entry.get('basis', '')})"
        for section, entry in (pack.get("confidence_by_section") or {}).items()
    }
    parts.append(_kv_table(confidence_rows))

    parts.append('<h3 id="testing-plan-thresholds">Plan de pruebas con umbrales</h3>')
    plan = pack.get("testing_plan_with_thresholds") or {}
    parts.append(
        _kv_table(
            {
                "first_test_budget_boundary_dry_run_only": plan.get(
                    "first_test_budget_boundary_dry_run_only", ""
                ),
                "no_pmf_claim": plan.get("no_pmf_claim", ""),
                "no_analytics_fetch": plan.get("no_analytics_fetch", ""),
            }
        )
    )
    for title, key in (
        ("Senales de exito", "success_signals"),
        ("Senales de advertencia", "warning_signals"),
        ("Senales de alto", "stop_signals"),
        ("Continuar si", "continue_if"),
        ("Revisar si", "review_if"),
        ("Matar si", "kill_if"),
        ("No concluir", "what_not_to_conclude"),
    ):
        parts.append(f"<h4>{_e(title)}</h4>")
        parts.append(_ul(plan.get(key) or []))

    parts.append("<h4>Confianza (global v1)</h4>")
    parts.append(_kv_table(pack.get("confidence") or {}))
    parts.append(_claim_guard_adjacent(pack.get("claim_guard") or {}, "marketing_pack"))
    return _section("marketing-pack", "Marketing Pack", "\n".join(parts))


def _render_learning_plan(data: Mapping[str, Any]) -> str:
    plan = data["learning_plan"]
    parts = []
    for title, key in (
        ("Hipotesis", "hypotheses"),
        ("Evidencia necesaria", "evidence_needed"),
        ("Senales de primera venta", "first_sale_signals"),
        ("Senales de riesgo", "risk_signals"),
        ("Continuar si", "continue_if"),
        ("Revisar si", "review_if"),
        ("Matar si", "kill_if"),
    ):
        parts.append(f"<h4>{_e(title)}</h4>")
        parts.append(_ul(plan.get(key) or []))
    parts.append("<h4>Esquema de observaciones del operador</h4>")
    parts.append(_ul((plan.get("operator_observations_schema") or {}).get("fields") or []))
    parts.append(
        _kv_table(
            {
                "no_pmf_claim": plan.get("no_pmf_claim"),
                "no_analytics_fetch": plan.get("no_analytics_fetch"),
                "operator_in_control": plan.get("operator_in_control"),
            }
        )
    )
    return _section("learning-plan", "Learning Plan", "\n".join(parts))


def _render_blocked_queue(data: Mapping[str, Any]) -> str:
    queue = data.get("blocked_queue") or []
    if not queue:
        body = '<p class="empty">Cola de bloqueados vacia.</p>'
        return _section("blocked-queue", "Blocked Queue", body)
    parts = []
    for item in queue:
        parts.append('<div class="blocked-item">')
        parts.append(f"<h3>{_e(item.get('product_name', ''))}</h3>")
        parts.append(
            _kv_table(
                {
                    "reason": item.get("reason", ""),
                    "severity": item.get("severity", ""),
                    "can_recover": item.get("can_recover", False),
                }
            )
        )
        parts.append("<h4>Reason codes</h4>")
        parts.append(_ul(item.get("reason_codes") or []))
        parts.append("<h4>Acciones del operador</h4>")
        parts.append(_actions_list(item.get("operator_actions") or []))
        parts.append("<h4>Safety boundary del item</h4>")
        parts.append(_kv_table(item.get("safety_boundary") or {}))
        parts.append("</div>")
    return _section("blocked-queue", "Blocked Queue", "\n".join(parts))


def _render_operator_actions(data: Mapping[str, Any]) -> str:
    return _section(
        "operator-actions",
        "Operator Actions",
        _actions_list(data.get("operator_actions") or []),
    )


def _render_safety_boundary(data: Mapping[str, Any]) -> str:
    return _section("safety-boundary", "Safety Boundary", _kv_table(data["safety_boundary"]))


def _render_evidence(data: Mapping[str, Any]) -> str:
    evidence = data.get("evidence") or {}
    body = (
        "<h4>Notas</h4>"
        + _ul(evidence.get("notes") or [])
        + "<h4>Artefactos</h4>"
        + _ul(evidence.get("artifacts") or [])
    )
    return _section("evidence-notes", "Evidence Notes", body)


def _render_copy_payloads(data: Mapping[str, Any]) -> str:
    payloads = data["copy_payloads"]
    if not payloads.get("enabled"):
        body = (
            f'<p class="disabled">Copy payloads deshabilitados: '
            f"{_e(payloads.get('disabled_reason', ''))}</p>"
        )
        return _section("copy-payload-registry", "Copy Payload Registry", body)
    parts = [f"<p>Payloads canonicos: {_e(payloads.get('count', 0))}</p>"]
    for item in payloads.get("items") or []:
        parts.append(f'<div class="copy-payload" data-payload-key="{_e(item["key"])}">')
        parts.append(
            f"<h3>{_e(item.get('label', ''))} <code>{_e(item.get('key', ''))}</code></h3>"
        )
        parts.append(
            _kv_table(
                {
                    "section": item.get("section", ""),
                    "claim_guard_ref": item.get("claim_guard_ref", ""),
                    "source_fields": ", ".join(item.get("source_fields") or []),
                }
            )
        )
        parts.append(_pre(item.get("text", "")))
        parts.append("</div>")
    return _section("copy-payload-registry", "Copy Payload Registry", "\n".join(parts))


_INLINE_CSS = """
body { font-family: "Segoe UI", Arial, sans-serif; margin: 24px; color: #1c1c1c; }
header { border: 2px solid #1c1c1c; padding: 12px; margin-bottom: 16px; }
section { border: 1px solid #b5b5b5; padding: 12px; margin-bottom: 16px; }
h2 { margin-top: 0; }
table { border-collapse: collapse; margin: 8px 0; }
th, td { border: 1px solid #b5b5b5; padding: 4px 8px; text-align: left; vertical-align: top; }
pre { background: #f4f4f4; border: 1px solid #b5b5b5; padding: 8px; white-space: pre-wrap; }
.warning { background: #fff3cd; border: 1px solid #a07800; padding: 8px; font-weight: bold; }
.disabled { background: #eeeeee; border: 1px dashed #777777; padding: 8px; }
.empty { color: #555555; }
.claim-guard-adjacent { border: 1px dashed #7a3030; padding: 8px; margin-top: 12px; }
.provenance-seal { border: 2px double #1c1c1c; padding: 8px; }
.blocked-item, .copy-payload, .module-status { border-bottom: 1px solid #d0d0d0; padding: 8px 0; }
""".strip()


def render_workbench_html(view_model: WorkbenchViewModel) -> str:
    """Render the ViewModel to a deterministic, self-contained HTML string."""
    data = view_model.to_dict()

    sections = "\n".join(
        (
            _render_provenance(data),
            _render_module_status_summary(data),
            _render_candidate_pipeline(data),
            _render_action_queue(data),
            _render_product_decision(data),
            _render_input_richness(data),
            _render_economics_scores(data),
            _render_shopify_pack(data),
            _render_marketing_pack(data),
            _render_learning_plan(data),
            _render_blocked_queue_summary(data),
            _render_blocked_queue(data),
            _render_operator_actions(data),
            _render_system_health_board(data),
            _render_safety_boundary(data),
            _render_capability_surface_map(data),
            _render_evidence(data),
            _render_copy_payloads(data),
        )
    )

    document = "\n".join(
        (
            "<!DOCTYPE html>",
            '<html lang="es">',
            "<head>",
            '<meta charset="utf-8">',
            f"<title>SYNAPSE Operator Workbench (R109A audit render) — {_e(data['fixture_id'])}</title>",
            f"<style>{_INLINE_CSS}</style>",
            "</head>",
            "<body>",
            "<header>",
            "<h1>SYNAPSE Operator Workbench — R109A data/render audit</h1>",
            f"<p><strong>Fixture:</strong> <code>{_e(data['fixture_id'])}</code>"
            f" | <strong>Schema:</strong> <code>{_e(data['schema_version'])}</code>"
            f" | <strong>Renderer:</strong> <code>{RENDERER_VERSION}</code></p>",
            "<p>NO LIVE · NO SPEND · NO WRITES · OFFLINE FILE RENDER</p>",
            "</header>",
            sections,
            "</body>",
            "</html>",
            "",
        )
    )

    found = scan_forbidden_tokens(document)
    if found:
        raise ValueError(f"Forbidden tokens in rendered output: {found}")
    return document


def render_fixture_to_file(fixture_path: str | Path, output_path: str | Path) -> Path:
    view_model = build_view_model_from_path(fixture_path)
    document = render_workbench_html(view_model)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(document)
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m synapse.ui.operator_workbench_renderer",
        description="Deterministic offline HTML render of A8-R109A workbench fixtures.",
    )
    parser.add_argument("--fixture", help="Path to one fixture JSON.")
    parser.add_argument("--output", help="Output HTML path for --fixture.")
    parser.add_argument("--fixture-dir", help="Directory with fixture JSON files.")
    parser.add_argument("--output-dir", help="Output directory for --fixture-dir.")
    args = parser.parse_args(argv)

    if args.fixture and args.output:
        target = render_fixture_to_file(args.fixture, args.output)
        print(f"rendered={target.as_posix()}")
        return 0

    if args.fixture_dir and args.output_dir:
        fixture_dir = Path(args.fixture_dir)
        output_dir = Path(args.output_dir)
        fixture_paths = sorted(fixture_dir.glob("*.json"))
        if not fixture_paths:
            parser.error(f"No fixture JSON files found in: {fixture_dir}")
        for fixture_path in fixture_paths:
            target = render_fixture_to_file(fixture_path, output_dir / f"{fixture_path.stem}.html")
            print(f"rendered={target.as_posix()}")
        return 0

    parser.error("Use --fixture with --output, or --fixture-dir with --output-dir.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
