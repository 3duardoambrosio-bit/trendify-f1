"""A8-R109B-I1B functional operator workspace renderer (operator_workbench_visual).

Scope (R109B visual flow layer over the R109A/R109A.1 contract, R4 functional
operator workspace on top of the R3 premium shell):
- Pure function ViewModel -> self-contained OS-style HTML, openable via file://.
- Consumes the real contract surfaces (module_status_summary, candidate_pipeline,
  blocked_queue_summary, action_queue, system_health_board, capability_surface_map)
  instead of inferring state in the renderer.
- Functional workspace: candidate selector/switcher (single- and multi-fixture
  workspace mode), editable local operator drafts (localStorage only; never
  mutate the fixture or ViewModel, never claim engine recomputation), local
  checklist/notes persistence, copy/export selling packets built
  deterministically from contract fields, an actionable Marketing Engine
  (risk-adjusted first angle, copy priority order, manual test plan), and a
  Shopify listing prep editor with preview.
- Premium OS shell retained: obsidian/graphite surfaces, champagne-gold money
  accents, steel-blue audit accents, session gate (local-only, explicitly NOT
  real authentication), cockpit money metrics, executive brief, brain map,
  evidence black box.
- Inline CSS + inline vanilla JS only. No network, no external assets, no
  forms, no live writes, no spend, no credentials, no analytics, no fake
  performance data.
- The only side effect lives in the CLI: writing the rendered HTML locally.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path
from typing import Any, Mapping, Sequence

from synapse.ui.operator_workbench_renderer import scan_forbidden_tokens
from synapse.ui.operator_workbench_view_model import (
    WorkbenchViewModel,
    build_view_model_from_path,
)

VISUAL_VERSION = "a8-r109b.operator_workbench_visual.v4-console"

# Local Fase 1 guardrails/assumptions for the Money Cockpit. These are
# operator-facing heuristics computed from fixture numbers, never engine
# output; they are declared in the assumptions ledger inside the drawer.
MARGIN_FLOOR_PCT = 25.0
RISK_RESERVE_RATE = 0.10
FLOW_MARKER = "r109b_visual_flow"
RENDERER_MARKER = "operator_workbench_visual"

# Marketing Engine workspace tabs (fixed order; the first tab is active).
LAB_TABS: tuple[tuple[str, str], ...] = (
    ("lab_firsttest", "Primer Test"),
    ("lab_strategy", "Estrategia"),
    ("lab_angles", "Angulos"),
    ("lab_hooks", "Hook Bank"),
    ("lab_adcopy", "Ad Copy"),
    ("lab_channels", "Canales / Scripts"),
    ("lab_testplan", "Plan de Pruebas"),
    ("lab_learning", "Learning"),
)

# Claim-risk ordering used only to sort existing contract entries
# (never to invent a risk level).
_RISK_RANK = {"low": 0, "medium": 1, "review": 1, "high": 2, "prohibited": 3}

# R5 evidence separation: the main stage speaks operator language only. These
# maps translate contract keys into commercial wording; the raw technical
# input_support_map (output keys + source paths) lives only in the
# Evidence/Audit Drawer.
_COPY_SURFACE_LABELS: dict[str, str] = {
    "strategy_summary": "Estrategia general",
    "core_angle": "Angulo principal",
    "hooks": "Hooks de venta",
    "headlines": "Titulares",
    "primary_texts": "Textos principales de anuncio",
    "short_ads": "Anuncios cortos",
    "long_ads": "Anuncios largos",
    "angle_matrix": "Matriz de angulos",
    "creative_hypotheses": "Hipotesis creativas",
    "channel_packs": "Guiones por canal",
}

_BRIEF_FACT_LABELS: dict[str, str] = {
    "market_context": "Contexto de mercado del brief",
    "target_audience": "Audiencia objetivo declarada",
    "pain_points": "Dolores reales del cliente",
    "customer_language": "Lenguaje real del cliente",
    "desires": "Deseos declarados del cliente",
    "differentiators": "Diferenciadores del producto",
    "proof_elements": "Elementos de prueba disponibles",
    "objections": "Objeciones conocidas del cliente",
}


def _surface_label(key: str) -> str:
    return _COPY_SURFACE_LABELS.get(key, str(key).replace("_", " ").capitalize())


def _fact_label(field_name: str) -> str:
    return _BRIEF_FACT_LABELS.get(field_name, str(field_name).replace("_", " ").capitalize())


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _ul(items: Sequence[Any], css_class: str = "plain") -> str:
    materialized = [str(item) for item in items if str(item).strip()]
    if not materialized:
        return '<p class="empty">(vacio)</p>'
    lis = "".join(f"<li>{_e(item)}</li>" for item in materialized)
    return f'<ul class="{_e(css_class)}">{lis}</ul>'


def _kv(mapping: Mapping[str, Any]) -> str:
    if not mapping:
        return '<p class="empty">(vacio)</p>'
    rows = "".join(
        f"<tr><th>{_e(key)}</th><td>{_e(value)}</td></tr>" for key, value in mapping.items()
    )
    return f'<table class="kv">{rows}</table>'


def _chip(text: str, kind: str = "muted") -> str:
    return f'<span class="chip chip-{_e(kind)}">{_e(text)}</span>'


def _status_chip(status: str) -> str:
    return f'<span class="status status-{_e(status)}">{_e(status.upper())}</span>'


def _fmt_money(value: Any) -> str:
    """Deterministic money formatting for fixture numbers (MXN 1,500.00)."""
    try:
        return f"MXN {float(value):,.2f}"
    except (TypeError, ValueError):
        return f"MXN {value}"


def _fmt_percent(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return f"{value}%"


def _metric(label: str, value: str, sub: str = "", tone: str = "gold", title: str = "") -> str:
    title_attr = f' title="{_e(title)}"' if title else ""
    sub_html = f'<span class="m-sub">{_e(sub)}</span>' if sub else ""
    return (
        f'<div class="metric"{title_attr}><span class="m-label">{_e(label)}</span>'
        f'<span class="m-value m-{_e(tone)}">{_e(value)}</span>{sub_html}</div>'
    )


def _draft_field(
    field_key: str,
    label: str,
    value: Any,
    *,
    rows: int = 3,
    kind: str = "textarea",
    hint: str = "",
) -> str:
    """Editable local operator draft. The system value stays in defaultValue;
    edits live only in localStorage and never touch the fixture/ViewModel."""
    if isinstance(value, (list, tuple)):
        value = "\n".join(str(item) for item in value)
    value = "" if value is None else str(value)
    if kind == "textarea":
        control = (
            f'<textarea class="draft-input" rows="{rows}" spellcheck="false"'
            f' data-draft-field="{_e(field_key)}">{_e(value)}</textarea>'
        )
    else:
        control = (
            f'<input class="draft-input" type="text" spellcheck="false"'
            f' value="{_e(value)}" data-draft-field="{_e(field_key)}">'
        )
    hint_html = f'<span class="draft-hint">{_e(hint)}</span>' if hint else ""
    return (
        '<div class="draft-field" data-draft-wrap>'
        f'<label class="draft-label">{_e(label)}'
        f'<span class="chip chip-gold dirty-chip" data-role="draft_dirty_state" hidden>'
        f"EDITADO</span></label>{control}{hint_html}</div>"
    )


def _draft_reset_button(scope: str) -> str:
    return (
        f'<button type="button" class="reset-btn" data-draft-reset="{_e(scope)}"'
        f' data-marker="reset_to_system_output"'
        f' title="Vuelve a la salida generada por el sistema y borra el draft local">'
        f"Restablecer a salida del sistema</button>"
    )


def _packet_block(
    packet_id: str,
    title: str,
    text: str,
    marker: str,
    *,
    append_drafts: bool = False,
    copy_marker: str = "",
) -> str:
    """Copy-ready packet built deterministically from contract fields."""
    extra = " data-append-drafts" if append_drafts else ""
    copy_attr = f' data-marker="{_e(copy_marker)}"' if copy_marker else ""
    return (
        f'<div class="copyblock" data-packet="{_e(marker)}">'
        f'<div class="cb-head"><span class="cb-title">{_e(title)}</span>'
        f'<button type="button" class="copy-btn" data-copy-button{extra}{copy_attr}'
        f' data-copy-target="{_e(packet_id)}">Copiar</button></div>'
        f'<pre class="cb-body" id="{_e(packet_id)}">{_e(text)}</pre></div>'
    )


def _first_primary(data: Mapping[str, Any]) -> dict[str, Any]:
    return next(
        (action for action in data.get("action_queue") or [] if action.get("is_primary")),
        {},
    )


def _pipeline_stage_for(data: Mapping[str, Any]) -> tuple[str, str]:
    """Honest pipeline stage per candidate, derived only from contract facts."""
    summary = data.get("blocked_queue_summary") or {}
    product = data.get("product") or {}
    richness = data.get("input_richness") or {}
    shopify = data.get("shopify_pack") or {}
    marketing = data.get("marketing_pack") or {}
    economics = data.get("economics") or {}

    if int(summary.get("blocked_count") or 0):
        return "BLOCKED", "risk"
    if not product.get("name"):
        return "SIN CANDIDATO", "muted"
    if str(richness.get("classification", "")) == "INPUT_LOW":
        return "EVALUATING", "warn"
    if not summary.get("can_prepare"):
        return "EVALUATING", "warn"
    missing = [str(item) for item in shopify.get("missing_inputs") or []]
    supplier_pending = any(
        "stock" in item or "proveedor" in item or "costo" in item for item in missing
    )
    if supplier_pending:
        return "SUPPLIER_PENDING", "warn"
    if _medium_risk_entries(data):
        return "MARKETING_READY", "warn"
    if missing:
        return "SHOPIFY_DRAFT_READY", "warn"
    if shopify.get("enabled") and marketing.get("enabled"):
        return "EXPORT_READY", "gold"
    if economics.get("contribution_margin_mxn"):
        return "ECONOMICS_PASSED", "go"
    return "IMPORTED", "muted"


def _candidate_summary(data: Mapping[str, Any]) -> dict[str, Any]:
    """Selector card facts, straight from existing ViewModel fields."""
    product = data.get("product") or {}
    economics = data.get("economics") or {}
    summary = data.get("blocked_queue_summary") or {}
    richness = data.get("input_richness") or {}
    decision = data.get("decision") or {}
    scores = data.get("scores") or {}
    shopify = data.get("shopify_pack") or {}
    modules = _modules_by_id(data)
    status = (modules.get("command_center") or {}).get("status", "empty")

    blocked_count = int(summary.get("blocked_count") or 0)
    can_prepare = bool(summary.get("can_prepare"))
    if blocked_count:
        badge, tone, kind = "BLOQUEADO", "risk", "blocked"
    elif not product.get("name"):
        badge, tone, kind = "SHORTLIST VACIA", "muted", "empty"
    elif str(richness.get("classification", "")) == "INPUT_LOW":
        badge, tone, kind = "INPUT BAJO", "warn", "low_input"
    elif can_prepare:
        badge, tone, kind = "RECOMENDADO", "gold", "recommended"
    else:
        badge, tone, kind = "EN REVISION", "muted", "review"

    stage, stage_tone = _pipeline_stage_for(data)

    margin = economics.get("contribution_margin_mxn")
    margin_str = (
        f"{_fmt_money(margin)} margen/unidad" if margin else "sin economia de candidato"
    )
    breakeven = economics.get("breakeven_cpa_mxn")
    breakeven_str = _fmt_money(breakeven) if breakeven else "-"
    richness_str = (
        f"brief {richness.get('filled_count', 0)}/{richness.get('total_fields', 0)}"
        f" {richness.get('classification', '')}"
        if richness.get("total_fields")
        else "sin brief"
    )
    if blocked_count:
        codes = summary.get("reason_codes") or []
        next_str = f"Bloqueo: {codes[0]}" if codes else "Bloqueo activo"
    else:
        primary = _first_primary(data)
        next_str = (
            f"Siguiente: {primary.get('label', '')}"
            if primary.get("label")
            else "Sin accion primaria"
        )

    opportunity = scores.get("opportunity_score")
    threshold = scores.get("threshold")
    score_str = (
        f"{opportunity} / umbral {threshold}"
        if opportunity is not None
        else "sin score"
    )

    # Drivers/blockers straight from the contract: reason codes act as drivers
    # when the gate passes and as blockers when it blocks.
    gate = str(decision.get("permission_gate", ""))
    codes = [str(code) for code in decision.get("reason_codes") or []]
    if gate.startswith("PASS"):
        drivers = codes
        blockers = [str(item) for item in shopify.get("missing_inputs") or []]
        blockers.extend(
            f"rewrite: {entry.get('copy_key', '')}" for entry in _medium_risk_entries(data)
        )
    else:
        drivers = []
        blockers = codes

    return {
        "fid": str(data.get("fixture_id", "")),
        "name": str(product.get("name") or "Sin candidato en shortlist"),
        "badge": badge,
        "tone": tone,
        "kind": kind,
        "stage": stage,
        "stage_tone": stage_tone,
        "status": str(status),
        "outcome": str(decision.get("outcome", "") or "SIN CANDIDATO"),
        "margin_str": margin_str,
        "breakeven_str": breakeven_str,
        "richness_str": richness_str,
        "next_str": next_str,
        "can_prepare": can_prepare,
        "score_str": score_str,
        "sort_score": str(opportunity if opportunity is not None else -1),
        "sort_margin": str(margin if margin is not None else -1),
        "sort_risk": str(scores.get("claim_risk") if scores.get("claim_risk") is not None else 99),
        "drivers": drivers[:3],
        "blockers": blockers[:3],
    }


_SELECTOR_FILTERS: tuple[tuple[str, str], ...] = (
    ("all", "Todos"),
    ("recommended", "Recomendado"),
    ("blocked", "Bloqueado"),
    ("low_input", "Input bajo"),
    ("empty", "Shortlist vacia"),
)

_SELECTOR_SORTS: tuple[tuple[str, str], ...] = (
    ("score", "Score"),
    ("margin", "Margen"),
    ("risk", "Riesgo"),
    ("state", "Estado"),
)


def _render_selector(
    candidates: Sequence[Mapping[str, Any]], selected_fid: str
) -> str:
    """Candidate pipeline board: filters, sorting, composite score, drivers,
    blockers, stage and next action per candidate. Local-only interaction."""
    filters = "".join(
        f'<button type="button" class="pill-btn{" active" if key == "all" else ""}"'
        f' data-filter="{key}">{_e(label)}</button>'
        for key, label in _SELECTOR_FILTERS
    )
    sorts = "".join(
        f'<button type="button" class="pill-btn" data-sort="{key}">{_e(label)}</button>'
        for key, label in _SELECTOR_SORTS
    )
    cards = []
    for cand in candidates:
        active = cand["fid"] == selected_fid
        selected_attr = ' data-marker="selected_candidate_state"' if active else ""
        drivers = (
            '<div class="sc-line sc-drivers" data-drivers="top_drivers">'
            "<b>Drivers:</b> " + _e(", ".join(cand["drivers"]) or "(sin drivers)") + "</div>"
        )
        blockers = (
            '<div class="sc-line sc-blockers" data-blockers="top_blockers">'
            "<b>Blockers:</b> " + _e(", ".join(cand["blockers"]) or "(sin blockers)") + "</div>"
        )
        cards.append(
            f'<div class="sel-card{" active" if active else ""}"'
            f' data-candidate-select="{_e(cand["fid"])}"{selected_attr}'
            f' data-candidate-kind="{_e(cand["kind"])}"'
            f' data-sort-score="{_e(cand["sort_score"])}"'
            f' data-sort-margin="{_e(cand["sort_margin"])}"'
            f' data-sort-risk="{_e(cand["sort_risk"])}"'
            f' data-sort-state="{_e(cand["badge"])}"'
            f' title="Cambia el candidato visible; seleccion local del navegador">'
            f'<div class="sc-top"><span class="chip chip-{_e(cand["tone"])}">'
            f'{_e(cand["badge"])}</span>'
            f'<span class="chip chip-{_e(cand["stage_tone"])} sc-stage">{_e(cand["stage"])}</span></div>'
            f'<div class="sc-name">{_e(cand["name"])}</div>'
            f'<div class="sc-score">Score compuesto: <b>{_e(cand["score_str"])}</b></div>'
            f'<div class="sc-money">{_e(cand["margin_str"])}</div>'
            f"{drivers}{blockers}"
            f'<div class="sc-next">{_e(cand["next_str"])}</div>'
            f'<div class="sc-rich">{_e(cand["richness_str"])}</div></div>'
        )
    compare_rows = "".join(
        f"<tr><th>{_e(cand['name'])}</th><td>{_e(cand['badge'])}</td>"
        f"<td>{_e(cand['stage'])}</td><td>{_e(cand['score_str'])}</td>"
        f"<td>{_e(cand['margin_str'])}</td><td>{_e(cand['breakeven_str'])}</td>"
        f"<td>{_e(cand['richness_str'])}</td><td>{_e(cand['next_str'])}</td></tr>"
        for cand in candidates
    )
    compare = (
        '<details class="sel-compare" data-marker="candidate_comparison">'
        "<summary>Tabla compacta / comparacion (solo campos existentes del ViewModel)</summary>"
        '<table class="kv"><tr><th>candidato</th><td>estado</td><td>etapa</td>'
        "<td>score</td><td>margen</td><td>breakeven CPA</td><td>brief</td>"
        "<td>siguiente / bloqueo</td></tr>"
        + compare_rows
        + "</table></details>"
    )
    single_note = (
        '<p class="honesty">Un candidato embebido en este render. Workspace'
        " multi-candidato: --fixture-dir tests/fixtures/a8_r109a --output"
        " runs/.../workspace.html</p>"
        if len(candidates) == 1
        else '<p class="honesty">Candidatos embebidos del fixture congelado;'
        " sin discovery en vivo.</p>"
    )
    return (
        '<div class="card selector" data-marker="product_selector"'
        ' data-role="candidate_switcher">'
        "<h3>Pipeline de candidatos (solo fixture)</h3>"
        '<div class="sel-controls">'
        f'<span class="sel-ctl-label">Filtrar</span>'
        f'<span data-role="selector_filters">{filters}</span>'
        f'<span class="sel-ctl-label">Ordenar por</span>'
        f'<span data-role="selector_sort">{sorts}</span></div>'
        f'<div class="sel-cards" data-marker="candidate_list">{"".join(cards)}</div>'
        f"{compare}{single_note}</div>"
    )


def _card(title: str, body: str, attrs: str = "") -> str:
    return (
        f'<div class="card" {attrs}><h3>{_e(title)}</h3>{body}</div>'
        if title
        else f'<div class="card" {attrs}>{body}</div>'
    )


def _modules_by_id(data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["module_id"]: entry for entry in data.get("module_status_summary") or []}


def _risk_chip_for(data: Mapping[str, Any], copy_key: str) -> str:
    for entry in data["marketing_pack"].get("claim_risk_by_copy") or []:
        if entry.get("copy_key") == copy_key:
            level = _e(entry.get("risk_level", "unknown"))
            rewrite = _e(entry.get("safe_rewrite", ""))
            reason = _e(entry.get("reason", ""))
            return (
                f'<div class="risk-note risk-{level}" data-copy-risk="{_e(copy_key)}">'
                f'<span class="risk-tag">riesgo: {level}</span> {reason}'
                f'<br><span class="safe">Rewrite seguro: {rewrite}</span></div>'
            )
    return ""


def _claim_guard_card(notes: Mapping[str, Any], surface: str) -> str:
    parts = [
        f'<div class="guard-card" data-contract-section="claim_guard"'
        f' data-role="claim_guard_adjacent" data-adjacent-to="{_e(surface)}">',
        '<div class="guard-head">Claim Guard (adyacente)</div>',
        '<div class="guard-body">',
        '<h4 class="ok">Permitido decir</h4>',
        _ul(notes.get("allowed_claims") or []),
        '<h4 class="warn">Riesgoso - reescribir</h4>',
        _ul(notes.get("risky_claims") or []),
        '<h4 class="no">Prohibido</h4>',
        _ul(notes.get("prohibited_claims") or []),
        '<h4 class="ok">Redaccion segura</h4>',
        _ul(notes.get("safe_wording") or []),
        f'<p class="guard-summary">{_e(notes.get("summary", ""))}</p>',
        "</div></div>",
    ]
    return "".join(parts)


def _payload_blocks(
    data: Mapping[str, Any],
    section: str,
    *,
    suppressed_reason: str = "",
    collapsible_keys: Sequence[str] = (),
) -> str:
    """Copy-ready payload blocks from the canonical copy_payloads registry."""
    payloads = data.get("copy_payloads") or {}
    if not payloads.get("enabled"):
        return (
            f'<p class="disabled">Sin payloads: {_e(payloads.get("disabled_reason", ""))}</p>'
        )
    items = [item for item in payloads.get("items") or [] if item.get("section") == section]
    if not items:
        return '<p class="empty">(sin payloads para esta seccion)</p>'
    if suppressed_reason:
        return (
            f'<p class="disabled" data-copy-suppressed="{_e(section)}">'
            f"Copiado deshabilitado: {_e(suppressed_reason)}</p>"
        )
    parts = []
    for item in items:
        key = _e(item.get("key", ""))
        label = _e(item.get("label", ""))
        text = _e(item.get("text", ""))
        block = (
            f'<div class="copyblock" data-payload-key="{key}">'
            f'<div class="cb-head"><span class="cb-title">{label}</span>'
            f'<button type="button" class="copy-btn" data-copy-button'
            f' data-copy-target="payload_{key}">Copiar</button></div>'
            f'<pre class="cb-body" id="payload_{key}">{text}</pre></div>'
        )
        if item.get("key") in collapsible_keys:
            block = f"<details><summary>{label} (abrir)</summary>{block}</details>"
        parts.append(block)
    return "".join(parts)


# --- deterministic packet texts (contract fields only, no invented data) --------

def _lines(title: str, items: Sequence[Any]) -> list[str]:
    out = [f"== {title} =="]
    materialized = [str(item) for item in items if str(item).strip()]
    out.extend(f"- {item}" for item in materialized)
    if not materialized:
        out.append("- (vacio)")
    out.append("")
    return out


def _packet_shopify_text(data: Mapping[str, Any]) -> str:
    pack = data.get("shopify_pack") or {}
    lines = [
        "SHOPIFY LISTING PACKET (borrador local; nada se publica desde aqui)",
        "",
        f"Titulo: {pack.get('title', '')}",
        f"Subtitulo: {pack.get('subtitle', '')}",
        f"Handle: {pack.get('handle', '')}",
        f"Categoria: {pack.get('category', '')}",
        f"Precio: {pack.get('price', '')} / Compare-at: {pack.get('compare_at_price', '')}",
        "",
    ]
    lines += _lines("Bullets", pack.get("bullets") or [])
    lines += [
        "== Descripcion corta ==",
        str(pack.get("short_description", "")),
        "",
        "== Descripcion larga ==",
        str(pack.get("long_description", "")),
        "",
        f"SEO title: {pack.get('seo_title', '')}",
        f"SEO meta: {pack.get('seo_meta_description', '')}",
        "Tags: " + ", ".join(str(tag) for tag in pack.get("tags") or []),
        "",
    ]
    lines += _lines("Inputs faltantes antes de publicar", pack.get("missing_inputs") or [])
    lines.append(f"Disclaimer: {pack.get('claim_safe_disclaimer', '')}")
    return "\n".join(lines)


def _packet_marketing_text(data: Mapping[str, Any]) -> str:
    pack = data.get("marketing_pack") or {}
    lines = ["MARKETING PACKET (preparacion; sin gasto, sin publicacion en Meta)", ""]
    if pack.get("input_richness_warning"):
        lines += [f"AVISO: {pack.get('input_richness_warning')}", ""]
    lines += [
        f"Angulo core: {pack.get('core_angle', '')}",
        f"Estrategia: {pack.get('strategy_summary', '')}",
        f"Buyer: {pack.get('buyer_profile', '')}",
        "",
    ]
    lines += _lines("Hooks", pack.get("hooks") or [])
    lines += _lines("Headlines", pack.get("headlines") or [])
    lines += _lines("Textos primarios", pack.get("primary_texts") or [])
    lines += _lines("Anuncios cortos", pack.get("short_ads") or [])
    lines += _lines("Anuncios largos", pack.get("long_ads") or [])
    lines += _lines("Captions", pack.get("captions") or [])
    plan = pack.get("testing_plan_with_thresholds") or {}
    lines.append(
        "Boundary de prueba (dry-run): "
        + str(plan.get("first_test_budget_boundary_dry_run_only", ""))
    )
    return "\n".join(lines)


def _packet_supplier_text(data: Mapping[str, Any]) -> str:
    product = data.get("product") or {}
    economics = data.get("economics") or {}
    pack = data.get("shopify_pack") or {}
    cost = economics.get("product_cost_mxn")
    cost_str = _fmt_money(cost) if cost else "(costo del fixture no disponible)"
    lines = [
        f"Hola {product.get('supplier', 'proveedor')}:",
        "",
        f"Sobre el producto \"{product.get('name', '')}\" (ref {product.get('product_id', '')}):",
        "",
        "1. Confirmas stock disponible y tiempo de entrega actual?",
        f"2. Confirmas costo por unidad (referencia local: {cost_str}) y costo de envio?",
        "3. Puedes compartir fotos reales del producto (no de catalogo)?",
    ]
    missing = pack.get("missing_inputs") or []
    if missing:
        lines.append("4. Nos faltan estos datos para preparar la ficha: " + ", ".join(map(str, missing)))
    lines += [
        "",
        "Nota: preparacion en dry-run; todavia no es una orden en firme.",
    ]
    return "\n".join(lines)


def _packet_claim_safe_text(data: Mapping[str, Any]) -> str:
    guard = data.get("claim_guard") or {}
    lines = ["CLAIM-SAFE COPY PACKET (solo redaccion segura aprobada por Claim Guard)", ""]
    lines += _lines("Permitido decir", guard.get("allowed_claims") or [])
    lines += _lines("Redaccion segura", guard.get("safe_wording") or [])
    rewrites = [
        f"{entry.get('copy_key', '')}: {entry.get('safe_rewrite', '')}"
        for entry in data["marketing_pack"].get("claim_risk_by_copy") or []
        if entry.get("safe_rewrite")
    ]
    lines += _lines("Rewrites seguros por superficie", rewrites)
    lines += _lines("Nunca decir", guard.get("prohibited_claims") or [])
    lines.append(f"Resumen guard: {guard.get('claim_guard_summary', '')}")
    return "\n".join(lines)


def _packet_full_text(data: Mapping[str, Any]) -> str:
    product = data.get("product") or {}
    decision = data.get("decision") or {}
    economics = data.get("economics") or {}
    shopify = data.get("shopify_pack") or {}
    richness = data.get("input_richness") or {}
    boundary = data.get("safety_boundary") or {}
    lines = [
        "SELLING PACKET LOCAL - SYNAPSE Fase 1 (dry-run; operador-en-control)",
        "",
        "== Producto ==",
        f"- {product.get('name', '')} ({product.get('product_id', '')})",
        f"- Proveedor: {product.get('supplier', '')} / Mercado: {product.get('market', '')}",
        "",
        "== Decision ==",
        f"- {decision.get('outcome', '')} (gate {decision.get('permission_gate', '')})",
        f"- {decision.get('reason', '')}",
        "",
        "== Economia (numeros del fixture) ==",
        f"- Precio: {_fmt_money(economics.get('price_mxn'))}"
        f" / Costo: {_fmt_money(economics.get('product_cost_mxn'))}",
        f"- Margen: {_fmt_money(economics.get('contribution_margin_mxn'))}"
        f" ({_fmt_percent(economics.get('contribution_margin_percent'))})",
        f"- Breakeven CPA: {_fmt_money(economics.get('breakeven_cpa_mxn'))}",
        "",
        _packet_shopify_text(data),
        "",
        _packet_marketing_text(data),
        "",
    ]
    missing = list(shopify.get("missing_inputs") or [])
    missing.extend(f"Brief: {field}" for field in richness.get("missing_fields") or [])
    lines += _lines("Faltantes antes de publicar", missing)
    lines.append(_packet_claim_safe_text(data))
    lines.append("")
    lines += _lines("Checklist de publicacion (manual)", shopify.get("publish_checklist") or [])
    lines += [
        "== Boundary de evidencia ==",
        "- Sin escrituras en vivo, sin gasto, sin red, sin fulfillment"
        if boundary.get("no_live_writes")
        else "- Boundary declarado en safety_boundary del contrato",
        "- Fixture congelado; render determinista; el operador decide y ejecuta.",
    ]
    return "\n".join(lines)


def _selling_packet_panel(data: Mapping[str, Any]) -> str:
    """Selling Packet Local export panel; full packet only for preparable states."""
    summary = data.get("blocked_queue_summary") or {}
    if not summary.get("can_prepare"):
        blocked_count = int(summary.get("blocked_count") or 0)
        if blocked_count:
            reason = "producto bloqueado; reparar o rechazar antes de exportar"
        elif not (data.get("product") or {}).get("name"):
            reason = "shortlist vacia; no hay nada que exportar"
        else:
            reason = "el candidato necesita enriquecimiento antes del sell-prep"
        return (
            f'<div class="card" data-packet-unavailable="true">'
            f"<h3>Selling Packet Local</h3>"
            f'<p class="disabled">Paquete no disponible: {_e(reason)}.'
            f" Nunca se exporta un paquete como listo en este estado.</p></div>"
        )
    return (
        '<div class="card export-panel" data-marker="selling_packet_export">'
        "<h3>Selling Packet Local - exportar y copiar</h3>"
        '<p class="honesty">Paquetes construidos deterministicamente desde el contrato.'
        " El boton del paquete completo agrega tus drafts locales al copiar"
        " (solo memoria del navegador; nada se envia).</p>"
        + _packet_block(
            "packet_full",
            "Selling Packet completo (+ drafts locales al copiar)",
            _packet_full_text(data),
            "full_selling_packet",
            append_drafts=True,
            copy_marker="copy_full_selling_packet",
        )
        + '<details class="payload-drawer"><summary>Paquetes individuales</summary>'
        + _packet_block(
            "packet_shopify_cc",
            "Shopify listing packet",
            _packet_shopify_text(data),
            "shopify_listing_packet",
        )
        + _packet_block(
            "packet_marketing_cc",
            "Marketing packet",
            _packet_marketing_text(data),
            "marketing_packet",
        )
        + _packet_block(
            "packet_supplier_cc",
            "Mensaje al proveedor (stock / costo)",
            _packet_supplier_text(data),
            "supplier_confirmation_message",
        )
        + _packet_block(
            "packet_claimsafe_cc",
            "Claim-safe copy packet",
            _packet_claim_safe_text(data),
            "claim_safe_copy_packet",
        )
        + "</details></div>"
    )


# --- module sections -----------------------------------------------------------

def _render_rail(data: Mapping[str, Any], active_module: str) -> str:
    parts = [
        '<nav id="module_rail" data-contract-section="module_rail"'
        ' data-source-contract="module_status_summary">',
        '<div class="logo">SYNAPSE <span>OS</span>'
        "<small>Operator Workbench - Fase 1 dry-run</small></div>",
    ]
    permission_gate = str((data.get("decision") or {}).get("permission_gate") or "")
    for index, entry in enumerate(data.get("module_status_summary") or [], start=1):
        module_id = _e(entry.get("module_id", ""))
        status = _e(entry.get("status", ""))
        active = " active" if entry.get("module_id") == active_module else ""
        badge = str(entry.get("badge_text", ""))
        # Display-only: the raw outcome string overflows the rail; the gate
        # value (PASS / BLOCK / ...) is the same contract, shorter.
        if entry.get("module_id") == "decision_center" and permission_gate:
            badge = permission_gate
        parts.append(
            f'<div class="nav-item{active}" data-nav-module="{module_id}"'
            f' data-module-status="{status}">'
            f'<span class="n">{index:02d}</span>'
            f'<span class="t">{_e(entry.get("label", ""))}</span>'
            f'<span class="b b-{status}">{_e(badge)}</span></div>'
        )
    parts.append(
        '<div class="rail-foot">Sin escrituras en vivo - sin gasto - sin red<br>'
        f'fixture: {_e(data.get("fixture_id", ""))}<br>{_e(VISUAL_VERSION)}</div>'
    )
    parts.append("</nav>")
    return "".join(parts)


def _render_session_gate(data: Mapping[str, Any]) -> str:
    """First-run local session overlay. Explicitly NOT real authentication."""
    return (
        '<div id="operator_session_gate" class="session-gate"'
        ' data-marker="operator_session_gate" data-session-scope="local_session_only">'
        '<div class="gate-card">'
        '<div class="gate-brand">SYNAPSE <span>OPERATOR OS</span></div>'
        "<h1>SYNAPSE Operator Session</h1>"
        '<p class="gate-sub">Sistema local de preparacion comercial - Fase 1</p>'
        '<div class="gate-modes">'
        + _chip("Fase 1", "steel")
        + _chip("Dry-run", "steel")
        + _chip("Operador-en-control", "gold")
        + "</div>"
        '<label class="gate-label" for="operator_alias_input">Alias local del operador (opcional)</label>'
        '<input id="operator_alias_input" class="gate-input" type="text" maxlength="40"'
        ' autocomplete="off" spellcheck="false" placeholder="ej. operador-mx"'
        ' data-marker="operator_alias_memory">'
        '<button type="button" class="gate-enter" data-gate-enter>Entrar al Workbench</button>'
        '<p class="gate-disclaimer">No es autenticacion real; sesion local del navegador'
        " (localStorage). Sin backend, sin cuenta, sin credenciales, sin red.</p>"
        f'<p class="gate-fixture">fixture: {_e(data.get("fixture_id", ""))}'
        " - offline - deterministico</p>"
        "</div></div>"
    )


def _render_header(data: Mapping[str, Any]) -> str:
    product = data.get("product") or {}
    decision = data.get("decision") or {}
    economics = data.get("economics") or {}
    summary = data.get("blocked_queue_summary") or {}
    queue = data.get("action_queue") or []

    name = _e(product.get("name") or "Sin candidato en shortlist")
    outcome = _e(decision.get("outcome", ""))
    modules = _modules_by_id(data)
    command_status = _e((modules.get("command_center") or {}).get("status", "empty"))

    margin = economics.get("contribution_margin_mxn")
    if margin:
        metrics = (
            _metric(
                "Margen / unidad",
                _fmt_money(margin),
                sub=f"{_fmt_percent(economics.get('contribution_margin_percent'))} de contribucion",
                tone="gold",
                title="economics.contribution_margin_mxn (numeros del fixture)",
            )
            + _metric(
                "Breakeven CPA",
                _fmt_money(economics.get("breakeven_cpa_mxn")),
                sub="tope de adquisicion por unidad",
                tone="gold",
                title="economics.breakeven_cpa_mxn (numeros del fixture)",
            )
            + _metric(
                "Precio",
                _fmt_money(economics.get("price_mxn")),
                sub=f"compare-at {_fmt_money(economics.get('compare_at_price_mxn'))}",
                tone="ink",
                title="economics.price_mxn / compare_at_price_mxn",
            )
        )
    else:
        metrics = (
            '<span class="metric-empty">Sin metricas de dinero: el fixture no tiene'
            " economia de candidato preparable.</span>"
        )

    primary = next((action for action in queue if action.get("is_primary")), None)
    if summary.get("can_prepare") and primary:
        cta = (
            f'<button type="button" class="cta cta-go" data-cta="prepare"'
            f' data-principle="operator_in_control"'
            f' data-nav-module="{_e(primary.get("target_module", ""))}">'
            f'Preparar venta con operador-en-control - {_e(primary.get("label", ""))}</button>'
        )
    elif primary:
        cta = (
            f'<button type="button" class="cta cta-warn" data-cta="next_action"'
            f' data-nav-module="{_e(primary.get("target_module", ""))}">'
            f'Siguiente accion - {_e(primary.get("label", ""))}</button>'
        )
    else:
        cta = '<span class="cta cta-muted" data-cta="none">Sin accion primaria</span>'

    return (
        f'<header class="cockpit" data-marker="premium_top_cockpit"'
        f' data-command-status="{command_status}">'
        f'<div class="ck-row ck-top">'
        f'<div class="ck-id"><div class="p-name">{name}</div>'
        f'<div class="p-meta">{_e(product.get("product_id", ""))}'
        f' {_e(product.get("supplier", ""))} {_e(product.get("market", ""))}</div></div>'
        f'<span class="status status-{command_status}">{outcome or "SIN CANDIDATO"}</span>'
        f'<div class="spacer"></div>'
        f'<span class="chip chip-gold" data-saved-indicator hidden'
        f' title="Cambio guardado en la memoria local del navegador">GUARDADO LOCAL</span>'
        f'<span class="chip chip-alias" data-operator-alias-chip hidden'
        f' title="Alias local del navegador; no es autenticacion real"></span>'
        f'<button type="button" class="drawer-btn" data-drawer-open'
        f' title="Auditoria tecnica: origen de datos, cadena determinista, mapa de'
        f' capacidades">Ver evidencia</button>'
        f'<span class="chip chip-steel" title="Datos de fixture congelado; render offline">'
        f"FIXTURE LOCAL - OFFLINE</span>"
        f'<span class="chip chip-boundary" data-marker="safety_boundary_chip"'
        f' title="Boundary Fase 1: sin escrituras en vivo, sin gasto, sin red externa">'
        f"SIN ESCRITURAS - SIN GASTO - SIN RED</span></div>"
        f'<div class="ck-row ck-money" data-marker="money_metrics_bar">{metrics}'
        f'<div class="spacer"></div>{cta}</div></header>'
    )


def _medium_risk_entries(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in data["marketing_pack"].get("claim_risk_by_copy") or []
        if entry.get("risk_level") == "medium"
    ]


def _selling_pack_snapshot(data: Mapping[str, Any]) -> str:
    """Sell-prep snapshot for the recommended state, built only from contract fields."""
    summary = data.get("blocked_queue_summary") or {}
    if not summary.get("can_prepare"):
        return ""

    decision = data.get("decision") or {}
    economics = data.get("economics") or {}
    board = data.get("system_health_board") or {}
    shopify = data.get("shopify_pack") or {}
    marketing = data.get("marketing_pack") or {}
    richness = data.get("input_richness") or {}
    queue = data.get("action_queue") or []

    ready_items: list[str] = [
        f"Decision: {decision.get('outcome', '')} (gate {decision.get('permission_gate', '')})",
    ]
    margin = economics.get("contribution_margin_mxn")
    if margin:
        ready_items.append(
            f"Margen positivo: MXN {margin} "
            f"({economics.get('contribution_margin_percent', '')}%) por unidad"
        )
    if shopify.get("enabled"):
        ready_items.append("Borrador de Shopify pack listo (payloads copy-ready)")
    if marketing.get("enabled"):
        ready_items.append("Marketing pack listo (angulos, hooks, ads, plan de pruebas)")
    ready_items.append(f"Claim guard: {board.get('claim_guard_status', '')} - manejable")

    missing_items: list[str] = list(shopify.get("missing_inputs") or [])
    rewrites = _medium_risk_entries(data)
    if rewrites:
        surfaces = ", ".join(entry.get("copy_key", "") for entry in rewrites)
        missing_items.append(f"Revisar {len(rewrites)} rewrites de copy: {surfaces}")
    for field in richness.get("missing_fields") or []:
        missing_items.append(f"Brief: completar {field}")

    primary = next((action for action in queue if action.get("is_primary")), None)
    secondary = [action for action in queue if not action.get("is_primary")]
    primary_html = (
        f'<div class="snap-primary" data-nav-module="{_e(primary.get("target_module", ""))}">'
        f'{_e(primary.get("label", ""))}</div>'
        if primary
        else '<p class="empty">(sin accion primaria)</p>'
    )
    secondary_html = _ul([action.get("label", "") for action in secondary], "plain")

    return (
        '<div class="card snapshot" data-contract-section="selling_pack_snapshot">'
        "<h3>Venta Prep Snapshot</h3>"
        '<div class="grid g3">'
        '<div class="snap-col" data-snapshot="ready_now">'
        '<h4 class="ok">Listo ahora</h4>' + _ul(ready_items, "plain go") + "</div>"
        '<div class="snap-col" data-snapshot="missing_before_publish">'
        '<h4 class="warn">Falta antes de publicar</h4>' + _ul(missing_items, "plain warn") + "</div>"
        '<div class="snap-col" data-snapshot="operator_next_actions"'
        ' data-principle="operator_in_control">'
        '<h4 class="go">Siguiente accion del operador</h4>'
        + primary_html
        + "<h4>Despues</h4>"
        + secondary_html
        + "</div></div>"
        '<p class="honesty">El sistema prepara; el operador decide y ejecuta. Nada se publica solo.</p>'
        "</div>"
    )


def _payload_count(data: Mapping[str, Any], section: str) -> int:
    payloads = data.get("copy_payloads") or {}
    return sum(1 for item in payloads.get("items") or [] if item.get("section") == section)


def _synapse_already_did_items(data: Mapping[str, Any]) -> list[str]:
    """Completed system actions, listed only when the ViewModel actually has them."""
    items: list[str] = []
    economics = data.get("economics") or {}
    richness = data.get("input_richness") or {}
    shopify = data.get("shopify_pack") or {}
    marketing = data.get("marketing_pack") or {}
    guard = data.get("claim_guard") or {}
    pipeline = data.get("candidate_pipeline") or {}
    provenance = data.get("provenance") or {}
    boundary = data.get("safety_boundary") or {}

    margin = economics.get("contribution_margin_mxn")
    if margin:
        items.append(
            f"Evaluo el margen de contribucion: MXN {margin} "
            f"({economics.get('contribution_margin_percent', '')}%) y el CPA breakeven "
            f"MXN {economics.get('breakeven_cpa_mxn', '')}"
        )
    if richness.get("classification"):
        items.append(
            f"Clasifico la riqueza del brief: {richness.get('classification')} "
            f"({richness.get('filled_count', 0)}/{richness.get('total_fields', 0)} campos, "
            f"politica {richness.get('policy', '')})"
        )
    if shopify.get("enabled"):
        items.append(
            f"Construyo el borrador del Shopify pack "
            f"({_payload_count(data, 'shopify_pack')} payloads copy-ready)"
        )
    if marketing.get("enabled"):
        items.append(
            f"Construyo el marketing pack ({len(marketing.get('angle_matrix') or [])} angulos, "
            f"{len(marketing.get('hooks') or [])} hooks, "
            f"{len(marketing.get('creative_hypotheses') or [])} hipotesis de prueba)"
        )
    risky = _texts_len(guard.get("risky_claims"))
    rewrites = _medium_risk_entries(data)
    if risky or rewrites:
        items.append(
            f"Detecto {risky} claim(s) riesgoso(s) y genero rewrites seguros "
            f"para {len(rewrites)} superficie(s) de copy"
        )
    if pipeline.get("pipeline_stage"):
        items.append(
            f"Resumio el pipeline de candidatos (etapa: {pipeline.get('pipeline_stage')}; "
            f"fuente: {pipeline.get('source', '')})"
        )
    if provenance.get("deterministic_renderer"):
        items.append(
            "Registro la cadena de evidencia determinista (mismo fixture, mismo"
            " output; auditoria completa en el drawer)"
        )
    if boundary.get("no_live_writes"):
        items.append("Preservo el boundary: sin escrituras en vivo, sin gasto, sin red")
    return items


def _texts_len(value: Any) -> int:
    if isinstance(value, (list, tuple)):
        return len([item for item in value if str(item).strip()])
    return 0


def _commercial_brief(data: Mapping[str, Any]) -> str:
    """SYNAPSE executive operating brief: only for a preparable (recommended) product."""
    summary = data.get("blocked_queue_summary") or {}
    if not summary.get("can_prepare"):
        return ""

    decision = data.get("decision") or {}
    economics = data.get("economics") or {}
    board = data.get("system_health_board") or {}
    guard = data.get("claim_guard") or {}
    shopify = data.get("shopify_pack") or {}
    marketing = data.get("marketing_pack") or {}
    richness = data.get("input_richness") or {}
    surface = data.get("capability_surface_map") or {}
    queue = data.get("action_queue") or []

    verdict = (
        '<div class="verdict-hero" data-marker="commercial_verdict_card">'
        '<span class="vh-tag">Veredicto comercial</span>'
        f'<div class="vh-outcome">{_e(decision.get("outcome", ""))}</div>'
        f'<div class="vh-gate">gate: {_e(decision.get("permission_gate", ""))}</div>'
        f'<p class="brief-why">{_e(decision.get("reason", ""))}</p>'
        + "".join(_chip(code, "go") for code in decision.get("reason_codes") or [])
        + "</div>"
    )

    money_card = (
        '<div class="brief-card money-card" data-marker="money_readiness_card">'
        '<span class="vh-tag">Dinero y preparacion</span>'
        + _metric(
            "Margen / unidad",
            _fmt_money(economics.get("contribution_margin_mxn")),
            sub=f"{_fmt_percent(economics.get('contribution_margin_percent'))} de contribucion",
        )
        + _metric(
            "Breakeven CPA",
            _fmt_money(economics.get("breakeven_cpa_mxn")),
            sub="tope por adquisicion",
        )
        + _ul(
            [
                f"{_payload_count(data, 'shopify_pack')} payloads Shopify copy-ready",
                f"{len(marketing.get('angle_matrix') or [])} angulos / "
                f"{len(marketing.get('hooks') or [])} hooks de marketing",
                f"Brief del operador: {richness.get('filled_count', 0)}/"
                f"{richness.get('total_fields', 0)} campos"
                f" ({richness.get('classification', '')})",
            ],
            "plain go",
        )
        + "</div>"
    )

    rewrites = _medium_risk_entries(data)
    risk_card = (
        '<div class="brief-card risk-card" data-marker="risk_control_card">'
        '<span class="vh-tag">Riesgo bajo control</span>'
        + _kv(
            {
                "claim_guard": board.get("claim_guard_status", ""),
                "claims riesgosos": _texts_len(guard.get("risky_claims")),
                "rewrites pendientes": len(rewrites),
                "claims prohibidos": _texts_len(guard.get("prohibited_claims")),
            }
        )
        + '<p class="honesty">Riesgo detectado y acotado por Claim Guard;'
        " nada se publica hasta resolverlo.</p></div>"
    )

    did = _ul(_synapse_already_did_items(data), "plain go")

    blockers: list[str] = list(shopify.get("missing_inputs") or [])
    if rewrites:
        blockers.append(
            "Rewrites pendientes: "
            + ", ".join(entry.get("copy_key", "") for entry in rewrites)
        )
    for field in richness.get("missing_fields") or []:
        blockers.append(f"Brief: completar {field}")

    primary = next((action for action in queue if action.get("is_primary")), None)
    first_move = (
        f'<div class="snap-primary" data-nav-module="{_e(primary.get("target_module", ""))}">'
        f'{_e(primary.get("label", ""))}</div>'
        f'<p class="honesty">{_e(primary.get("reason", "")) if primary else ""}</p>'
        if primary
        else '<p class="empty">(sin accion primaria)</p>'
    )

    refuses = [f"Prohibido reclamar: {item}" for item in surface.get("forbidden_to_claim") or []]
    refuses.extend(
        [
            "No publica en Shopify, no gasta en Meta, no ordena a Dropi",
            "No toca red externa ni credenciales; todo es preparacion local",
        ]
    )

    return (
        '<div class="card brief" data-contract-section="commercial_intelligence_brief"'
        ' data-marker="executive_operating_brief">'
        "<h3>SYNAPSE Commercial Brief - operating brief ejecutivo</h3>"
        f'<div class="grid g3 brief-hero">{verdict}{money_card}{risk_card}</div>'
        '<div class="grid g3">'
        '<div class="snap-col" data-brief-col="synapse_already_did">'
        '<h4 class="go">Lo que SYNAPSE ya hizo</h4>' + did + "</div>"
        '<div class="snap-col" data-brief-col="publish_blockers">'
        '<h4 class="warn">Bloqueadores antes de publicar</h4>'
        + _ul(blockers, "plain warn")
        + "</div>"
        '<div class="snap-col" data-brief-col="operator_first_move">'
        '<h4 class="ok">Primer movimiento del operador</h4>' + first_move + "</div></div>"
        '<div class="trust-boundary" data-brief-col="synapse_refuses_to_do"'
        ' data-marker="trust_boundary_card">'
        '<h4 class="no">Lo que SYNAPSE se niega a hacer (frontera de confianza)</h4>'
        + _ul(refuses, "plain risk")
        + "</div></div>"
    )


def _capability_strip(data: Mapping[str, Any]) -> str:
    surface = data.get("capability_surface_map") or {}
    tiers = (
        ("real_now", "Real hoy", "go"),
        ("fixture_only", "Solo fixture", "muted"),
        ("future_or_not_connected", "Futuro / no conectado", "warn"),
        ("forbidden_to_claim", "Prohibido reclamar", "risk"),
    )
    columns = []
    for key, label, kind in tiers:
        chips = "".join(_chip(item, kind) for item in surface.get(key) or [])
        columns.append(
            f'<div class="strip-col" data-capability-tier="{_e(key)}">'
            f'<span class="strip-label">{_e(label)}</span>{chips}</div>'
        )
    return (
        '<div class="card strip" data-contract-section="capability_surface_strip">'
        "<h3>Superficie de capacidades SYNAPSE</h3>" + "".join(columns) + "</div>"
    )


# Brain map nodes: (label, contract key, kind). Capability nodes resolve their
# tier by membership in capability_surface_map; boundary nodes read the
# safety_boundary flags. The renderer never invents a tier.
_BRAIN_NODES: tuple[tuple[str, str, str], ...] = (
    ("Discovery", "candidate_pipeline_counts", "capability"),
    ("Evaluacion financiera", "economics_unit_numbers", "capability"),
    ("Product Lab", "input_richness_classification_r105_3", "capability"),
    ("Shopify pack", "shopify_pack_content", "capability"),
    ("Publicacion Shopify", "shopify_publish_flow", "capability"),
    ("Marketing pack", "marketing_pack_content", "capability"),
    ("Ejecucion Meta", "meta_campaign_execution", "capability"),
    ("Claim Guard", "claim_guard_adjacent_to_copy_surfaces", "capability"),
    ("Evidence", "offline_static_html_render_no_network", "capability"),
    ("Learning feedback", "learning_feedback_live_observations", "capability"),
    ("Spend Guard", "no_spend", "boundary"),
    ("Fulfillment", "no_fulfillment", "boundary"),
)

_TIER_PRESENTATION: dict[str, tuple[str, str]] = {
    "real_now": ("REAL HOY", "go"),
    "fixture_only": ("SOLO FIXTURE", "steel"),
    "future_or_not_connected": ("FUTURO", "violet"),
    "forbidden_to_claim": ("PROHIBIDO", "risk"),
}


def _render_brain_map(data: Mapping[str, Any]) -> str:
    """Compact system map; each node declares its honest tier from the contract."""
    surface = data.get("capability_surface_map") or {}
    boundary = data.get("safety_boundary") or {}

    nodes = []
    for label, key, kind in _BRAIN_NODES:
        if kind == "boundary":
            if boundary.get(key):
                tier, tier_label, tone = "forbidden_to_claim", "BOUNDARY ACTIVO", "risk"
            else:
                tier, tier_label, tone = "undeclared", "SIN DECLARAR", "muted"
            source = f"safety_boundary.{key}"
        else:
            tier = next(
                (name for name in _TIER_PRESENTATION if key in (surface.get(name) or [])),
                "",
            )
            if tier:
                tier_label, tone = _TIER_PRESENTATION[tier]
                source = f"capability_surface_map.{tier}"
            else:
                tier, tier_label, tone = "undeclared", "SIN DECLARAR", "muted"
                source = "capability_surface_map"
        nodes.append(
            f'<div class="bnode bnode-{tone}" data-brain-node="{_e(key)}"'
            f' data-node-tier="{_e(tier)}" title="{_e(source)}">'
            f'<span class="bn-name">{_e(label)}</span>'
            f'<span class="bn-tier">{_e(tier_label)}</span>'
            f'<span class="bn-src">{_e(source)}</span></div>'
        )

    return (
        '<div class="card brainmap" data-marker="synapse_brain_map"'
        ' data-nodes="system_capability_nodes">'
        "<h3>SYNAPSE Brain Map - estado real del sistema</h3>"
        '<div class="bmap">' + "".join(nodes) + "</div>"
        '<p class="honesty">Cada nodo declara su tier desde capability_surface_map /'
        " safety_boundary del contrato; sin overclaim.</p></div>"
    )


_STACK_STEPS: tuple[tuple[str, str], ...] = (
    ("product_lab", "Product"),
    ("economics", "Economics"),
    ("shopify_studio", "Shopify"),
    ("marketing_engine", "Marketing"),
    ("safety_claim_guard", "Safety"),
    ("evidence", "Evidence"),
    ("learning_feedback", "Learning"),
)


def _stack_missing_items(data: Mapping[str, Any], module_id: str) -> list[str]:
    """Per-module missing/risk items, straight from the contract sections."""
    if module_id == "product_lab":
        return [
            f"Campo del brief: {field}"
            for field in (data.get("input_richness") or {}).get("missing_fields") or []
        ]
    if module_id == "shopify_studio":
        return list((data.get("shopify_pack") or {}).get("missing_inputs") or [])
    if module_id == "marketing_engine":
        return [
            f"Rewrite pendiente: {entry.get('copy_key', '')}"
            for entry in _medium_risk_entries(data)
        ]
    if module_id == "safety_claim_guard":
        return list((data.get("claim_guard") or {}).get("risky_claims") or [])
    if module_id == "learning_feedback":
        return ["Datos en vivo no conectados (Fase 2)"]
    return []


def _readiness_stack(data: Mapping[str, Any]) -> str:
    modules_by_id = _modules_by_id(data)
    steps = []
    for module_id, label in _STACK_STEPS:
        entry = modules_by_id.get(module_id) or {}
        status = _e(entry.get("status", ""))
        missing = _stack_missing_items(data, module_id)
        missing_html = (
            "<h5 class=\"warn\">Falta / riesgo</h5>" + _ul(missing, "plain warn")
            if missing
            else '<p class="empty">(sin pendientes)</p>'
        )
        next_action = _e(entry.get("operator_action", "")) or "(sin accion pendiente)"
        steps.append(
            f'<div class="stack-step" data-stack-step="{_e(module_id)}"'
            f' data-operator-card="{_e(module_id)}" data-module-status="{status}">'
            f'<div class="stack-rail-line"><span class="stack-dot dot-{status}"></span></div>'
            f'<div class="stack-body"><div class="op-top"><h4>{_e(label)}</h4>'
            f"{_status_chip(entry.get('status', ''))}"
            f'<span class="mod-badge">{_e(entry.get("badge_text", ""))}</span></div>'
            f'<p class="op-summary">{_e(entry.get("summary", ""))}</p>'
            f"{missing_html}"
            f'<p class="op-next"><b>Siguiente:</b> {next_action}</p>'
            f'<span class="a-jump" data-nav-module="{_e(module_id)}">abrir -&gt;</span>'
            f"</div></div>"
        )
    return (
        '<div class="card" data-contract-section="commercial_readiness_stack"'
        ' data-operator-cards="true">'
        "<h3>Commercial Readiness Stack</h3>"
        '<div class="stack">' + "".join(steps) + "</div></div>"
    )


def _render_command_center(
    data: Mapping[str, Any],
    active_module: str,
    candidates: Sequence[Mapping[str, Any]],
    selected_fid: str,
) -> str:
    decision = data.get("decision") or {}
    pipeline = dict(data.get("candidate_pipeline") or {})
    board = dict(data.get("system_health_board") or {})
    queue = data.get("action_queue") or []
    modules = data.get("module_status_summary") or []

    pipeline_fields = {
        key: pipeline.get(key)
        for key in (
            "pipeline_stage",
            "total_candidates",
            "recommended_count",
            "blocked_count",
            "low_input_count",
            "empty_count",
            "current_candidate_id",
            "current_candidate_rank",
            "source",
            "confidence",
            "live_discovery_connected",
        )
    }
    pipeline_block = _card(
        "Candidate Pipeline (solo fixture)",
        _kv(pipeline_fields)
        + f'<p class="honesty">{_e(pipeline.get("pipeline_note", ""))}</p>',
        attrs='data-contract-section="candidate_pipeline"',
    )

    board.pop("source_fields", None)
    board_block = _card(
        "System Health Board",
        _kv(board),
        attrs='data-contract-section="system_health_board"',
    )

    modules_by_id_map = _modules_by_id(data)
    action_rows = []
    for action in queue:
        primary = ' data-primary="true"' if action.get("is_primary") else ""
        tag = '<span class="chip chip-gold">PRIMARIA</span> ' if action.get("is_primary") else ""
        target_module = action.get("target_module", "")
        target_entry = modules_by_id_map.get(target_module) or {}
        target_label = target_entry.get("label", target_module)
        target_status = target_entry.get("status", "")
        unlocks = (
            f"Avanza el modulo {target_label} (estado actual: {target_status})"
        )
        prevents = target_entry.get("summary", "") or "(sin riesgo declarado en el contrato)"
        action_rows.append(
            f'<div class="action-item" data-local-check="action_{_e(action.get("action_id", ""))}"'
            f' data-unlocks="{_e(unlocks)}" data-prevents="{_e(prevents)}"'
            f"{primary}><span class=\"ck\"></span>"
            f'<span class="prio">P{_e(action.get("priority", ""))}</span><div>'
            f'<div class="a-label">{tag}{_e(action.get("label", ""))}</div>'
            f'<div class="a-note"><b>Por que importa:</b> {_e(action.get("reason", ""))}</div>'
            f'<div class="a-note"><b>Que desbloquea:</b> {_e(unlocks)}</div>'
            f'<div class="a-note"><b>Que riesgo evita:</b> {_e(prevents)}</div>'
            f'<div class="a-src">fuente: action_queue + module_status_summary</div></div>'
            f'<span class="a-jump" data-nav-module="{_e(target_module)}">'
            f"{_e(target_module)} -&gt;</span></div>"
        )
    actions_block = _card(
        "Anticipation Playbook (secuencia del operador; checks locales)",
        ("".join(action_rows) or '<p class="empty">(sin acciones)</p>')
        + '<p class="local-note">Checks guardados solo en este navegador (localStorage).'
        " Desbloqueos y riesgos derivados del module_status_summary del contrato.</p>",
        attrs='data-contract-section="action_queue" data-role="anticipation_queue"'
        ' data-marker="anticipation_playbook" data-checklist="persisted_checklist"',
    )

    honesty = (
        '<div class="honesty-banner">Datos de fixture congelado - sin discovery en vivo'
        " - sin analytics - sin escrituras - Fase 1 dry-run</div>"
    )

    brief = _commercial_brief(data)
    snapshot = _selling_pack_snapshot(data)
    stack = _readiness_stack(data)
    selector = _render_selector(candidates, selected_fid)
    export_panel = _selling_packet_panel(data)

    empty_state = ""
    if not (data.get("product") or {}).get("name"):
        empty_state = (
            '<div class="card" data-marker="empty_state_no_product">'
            "<h3>Shortlist vacia</h3>"
            '<p class="disabled">Sin producto en la shortlist: no hay editor, no hay'
            " payloads, no hay paquete de venta. Siguiente accion segura: revisar el"
            " pipeline de candidatos (solo fixture; sin discovery en vivo).</p></div>"
        )

    progress_card = (
        '<div class="card" data-marker="local_progress_summary">'
        "<h3>Progreso local del operador</h3>"
        '<div class="prog-row" data-marker="checklist_progress">'
        '<span class="prog-label">Checklist local</span>'
        '<span class="prog-bar"><i data-checklist-bar></i></span>'
        '<span class="prog-val" data-checklist-progress>0 / 0</span></div>'
        '<div class="prog-row" data-marker="draft_progress">'
        '<span class="prog-label">Drafts editados</span>'
        '<span class="prog-val" data-draft-progress>0 campo(s)</span></div>'
        '<p class="local-note">Progreso guardado solo en este navegador (localStorage);'
        " no es telemetria ni un backend.</p></div>"
    )
    notes_card = (
        '<div class="card" data-marker="operator_notes">'
        "<h3>Notas del operador (memoria local)</h3>"
        + _draft_field(
            "operator_notes",
            "Notas locales",
            "",
            rows=4,
            hint="Solo memoria local del navegador; no se envia a ningun lado.",
        )
        + "</div>"
    )

    return (
        f'<section id="command_center" data-module="command_center"'
        f' class="module{" active" if active_module == "command_center" else ""}"'
        f' data-marker="command_center_hub">'
        f'<div class="mod-head"><h2>Command Center</h2>'
        f'<p class="purpose">Hub del operador: seleccionar candidato, ver que hizo el'
        f" sistema, que falta y exportar el paquete de venta.</p></div>"
        f"{honesty}{selector}{empty_state}{brief}{snapshot}"
        f'<div class="grid g2">{progress_card}{notes_card}</div>'
        f"{export_panel}"
        f"{stack}"
        f'<div class="grid g2">{_card("Decision", _kv({"outcome": decision.get("outcome", ""), "permission_gate": decision.get("permission_gate", ""), "reason": decision.get("reason", "")}))}{pipeline_block}</div>'
        f'<div class="grid g2">{actions_block}{board_block}</div>'
        f"</section>"
    )


def _render_decision_center(data: Mapping[str, Any], active_module: str) -> str:
    decision = data.get("decision") or {}
    scores = data.get("scores") or {}
    richness = data.get("input_richness") or {}

    score_rows = []
    for key, value in scores.items():
        try:
            width = max(0, min(100, int(float(value) * 10)))
        except (TypeError, ValueError):
            width = 0
        score_rows.append(
            f'<div class="score-row"><span class="lbl">{_e(key)}</span>'
            f'<span class="bar"><i style="width:{width}%"></i></span>'
            f'<span class="val">{_e(value)}</span></div>'
        )

    richness_block = _card(
        "Input richness",
        _kv(
            {
                "classification": richness.get("classification", ""),
                "filled": f"{richness.get('filled_count', 0)}/{richness.get('total_fields', 0)}",
                "policy": richness.get("policy", ""),
            }
        )
        + (
            f'<p class="warning">{_e(richness.get("warning"))}</p>'
            if richness.get("warning")
            else ""
        ),
    )

    scores_html = "".join(score_rows) or '<p class="empty">(sin scores)</p>'
    scores_card = _card("Scores del motor", scores_html)
    decision_card = _card(
        "Decision y razones",
        _kv(
            {
                "outcome": decision.get("outcome", ""),
                "permission_gate": decision.get("permission_gate", ""),
                "reason": decision.get("reason", ""),
            }
        )
        + "<h4>Reason codes</h4>"
        + _ul(decision.get("reason_codes") or [])
        + "<h4>Caveats</h4>"
        + _ul(decision.get("caveats") or [], "plain warn"),
    )
    active = " active" if active_module == "decision_center" else ""
    return (
        f'<section id="decision_center" data-module="decision_center" class="module{active}">'
        f'<div class="mod-head"><h2>Decision Center</h2>'
        f'<p class="purpose">Por que el motor decidio esto y donde esta el riesgo.</p></div>'
        f'<div class="grid g2">{scores_card}{decision_card}</div>{richness_block}</section>'
    )


def _render_product_lab(data: Mapping[str, Any], active_module: str) -> str:
    product = data.get("product") or {}
    richness = data.get("input_richness") or {}
    marketing = data.get("marketing_pack") or {}
    queue = data.get("action_queue") or []

    field_chips = "".join(
        f'<span class="chip chip-go">{_e(field)}</span>'
        for field in richness.get("filled_fields") or []
    ) + "".join(
        f'<span class="chip chip-risk">{_e(field)} - falta</span>'
        for field in richness.get("missing_fields") or []
    )

    enrich_rows = [
        f"<li>{_e(action.get('label', ''))}</li>"
        for action in queue
        if action.get("target_module") == "product_lab"
    ]
    enrich_block = (
        f'<div class="warn-strip" data-enrichment-gaps="true"><b>Acciones de enriquecimiento:</b>'
        f'<ul class="plain warn">{"".join(enrich_rows)}</ul></div>'
        if enrich_rows
        else ""
    )

    product_html = _kv(product) if product else (
        '<p class="empty">Sin producto: la shortlist esta vacia.</p>'
    )
    product_card = _card("Producto", product_html)
    provenance_card = _card(
        "Origen de los datos (resumen)",
        '<p class="op-summary">Fixture local congelado, solo lectura. El detalle'
        " tecnico de auditoria (origen, cadena determinista, mapa de capacidades)"
        " vive en el Evidence Drawer.</p>"
        '<button type="button" class="drawer-btn" data-drawer-open>Ver evidencia</button>',
    )
    brief_card = _card(
        "Brief del operador - " + str(richness.get("classification", "")),
        '<div class="field-chips">' + field_chips + "</div>" + enrich_block,
    )
    pains_card = _card("Dolores", _ul(marketing.get("pain_points") or [], "plain risk"))
    desires_card = _card("Deseos", _ul(marketing.get("desire") or [], "plain go"))
    objections_card = _card("Objeciones", _ul(marketing.get("objections") or [], "plain warn"))
    enrichment_card = ""
    if str(richness.get("classification", "")) == "INPUT_LOW":
        enrichment_card = (
            '<div class="card" data-marker="enrichment_workspace">'
            "<h3>Workspace de enriquecimiento</h3>"
            '<p class="warning">Necesita enriquecimiento antes del sell-prep: el brief'
            " esta en INPUT_LOW y el pack actual usa fallbacks genericos, no un pack"
            " completo.</p>"
            + _draft_field(
                "enrichment_notes",
                "Notas de enriquecimiento del operador",
                "",
                rows=4,
                hint="Apunta datos reales del producto y del cliente para completar el"
                " brief; memoria local del navegador, no actualiza el fixture.",
            )
            + "</div>"
        )
    body = (
        f'<div class="grid g2">{product_card}{provenance_card}</div>'
        f"{brief_card}{enrichment_card}"
        f'<div class="grid g3">{pains_card}{desires_card}{objections_card}</div>'
    )

    return (
        f'<section id="product_lab" data-module="product_lab"'
        f' class="module{" active" if active_module == "product_lab" else ""}">'
        f'<div class="mod-head"><h2>Product Lab</h2>'
        f'<p class="purpose">La materia prima del copy: brief, hechos y procedencia.</p></div>'
        f"{body}</section>"
    )


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _economics_verdict(data: Mapping[str, Any]) -> tuple[str, str, str]:
    """PASS / WATCH / FAIL / KILL from contract gate + local floor guardrail."""
    decision = data.get("decision") or {}
    summary = data.get("blocked_queue_summary") or {}
    richness = data.get("input_richness") or {}
    economics = data.get("economics") or {}
    gate = str(decision.get("permission_gate", ""))
    margin = _float_or_none(economics.get("contribution_margin_mxn"))
    pct = _float_or_none(economics.get("contribution_margin_percent"))

    if int(summary.get("blocked_count") or 0) or gate == "BLOCK":
        return "KILL", "risk", "Gate BLOCK del contrato: candidato bloqueado (claims/economia)."
    if margin is None:
        return "SIN DATOS", "muted", "Sin economia de candidato en el fixture."
    if margin <= 0:
        return "FAIL", "risk", "Margen no positivo: no avanzar."
    if pct is not None and pct < MARGIN_FLOOR_PCT:
        return (
            "FAIL",
            "risk",
            f"Margen bajo el piso local de {MARGIN_FLOOR_PCT:.0f}%: no avanzar si margen bajo piso.",
        )
    if str(richness.get("classification", "")) == "INPUT_LOW":
        return "WATCH", "warn", "Economia sobre piso, pero el brief esta en INPUT_LOW."
    if gate == "PASS":
        return "PASS", "go", "Gate PASS del contrato y margen sobre el piso local."
    return "WATCH", "warn", f"Gate {gate}: revisar caveats antes de avanzar."


def _waterfall_row(label: str, amount: float, price: float, tone: str) -> str:
    width = max(2, min(100, int(round(abs(amount) * 100 / price)))) if price else 0
    sign = "-" if tone in ("cost",) else ""
    return (
        f'<div class="wf-row"><span class="wf-label">{_e(label)}</span>'
        f'<span class="wf-track"><i class="wf-bar wf-{_e(tone)}" style="width:{width}%"></i></span>'
        f'<span class="wf-val wf-v-{_e(tone)}">{sign}{_e(_fmt_money(abs(amount)))}</span></div>'
    )


def _render_economics(data: Mapping[str, Any], active_module: str) -> str:
    economics = dict(data.get("economics") or {})
    notes = economics.pop("notes", "")
    price = _float_or_none(economics.get("price_mxn"))
    cost = _float_or_none(economics.get("product_cost_mxn")) or 0.0
    shipping = _float_or_none(economics.get("shipping_cost_mxn")) or 0.0
    fee = _float_or_none(economics.get("payment_fee_mxn")) or 0.0
    margin = _float_or_none(economics.get("contribution_margin_mxn"))
    pct = _float_or_none(economics.get("contribution_margin_percent"))
    breakeven = _float_or_none(economics.get("breakeven_cpa_mxn"))
    verdict, verdict_tone, verdict_reason = _economics_verdict(data)

    gate_legend = "".join(
        f'<span class="gate-chip gate-{tone}{" current" if level == verdict else ""}">{level}</span>'
        for level, tone in (
            ("PASS", "go"),
            ("WATCH", "warn"),
            ("FAIL", "risk"),
            ("KILL", "risk"),
        )
    )
    verdict_card = (
        f'<div class="card verdict-gate" data-marker="verdict_gate">'
        f"<h3>Verdict gate (economia)</h3>"
        f'<div class="gate-legend">{gate_legend}</div>'
        f'<div class="vh-outcome gate-current-{_e(verdict_tone)}">{_e(verdict)}</div>'
        f'<p class="op-summary">{_e(verdict_reason)}</p>'
        '<p class="honesty">Derivado del permission_gate del contrato + guardrails'
        " locales; sin forecast de ventas.</p></div>"
    )

    if price is None or margin is None:
        body = (
            '<div class="card" data-marker="money_cockpit">'
            "<h3>Money Cockpit</h3>"
            '<p class="disabled">Sin economia de candidato: la shortlist esta vacia.'
            " No se inventan numeros.</p></div>" + verdict_card
        )
        return (
            f'<section id="economics" data-module="economics"'
            f' class="module{" active" if active_module == "economics" else ""}">'
            f'<div class="mod-head"><h2>Economics - Money Cockpit</h2>'
            f'<p class="purpose">El dinero por unidad y el CPA breakeven, sin inventos.</p></div>'
            f"{body}</section>"
        )

    reserve = round(price * RISK_RESERVE_RATE, 2)
    buffer = round(margin - reserve, 2)
    floor_mxn = round(price * MARGIN_FLOOR_PCT / 100, 2)

    kpis = "".join(
        (
            _metric("Precio", _fmt_money(price), tone="ink"),
            _metric("Costo producto", _fmt_money(cost), tone="ink"),
            _metric("Envio", _fmt_money(shipping), tone="ink"),
            _metric("Fees", _fmt_money(fee), tone="ink"),
            _metric("Margen bruto", _fmt_money(margin), sub=_fmt_percent(pct), tone="gold"),
            _metric("Breakeven CPA", _fmt_money(breakeven), tone="gold"),
            _metric(
                "Buffer post-reserva",
                _fmt_money(buffer),
                sub=f"reserva teorica {_fmt_money(reserve)} (supuesto local)",
                tone="gold",
            ),
        )
    )
    kpi_card = (
        '<div class="card money-cockpit" data-marker="money_cockpit">'
        "<h3>Money Cockpit - KPI strip (numeros del fixture)</h3>"
        f'<div class="kpi-strip" data-marker="kpi_strip">{kpis}</div>'
        + (f'<p class="honesty">{_e(notes)}</p>' if notes else "")
        + "</div>"
    )

    waterfall_card = (
        '<div class="card" data-marker="margin_waterfall">'
        "<h3>Margin waterfall (por unidad)</h3>"
        + _waterfall_row("Precio", price, price, "price")
        + _waterfall_row("Costo producto", -cost, price, "cost")
        + _waterfall_row("Envio", -shipping, price, "cost")
        + _waterfall_row("Fees", -fee, price, "cost")
        + _waterfall_row("Reserva / riesgo (supuesto local)", -reserve, price, "reserve")
        + _waterfall_row("Contribution margin (motor)", margin, price, "margin")
        + _waterfall_row("Buffer post-reserva (local)", buffer, price, "buffer")
        + '<p class="honesty">Reserva teorica del 10% del precio: supuesto local del'
        " cockpit declarado en el ledger de supuestos; no es salida del motor.</p></div>"
    )

    def scenario(label: str, s_price: float, s_cost: float, s_ship: float, s_fee: float) -> str:
        s_margin = round(s_price - s_cost - s_ship - s_fee, 2)
        s_floor = round(s_price * MARGIN_FLOOR_PCT / 100, 2)
        state = "sobre piso" if s_margin >= s_floor else "BAJO PISO"
        tone = "go" if s_margin >= s_floor else "risk"
        return (
            f'<div class="brief-card scenario-card"><span class="vh-tag">{_e(label)}</span>'
            f'<div class="m-value m-gold">{_e(_fmt_money(s_margin))}</div>'
            f'<span class="m-sub">margen teorico / unidad</span>'
            + _kv(
                {
                    "precio": _fmt_money(s_price),
                    "costo": _fmt_money(s_cost),
                    "envio": _fmt_money(s_ship),
                    "piso local": _fmt_money(s_floor),
                }
            )
            + f'<span class="chip chip-{tone}">{_e(state)}</span></div>'
        )

    scenarios_card = (
        '<div class="card" data-marker="economic_scenarios">'
        "<h3>Escenarios teoricos locales (no forecast de ventas)</h3>"
        '<div class="grid g3">'
        + scenario("Conservative (precio -10%, costos +10%)", round(price * 0.9, 2), round(cost * 1.1, 2), round(shipping * 1.1, 2), fee)
        + scenario("Base (fixture)", price, cost, shipping, fee)
        + scenario("Stretch (precio +5%)", round(price * 1.05, 2), cost, shipping, fee)
        + "</div></div>"
    )

    def sens_row(label: str, new_margin: float) -> str:
        state = "sobre piso" if new_margin >= floor_mxn else "BAJO PISO"
        tone = "go" if new_margin >= floor_mxn else "risk"
        return (
            f"<tr><th>{_e(label)}</th><td>{_e(_fmt_money(new_margin))}</td>"
            f'<td><span class="chip chip-{tone}">{_e(state)}</span></td></tr>'
        )

    cpa_hit = round(margin - (breakeven or 0.0) * 1.15, 2)
    sensitivity_card = (
        '<div class="card" data-marker="sensitivity_grid">'
        "<h3>Sensitivity grid local (margen resultante por unidad)</h3>"
        '<table class="kv"><tr><th>variable</th><td>margen resultante</td><td>vs piso</td></tr>'
        + sens_row("CPA real = breakeven +15%", cpa_hit)
        + sens_row("Precio -10%", round(margin - price * 0.10, 2))
        + sens_row("Costo proveedor +10%", round(margin - cost * 0.10, 2))
        + sens_row("Envio +10%", round(margin - shipping * 0.10, 2))
        + sens_row("Aplicando reserva/fee teorica", buffer)
        + "</table>"
        '<p class="honesty">Calculos locales derivados del fixture; no usan datos de'
        " mercado reales.</p></div>"
    )

    plan = (data.get("marketing_pack") or {}).get("testing_plan_with_thresholds") or {}
    guardrails_card = (
        '<div class="card" data-marker="economics_guardrails">'
        "<h3>Guardrails (locales Fase 1)</h3>"
        + _ul(
            [
                f"Piso minimo de margen: {MARGIN_FLOOR_PCT:.0f}% del precio"
                f" ({_fmt_money(floor_mxn)} por unidad) - guardrail local",
                "Regla: no avanzar si margen bajo piso.",
                "Perdida maxima teorica del primer test: "
                + str(plan.get("first_test_budget_boundary_dry_run_only", "(boundary no definido)")),
            ],
            "plain warn",
        )
        + "</div>"
    )

    shopify = data.get("shopify_pack") or {}
    missing = [str(item) for item in shopify.get("missing_inputs") or []]
    actions: list[str] = []
    if any("stock" in item or "proveedor" in item or "costo" in item for item in missing):
        actions.append("Confirmar costo final y stock con el proveedor antes del primer test.")
    conservative_margin = round(price * 0.9 - cost * 1.1 - shipping * 1.1 - fee, 2)
    if conservative_margin < round(price * 0.9 * MARGIN_FLOOR_PCT / 100, 2):
        actions.append("Renegociar envio/costo o ajustar precio: el escenario conservador cae bajo piso.")
    if pct is not None and pct < MARGIN_FLOOR_PCT:
        actions.append("Mantener en hold: margen bajo el piso local.")
    if not actions:
        actions.append("Mantener precio actual; validar costo real del proveedor antes del primer test.")
    actions_card = _card(
        "Sugerencias de accion (economia)",
        _ul(actions, "plain warn"),
        attrs='data-marker="economics_actions"',
    )

    body = (
        kpi_card
        + f'<div class="grid g2">{waterfall_card}{verdict_card}</div>'
        + scenarios_card
        + f'<div class="grid g2">{sensitivity_card}{guardrails_card}</div>'
        + actions_card
    )
    return (
        f'<section id="economics" data-module="economics"'
        f' class="module{" active" if active_module == "economics" else ""}">'
        f'<div class="mod-head"><h2>Economics - Money Cockpit</h2>'
        f'<p class="purpose">El dinero por unidad, el breakeven y los guardrails;'
        f" sin inventos ni forecast.</p></div>"
        f"{body}</section>"
    )


def _render_shopify_studio(data: Mapping[str, Any], active_module: str) -> str:
    pack = data.get("shopify_pack") or {}
    modules = _modules_by_id(data)
    status = (modules.get("shopify_studio") or {}).get("status", "empty")

    if not pack.get("enabled"):
        body = (
            f'<p class="disabled" data-shopify-disabled="true">Shopify pack deshabilitado: '
            f'{_e(pack.get("disabled_reason", ""))}</p>'
        )
    else:
        blocked = status == "blocked"
        banner = (
            '<div class="blocked-banner">PRODUCTO BLOQUEADO - NO PUBLICAR. '
            "El pack existe solo como registro.</div>"
            if blocked
            else '<div class="honesty-banner" data-no-publish="true"'
            ' data-marker="no_live_publish">'
            "No se publica desde aqui; solo payload copy-ready para que el operador"
            " lo pegue en su tienda.</div>"
        )
        spec_rows = {
            item.get("name", ""): item.get("value", "")
            for item in pack.get("specifications") or []
        }
        faq_rows = [
            f"P: {item.get('q', '')} / R: {item.get('a', '')}" for item in pack.get("faq") or []
        ]
        checklist_rows = "".join(
            f'<div class="action-item" data-local-check="publish_{index}"><span class="ck"></span>'
            f'<div><div class="a-label">{_e(item)}</div></div></div>'
            for index, item in enumerate(pack.get("publish_checklist") or [])
        )
        payloads = _payload_blocks(
            data,
            "shopify_pack",
            suppressed_reason="producto bloqueado; resolver claims antes de copiar" if blocked else "",
            collapsible_keys=("shopify_full_pack",),
        )
        preview_card = ""
        if not blocked:
            preview_bullets = _ul((pack.get("bullets") or [])[:3], "plain go")
            preview_card = (
                '<div class="card listing-preview" data-marker="listing_preview">'
                "<h3>Vista previa del listing (borrador local)</h3>"
                '<div class="lp-frame">'
                '<div class="lp-img" title="Gap declarado en image_checklist del contrato">'
                "Imagen pendiente:<br>fotos reales del proveedor</div>"
                '<div class="lp-body">'
                f'<div class="lp-title">{_e(pack.get("title", ""))}</div>'
                f'<div class="lp-sub">{_e(pack.get("subtitle", ""))}</div>'
                f'<div class="price-block"><span class="price-now">{_e(pack.get("price", ""))}</span>'
                f'<span class="price-compare">{_e(pack.get("compare_at_price", ""))}</span></div>'
                f"{preview_bullets}"
                f'<div class="lp-note">{_e(pack.get("claim_safe_disclaimer", ""))}</div>'
                "</div></div></div>"
            )
        identity_card = _card(
            "Identidad del listing",
            f'<div class="listing-title">{_e(pack.get("title", ""))}</div>'
            f'<div class="listing-subtitle">{_e(pack.get("subtitle", ""))}</div>'
            + _kv({"handle": pack.get("handle", ""), "categoria": pack.get("category", "")}),
        )
        price_card = _card(
            "Precio",
            f'<div class="price-block"><span class="price-now">{_e(pack.get("price", ""))}</span>'
            f'<span class="price-compare">{_e(pack.get("compare_at_price", ""))}</span></div>',
        )
        seo_card = _card(
            "SEO",
            _kv(
                {
                    "seo_title": pack.get("seo_title", ""),
                    "seo_meta_description": pack.get("seo_meta_description", ""),
                }
            )
            + "".join(_chip(tag, "muted") for tag in pack.get("tags") or []),
        )
        if blocked:
            payload_card = _card(
                "Payloads (suprimidos)",
                payloads,
                attrs='data-suppressed-section="shopify_payloads"',
            )
            editor_card = (
                '<div class="warning" data-marker="blocked_editing_disabled">'
                "Edicion local deshabilitada: producto bloqueado, no utilizable hasta"
                " reparar los claims. Solo quedan las acciones de reparar / rechazar y"
                " las notas del operador en Command Center.</div>"
            )
            supplier_block = ""
        else:
            payload_count = _payload_count(data, "shopify_pack")
            payload_card = _card(
                "Payloads copy-ready",
                f'<details class="payload-drawer" data-marker="payload_drawer" open>'
                f"<summary>Cajon de payloads ({payload_count}) - copiar y pegar en la tienda"
                f"</summary>{payloads}</details>",
                attrs='data-contract-section="shopify_payload_copy"',
            )
            editor_card = _card(
                "Editor local del listing (draft del operador)",
                '<p class="honesty">Drafts locales: no modifican el fixture ni el'
                " ViewModel y no recalculan el motor. Se guardan solo en este"
                " navegador.</p>"
                + _draft_field("shopify_title", "Titulo", pack.get("title", ""), kind="input")
                + _draft_field("shopify_subtitle", "Subtitulo", pack.get("subtitle", ""), kind="input")
                + _draft_field(
                    "shopify_price_note",
                    "Nota de precio del operador",
                    "",
                    rows=2,
                    hint=f"Referencia fixture: {pack.get('price', '')} /"
                    f" compare-at {pack.get('compare_at_price', '')}. La nota no recalcula economia.",
                )
                + _draft_field("shopify_bullets", "Bullets (uno por linea)", pack.get("bullets") or [], rows=5)
                + _draft_field(
                    "shopify_short_description", "Descripcion corta", pack.get("short_description", ""), rows=3
                )
                + _draft_field(
                    "shopify_long_description", "Descripcion larga", pack.get("long_description", ""), rows=7
                )
                + _draft_field("shopify_seo_title", "SEO title", pack.get("seo_title", ""), kind="input")
                + _draft_field(
                    "shopify_seo_meta_description",
                    "SEO meta description",
                    pack.get("seo_meta_description", ""),
                    rows=2,
                )
                + _draft_reset_button("shopify_listing"),
                attrs='data-marker="listing_editor" data-editor="local_draft_editor"'
                ' data-drafts="editable_operator_drafts"',
            )
            supplier_block = _card(
                "Mensaje al proveedor (confirmacion de stock / costo)",
                _packet_block(
                    "packet_supplier_sh",
                    "Mensaje listo para copiar",
                    _packet_supplier_text(data),
                    "supplier_confirmation_message",
                ),
            )
        assets_rows = "".join(
            f'<div class="action-item" data-local-check="asset_{index}"><span class="ck"></span>'
            f'<div><div class="a-label">{_e(item)}</div></div></div>'
            for index, item in enumerate(pack.get("image_checklist") or [])
        )
        assets_card = _card(
            "Checklist de assets faltantes (local)",
            (assets_rows or '<p class="empty">(sin gaps declarados)</p>')
            + "<h4>Inputs faltantes</h4>"
            + _ul(pack.get("missing_inputs") or [], "plain risk"),
            attrs='data-marker="missing_assets_checklist"',
        )
        body = (
            banner
            + '<div data-contract-section="shopify_listing_builder">'
            + preview_card
            + '<div class="studio">'
            + "<div>"
            + editor_card
            + f'<div class="grid g2">{identity_card}{price_card}</div>'
            + seo_card
            + _card("Bullets", _ul(pack.get("bullets") or []))
            + _card("Beneficios / Especificaciones", _ul(pack.get("benefits") or [], "plain go") + _kv(spec_rows))
            + _card("FAQ", _ul(faq_rows))
            + assets_card
            + _card(
                "Checklist de publicacion (local, no publica nada)",
                checklist_rows or '<p class="empty">(vacio)</p>',
                attrs='data-marker="publish_readiness_checklist"',
            )
            + supplier_block
            + payload_card
            + "</div>"
            + f'<aside class="guard-rail">{_claim_guard_card(pack.get("claim_guard_notes") or {}, "shopify_pack")}</aside>'
            + "</div></div>"
        )

    module_entry = modules.get("shopify_studio") or {}
    badge = _e(module_entry.get("badge_text", ""))
    return (
        f'<section id="shopify_studio" data-module="shopify_studio"'
        f' class="module{" active" if active_module == "shopify_studio" else ""}"'
        f' data-module-status="{_e(status)}" data-marker="premium_shopify_builder"'
        f' data-functional="functional_shopify_studio">'
        f'<div class="mod-head"><h2>Shopify Studio {_status_chip(status)}'
        f' <span class="mod-badge">{badge}</span></h2>'
        f'<p class="purpose">Pack copy-ready para armar la ficha; nada se publica desde aqui.</p></div>'
        f"{body}</section>"
    )


def _render_first_test_panel(data: Mapping[str, Any], blocked: bool) -> str:
    """Operator tool: risk-adjusted first angle + manual test plan.

    Everything comes from existing pack fields (angle_matrix,
    creative_hypotheses, claim_risk_by_copy, testing plans). No analytics,
    no efficacy claims, no invented performance data.
    """
    pack = data["marketing_pack"]
    honesty = (
        '<div class="honesty-banner" data-marker="no_fake_performance_claims">'
        "Sin datos de rendimiento reales - nada aqui es un claim de eficacia o"
        " ventas - plan de prueba manual del operador</div>"
    )
    if blocked:
        return (
            '<div class="lab-panel active" data-lab-panel id="lab_firsttest">'
            + honesty
            + '<div class="blocked-banner">Sin plan de primer test: el producto esta'
            " bloqueado por claims prohibidos. Reparar o rechazar primero.</div></div>"
        )

    angles = pack.get("angle_matrix") or []
    best = (
        min(
            angles,
            key=lambda angle: _RISK_RANK.get(str(angle.get("claim_risk", "")).lower(), 99),
        )
        if angles
        else None
    )
    if best:
        best_id = best.get("angle_id", "")
        linked = [
            hyp
            for hyp in pack.get("creative_hypotheses") or []
            if hyp.get("linked_angle_id") == best_id
        ] or list(pack.get("creative_hypotheses") or [])
        angle_card = _card(
            "Primer angulo ajustado por riesgo (risk-adjusted first angle)",
            f'<div class="vh-outcome">[{_e(best_id)}] {_e(best.get("angle_name", ""))}</div>'
            + _kv(
                {
                    "riesgo de claims": best.get("claim_risk", ""),
                    "promesa": best.get("promise_type", ""),
                    "segmento": best.get("target_segment", ""),
                    "redaccion segura": best.get("safe_wording", ""),
                }
            )
            + '<h4 class="ok">Por que este angulo primero</h4>'
            + '<p class="op-summary">Menor riesgo de claims dentro de la matriz de'
            f' angulos del contrato. {_e(best.get("why_it_might_work", ""))}</p>'
            + f'<div class="a-fail">Puede fallar: {_e(best.get("why_it_might_fail", ""))}</div>',
            attrs='data-marker="recommended_first_angle"',
        )
        signal_items = [
            f"[{hyp.get('hypothesis_id', '')}] {hyp.get('expected_signal', '')}"
            for hyp in linked
            if hyp.get("expected_signal")
        ]
        failure_items = [
            f"[{hyp.get('hypothesis_id', '')}] {hyp.get('failure_signal', '')}"
            for hyp in linked
            if hyp.get("failure_signal")
        ]
        evidence_items = [
            f"[{hyp.get('hypothesis_id', '')}] {hyp.get('minimum_evidence_needed', '')}"
            for hyp in linked
            if hyp.get("minimum_evidence_needed")
        ]
        signals_card = _card(
            "Que contaria como senal (evidence needed)",
            '<h4 class="ok">Senal esperada (expected signal)</h4>'
            + _ul(signal_items, "plain go")
            + '<h4 class="no">Senal de falla (failure signal) - que mataria el angulo</h4>'
            + _ul(failure_items, "plain risk")
            + "<h4>Evidencia minima necesaria</h4>"
            + _ul(evidence_items, "plain warn"),
            attrs='data-signals="expected_signal failure_signal"',
        )
    else:
        angle_card = _card(
            "Primer angulo ajustado por riesgo",
            '<p class="empty">(sin angulos definidos en el contrato)</p>',
            attrs='data-marker="recommended_first_angle"',
        )
        signals_card = _card(
            "Que contaria como senal",
            '<p class="empty">(sin hipotesis definidas)</p>',
            attrs='data-signals="expected_signal failure_signal"',
        )

    risk_entries = list(pack.get("claim_risk_by_copy") or [])
    ordered = sorted(
        enumerate(risk_entries),
        key=lambda pair: (
            _RISK_RANK.get(str(pair[1].get("risk_level", "")).lower(), 99),
            pair[0],
        ),
    )
    priority_items = []
    for position, (_original_index, entry) in enumerate(ordered, start=1):
        level = str(entry.get("risk_level", "")).lower()
        if level == "low":
            note = "usable ya (riesgo bajo)"
        elif level == "prohibited":
            note = "NO USAR: prohibido; requiere reposicionamiento"
        else:
            note = "usar solo la version claim-safe (rewrite)"
        priority_items.append(f"{position}. {entry.get('copy_key', '')} - {note}")
    priority_card = _card(
        "Orden de prioridad del copy (riesgo primero)",
        _ul(priority_items)
        + '<p class="honesty">Orden derivado de claim_risk_by_copy del contrato;'
        " no es una prediccion de rendimiento.</p>",
        attrs='data-marker="copy_priority_order"',
    )

    rewrites = [
        entry
        for entry in risk_entries
        if entry.get("safe_rewrite")
        and str(entry.get("risk_level", "")).lower() not in ("low", "")
    ]
    rewrite_rows = "".join(
        f'<div class="risk-note" data-rewrite-surface="{_e(entry.get("copy_key", ""))}">'
        f'<span class="risk-tag">{_e(entry.get("copy_key", ""))}'
        f' ({_e(entry.get("risk_level", ""))})</span> {_e(entry.get("reason", ""))}'
        f'<br><span class="safe">Version claim-safe: {_e(entry.get("safe_rewrite", ""))}</span></div>'
        for entry in rewrites
    )
    rewrite_card = _card(
        f"Cola de rewrites ({len(rewrites)})",
        (rewrite_rows or '<p class="empty">(sin rewrites pendientes)</p>')
        + '<div data-marker="claim_safe_version"></div>',
        attrs='data-marker="rewrite_queue"',
    )

    plan_v1 = pack.get("testing_plan") or {}
    plan_v2 = pack.get("testing_plan_with_thresholds") or {}
    test_plan_card = _card(
        "Plan de prueba manual (primer test del operador)",
        f'<div class="budget-banner">{_e(plan_v2.get("first_test_budget_boundary_dry_run_only", ""))}</div>'
        + _kv(
            {
                "fase 1": plan_v1.get("phase_1", ""),
                "fase 2": plan_v1.get("phase_2", ""),
                "presupuesto": plan_v1.get("budget_note", ""),
            }
        )
        + '<h4 class="ok">Continuar si</h4>'
        + _ul(plan_v2.get("continue_if") or [], "plain go")
        + '<h4 class="warn">Revisar si</h4>'
        + _ul(plan_v2.get("review_if") or [], "plain warn")
        + '<h4 class="no">Matar si</h4>'
        + _ul(plan_v2.get("kill_if") or [], "plain risk"),
        attrs='data-marker="manual_test_plan"',
    )
    no_conclude_card = _card(
        "No concluir (anti-overclaim)",
        _ul(plan_v2.get("what_not_to_conclude") or [], "plain risk"),
    )
    observation_card = _card(
        "Observaciones manuales del operador",
        _draft_field(
            "marketing_observation_notes",
            "Observacion del operador (manual, local)",
            "",
            rows=4,
            hint="Registro local de lo observado en el test manual; no es analytics"
            " y no genera conclusiones automaticas.",
        ),
        attrs='data-marker="manual_observation_notes"',
    )
    packets = _card(
        "Paquetes de copy para ejecutar a mano",
        _packet_block(
            "packet_marketing_mk",
            "Marketing packet",
            _packet_marketing_text(data),
            "marketing_packet",
        )
        + _packet_block(
            "packet_claimsafe_mk",
            "Claim-safe copy packet",
            _packet_claim_safe_text(data),
            "claim_safe_copy_packet",
        ),
    )
    return (
        '<div class="lab-panel active" data-lab-panel id="lab_firsttest">'
        + honesty
        + '<div class="grid g2">'
        + angle_card
        + test_plan_card
        + "</div><div class=\"grid g2\">"
        + priority_card
        + signals_card
        + "</div>"
        + rewrite_card
        + no_conclude_card
        + observation_card
        + packets
        + "</div>"
    )


def _commercial_copy_support(pack: Mapping[str, Any]) -> str:
    """Non-technical copy support summary for the Marketing main stage (R5).

    Says which facts back the strategy, which copy is data-backed vs generic,
    and what is missing before trusting the copy — in operator language, no
    source paths or raw field names. The technical input_support_map card
    renders only inside the Evidence/Audit Drawer."""
    entries = list(pack.get("input_support_map") or [])
    supported = [entry for entry in entries if entry.get("supported")]
    generic = [entry for entry in entries if not entry.get("supported")]

    facts: list[str] = []
    operator_material = False
    for entry in supported:
        for path in entry.get("support_fields") or []:
            section, _, field_name = str(path).partition(".")
            if section == "operator_input":
                label = _fact_label(field_name)
                if label not in facts:
                    facts.append(label)
            else:
                operator_material = True
    if operator_material:
        facts.append("Material de copy ya aportado por el operador en el brief")

    backed = [_surface_label(str(entry.get("output_key", ""))) for entry in supported]
    caution = [
        _surface_label(str(entry.get("output_key", "")))
        + " - redaccion generica, no usar como claim"
        for entry in generic
    ]

    missing: list[str] = []
    for path in pack.get("missing_marketing_inputs") or []:
        section, _, field_name = str(path).partition(".")
        if section == "operator_input":
            missing.append(f"Completar en el brief: {_fact_label(field_name).lower()}")
        else:
            missing.append(f"Material base pendiente: {_surface_label(field_name).lower()}")

    return _card(
        "Soporte comercial del copy",
        '<h4 class="ok">Que facts soportan esta estrategia</h4>'
        + _ul(facts, "plain go")
        + '<h4 class="ok">Copy respaldado por datos del producto</h4>'
        + _ul(backed, "plain go")
        + '<h4 class="warn">Copy generico - usar con cautela</h4>'
        + _ul(caution, "plain warn")
        + '<h4 class="warn">Que inputs faltan antes de confiar en el copy</h4>'
        + _ul(missing, "plain warn")
        + '<p class="honesty">Resumen comercial para decidir; la trazabilidad'
        " tecnica completa vive en el Evidence Drawer (Ver evidencia).</p>",
        attrs='data-marker="commercial_copy_support"',
    )


def _render_marketing_engine(data: Mapping[str, Any], active_module: str) -> str:
    pack = data.get("marketing_pack") or {}
    modules = _modules_by_id(data)
    status = (modules.get("marketing_engine") or {}).get("status", "empty")

    if not pack.get("enabled"):
        body = (
            f'<p class="disabled" data-marketing-disabled="true">Marketing pack deshabilitado: '
            f'{_e(pack.get("disabled_reason", ""))}</p>'
        )
        return (
            f'<section id="marketing_engine" data-module="marketing_engine"'
            f' class="module{" active" if active_module == "marketing_engine" else ""}">'
            f'<div class="mod-head"><h2>Marketing Engine</h2></div>{body}</section>'
        )

    blocked = status == "blocked"
    suppressed = "copy bloqueado por claims prohibidos" if blocked else ""
    banner = (
        '<div class="blocked-banner">COPY BLOQUEADO POR CLAIMS PROHIBIDOS. '
        "Ningun angulo es utilizable sin reposicionamiento.</div>"
        if blocked
        else ""
    )
    warning = (
        f'<p class="warning">{_e(pack.get("input_richness_warning"))}</p>'
        if pack.get("input_richness_warning")
        else ""
    )

    rewrites = _medium_risk_entries(data)
    rewrites_card = ""
    if rewrites and not blocked:
        rewrite_rows = "".join(
            f'<div class="risk-note" data-rewrite-surface="{_e(entry.get("copy_key", ""))}">'
            f'<span class="risk-tag">{_e(entry.get("copy_key", ""))}</span>'
            f' - terminos: {_e(", ".join(entry.get("risky_terms") or []) or "(ninguno)")}'
            f"<br>{_e(entry.get('reason', ''))}"
            f'<br><span class="safe">Rewrite seguro: {_e(entry.get("safe_rewrite", ""))}</span></div>'
            for entry in rewrites
        )
        rewrites_card = _card(
            f"Rewrites pendientes antes de publicar ({len(rewrites)})",
            rewrite_rows,
            attrs='data-rewrites-pending="true" data-marker="rewrites_pending"',
        )

    tabs_nav = "".join(
        f'<span class="lab-tab{" active" if tab_id == LAB_TABS[0][0] else ""}"'
        f' data-lab-tab="{tab_id}">{_e(label)}</span>'
        for tab_id, label in LAB_TABS
    )
    first_test_panel = _render_first_test_panel(data, blocked)

    confidence_pills = "".join(
        f'<span class="conf-pill">{_e(section)}: <b>{_e(entry.get("level", ""))}</b>'
        f" ({_e(entry.get('basis', ''))})</span>"
        for section, entry in (pack.get("confidence_by_section") or {}).items()
    )
    strategy_panel = (
        f'<div class="lab-panel" data-lab-panel id="lab_strategy">'
        + _card(
            "Estrategia",
            _kv(
                {
                    "core_angle": pack.get("core_angle", ""),
                    "strategy_summary": pack.get("strategy_summary", ""),
                    "why_this_angle": pack.get("why_this_angle", ""),
                    "buyer_profile": pack.get("buyer_profile", ""),
                }
            ),
            attrs='data-marker="strategy_snapshot"',
        )
        + _card("Confianza por seccion", f'<div class="conf-strip">{confidence_pills}</div>')
        + _commercial_copy_support(pack)
        + "</div>"
    )

    ranked_angles = sorted(
        enumerate(pack.get("angle_matrix") or []),
        key=lambda pair: (
            _RISK_RANK.get(str(pair[1].get("claim_risk", "")).lower(), 99),
            pair[0],
        ),
    )
    angle_cards = []
    for priority, (_original_index, angle) in enumerate(ranked_angles, start=1):
        risk = str(angle.get("claim_risk", "")).lower()
        angle_score = max(1, 10 - 3 * _RISK_RANK.get(risk, 3))
        angle_id = _e(angle.get("angle_id", ""))
        use_button = (
            f'<button type="button" class="reset-btn use-angle-btn"'
            f' data-select-angle="{angle_id}">Usar este angulo (local)</button>'
            if not blocked
            else ""
        )
        angle_cards.append(
            f'<div class="angle-card" data-angle-card="{angle_id}">'
            f'<div class="a-top"><b>[{angle_id}]'
            f' {_e(angle.get("angle_name", ""))}</b>'
            f'<span class="angle-meta"><span class="chip chip-gold">P{priority}</span>'
            f'<span class="chip chip-steel" title="Heuristica local riesgo-ajustada;'
            f' no es prediccion de rendimiento">score {angle_score}/10</span>'
            f'<span class="chip chip-warn">riesgo {_e(angle.get("claim_risk", ""))}</span>'
            f'<span class="chip chip-gold angle-chosen" data-angle-chosen hidden>'
            f"ANGULO ELEGIDO (LOCAL)</span></span></div>"
            + _kv(
                {
                    key: angle.get(key, "")
                    for key in (
                        "promise_type",
                        "target_segment",
                        "pain_addressed",
                        "desire_addressed",
                        "objection_addressed",
                        "proof_needed",
                        "safe_wording",
                    )
                }
            )
            + f'<div class="a-why">Puede funcionar: {_e(angle.get("why_it_might_work", ""))}</div>'
            + f'<div class="a-fail">Puede fallar: {_e(angle.get("why_it_might_fail", ""))}</div>'
            + use_button
            + "</div>"
        )
    hypothesis_cards = []
    for hyp in pack.get("creative_hypotheses") or []:
        hypothesis_cards.append(
            f'<div class="hyp-card"><b>[{_e(hyp.get("hypothesis_id", ""))}]'
            f' {_e(hyp.get("hypothesis", ""))}</b>'
            + _kv(
                {
                    key: hyp.get(key, "")
                    for key in (
                        "variable_tested",
                        "expected_signal",
                        "failure_signal",
                        "minimum_evidence_needed",
                        "channel",
                        "linked_angle_id",
                    )
                }
            )
            + "</div>"
        )
    angles_panel = (
        '<div class="lab-panel" data-lab-panel id="lab_angles" data-marker="angle_cards">'
        + _card(
            "Angle Board (prioridad riesgo-ajustada, heuristica local)",
            ("".join(angle_cards) or '<p class="empty">(sin angulos definidos)</p>')
            + '<p class="local-note">El angulo elegido se guarda solo en este'
            " navegador; no reordena el motor.</p>",
            attrs='data-marker="angle_board"',
        )
        + _card("Hipotesis creativas", "".join(hypothesis_cards) or '<p class="empty">(sin hipotesis definidas)</p>')
        + "</div>"
    )

    def _surface_state_chip(copy_key: str) -> str:
        for entry in pack.get("claim_risk_by_copy") or []:
            if entry.get("copy_key") == copy_key:
                level = str(entry.get("risk_level", "")).lower()
                if level == "low":
                    return '<span class="chip chip-go">claim-safe</span>'
                if level == "prohibited":
                    return '<span class="chip chip-risk">blocked</span>'
                return '<span class="chip chip-warn">needs rewrite</span>'
        return '<span class="chip chip-muted">sin analisis</span>'

    hook_rows = "".join(
        f'<div class="hook-row"><span class="prio">H{index}</span>'
        f'<span class="hook-text">{_e(hook)}</span>'
        f"{_surface_state_chip('hooks')}</div>"
        for index, hook in enumerate(pack.get("hooks") or [], start=1)
    )
    hooks_panel = (
        '<div class="lab-panel" data-lab-panel id="lab_hooks" data-marker="hooks_bank">'
        + _card(
            "Hook Console (prioridad = orden del pack; estado por superficie)",
            (hook_rows or '<p class="empty">(sin hooks)</p>') + _risk_chip_for(data, "hooks"),
            attrs='data-marker="hook_console"',
        )
        + _card("Headlines", _ul(pack.get("headlines") or []) + _risk_chip_for(data, "headlines"))
        + "</div>"
    )

    adcopy_payloads = _payload_blocks(
        data,
        "marketing_pack",
        suppressed_reason=suppressed,
        collapsible_keys=("marketing_full_pack", "marketing_full_pack_v2"),
    )
    if blocked:
        adcopy_payload_card = _card(
            "Payloads (suprimidos)",
            adcopy_payloads,
            attrs='data-suppressed-section="marketing_payloads"',
        )
    else:
        adcopy_payload_card = _card(
            "Payloads copy-ready",
            f'<details class="payload-drawer" data-marker="payload_drawer" open>'
            f"<summary>Cajon de payloads ({_payload_count(data, 'marketing_pack')})"
            f" - copiar y pegar</summary>{adcopy_payloads}</details>",
            attrs='data-contract-section="marketing_payload_copy"',
        )
    if blocked:
        adcopy_editor_card = (
            '<div class="warning" data-marker="blocked_editing_disabled">'
            "Edicion local de copy deshabilitada: producto bloqueado por claims"
            " prohibidos; no utilizable hasta reparar.</div>"
        )
    else:
        adcopy_editor_card = _card(
            "Consola de edicion local (drafts del operador, un item por linea)",
            '<p class="honesty">Drafts locales del navegador; no modifican el pack'
            " del sistema ni pasan por Claim Guard: valida contra la columna de"
            " Claim Guard antes de usar.</p>"
            + _draft_field("marketing_hooks", "Hooks", pack.get("hooks") or [], rows=5)
            + _draft_field("marketing_headlines", "Headlines", pack.get("headlines") or [], rows=3)
            + _draft_field(
                "marketing_primary_texts", "Textos primarios", pack.get("primary_texts") or [], rows=5
            )
            + _draft_field("marketing_short_ads", "Anuncios cortos", pack.get("short_ads") or [], rows=3)
            + _draft_field("marketing_long_ads", "Anuncios largos", pack.get("long_ads") or [], rows=5)
            + _draft_field("marketing_captions", "Captions", pack.get("captions") or [], rows=3)
            + _draft_reset_button("marketing_copy"),
            attrs='data-editor="local_draft_editor" data-drafts="editable_operator_drafts"',
        )
    adcopy_panel = (
        '<div class="lab-panel" data-lab-panel id="lab_adcopy" data-marker="ad_copy_console">'
        + '<div class="studio"><div>'
        + adcopy_editor_card
        + _card("Textos primarios", _ul(pack.get("primary_texts") or []) + _risk_chip_for(data, "primary_texts"))
        + _card("Anuncios cortos", _ul(pack.get("short_ads") or []) + _risk_chip_for(data, "short_ads"))
        + _card("Anuncios largos", _ul(pack.get("long_ads") or []) + _risk_chip_for(data, "long_ads"))
        + _card("Captions", _ul(pack.get("captions") or []))
        + adcopy_payload_card
        + "</div>"
        + f'<aside class="guard-rail">{_claim_guard_card(pack.get("claim_guard") or {}, "marketing_pack")}</aside>'
        + "</div></div>"
    )

    channel_rows = [
        f"{item.get('channel', '')} | objetivo: {item.get('objective', '')} | {item.get('notes', '')}"
        for item in pack.get("channel_packs") or []
    ]
    channels_panel = (
        '<div class="lab-panel" data-lab-panel id="lab_channels" data-marker="channel_script_pack">'
        + _card("Channel packs", _ul(channel_rows))
        + _card("Guiones UGC", _ul(pack.get("ugc_scripts") or []))
        + _card("Guiones de video", _ul(pack.get("video_scripts") or []))
        + _card("Conceptos de imagen", _ul(pack.get("image_ad_concepts") or []))
        + "</div>"
    )

    plan = pack.get("testing_plan_with_thresholds") or {}
    testplan_panel = (
        '<div class="lab-panel" data-lab-panel id="lab_testplan"'
        ' data-contract-section="testing_plan_with_thresholds">'
        + f'<div class="budget-banner">{_e(plan.get("first_test_budget_boundary_dry_run_only", ""))}</div>'
        + '<div class="grid g3">'
        + _card("Continuar si", _ul(plan.get("continue_if") or [], "plain go"))
        + _card("Revisar si", _ul(plan.get("review_if") or [], "plain warn"))
        + _card("Matar si", _ul(plan.get("kill_if") or [], "plain risk"))
        + "</div><div class=\"grid g2\">"
        + _card(
            "Senales",
            "<h4>Exito</h4>" + _ul(plan.get("success_signals") or [], "plain go")
            + "<h4>Advertencia</h4>" + _ul(plan.get("warning_signals") or [], "plain warn")
            + "<h4>Alto</h4>" + _ul(plan.get("stop_signals") or [], "plain risk"),
        )
        + _card("No concluir (anti-overclaim)", _ul(plan.get("what_not_to_conclude") or [], "plain risk"))
        + "</div></div>"
    )

    learning = data.get("learning_plan") or {}
    learning_panel = (
        '<div class="lab-panel" data-lab-panel id="lab_learning">'
        + '<div class="future-box"><span class="fb-tag">FUTURO - DATOS EN VIVO NO CONECTADOS</span>'
        "<p>Este panel definira observaciones del operador cuando existan datos reales (Fase 2)."
        " Hoy no hay analytics, no hay fetch de datos, no hay conclusiones.</p></div>"
        + _card("Hipotesis", _ul(learning.get("hypotheses") or []))
        + _card("Evidencia necesaria", _ul(learning.get("evidence_needed") or [], "plain warn"))
        + "</div>"
    )

    no_spend_banner = (
        '<div class="boundary-banner" data-marker="no_spend_boundary"'
        ' title="Boundary Fase 1: el plan es preparacion; la ejecucion es del operador">'
        "SIN GASTO - SIN PUBLICACION EN META - plan preparado para ejecucion manual"
        " del operador</div>"
    )

    return (
        f'<section id="marketing_engine" data-module="marketing_engine"'
        f' class="module{" active" if active_module == "marketing_engine" else ""}"'
        f' data-module-status="{_e(status)}" data-role="marketing_war_room"'
        f' data-marker="premium_marketing_war_room"'
        f' data-functional="functional_marketing_engine">'
        f'<div class="mod-head"><h2>Marketing Engine</h2>'
        f'<p class="purpose">Herramienta del operador: primer test manual, estrategia,'
        f" angulos, copy editable y umbrales de prueba.</p></div>"
        f"{banner}{no_spend_banner}{warning}{rewrites_card}"
        f'<div class="lab-nav">{tabs_nav}</div>'
        f"{first_test_panel}{strategy_panel}{angles_panel}{hooks_panel}{adcopy_panel}{channels_panel}"
        f"{testplan_panel}{learning_panel}</section>"
    )


def _render_safety(data: Mapping[str, Any], active_module: str) -> str:
    guard = data.get("claim_guard") or {}
    board = data.get("system_health_board") or {}
    modules = _modules_by_id(data)
    status = (modules.get("safety_claim_guard") or {}).get("status", "pass")

    risk_rows = "".join(
        f'<div class="mod-row"><span>{_e(entry.get("copy_key", ""))}</span>'
        f'{_status_chip("blocked" if entry.get("risk_level") == "prohibited" else ("warning" if entry.get("risk_level") in ("medium", "review") else "pass"))}'
        f'<span class="mod-badge">{_e(entry.get("risk_level", ""))}</span></div>'
        for entry in data["marketing_pack"].get("claim_risk_by_copy") or []
    )
    boundary_chips = "".join(
        _chip(key, "go" if value else "risk")
        for key, value in (data.get("safety_boundary") or {}).items()
    )
    guard_notes = {
        "allowed_claims": guard.get("allowed_claims") or [],
        "risky_claims": guard.get("risky_claims") or [],
        "prohibited_claims": guard.get("prohibited_claims") or [],
        "safe_wording": guard.get("safe_wording") or [],
        "summary": guard.get("claim_guard_summary", ""),
    }
    risk_card = _card(
        "Riesgo por superficie de copy",
        risk_rows or '<p class="empty">(sin analisis)</p>',
    )
    guard_state_card = _card(
        "Estado del guard",
        _kv(
            {
                "claim_guard_status": board.get("claim_guard_status", ""),
                "estado_modulo": status,
            }
        ),
    )
    boundary_card = _card(
        "Safety boundary Fase 1",
        '<div class="field-chips">' + boundary_chips + "</div>",
    )
    active = " active" if active_module == "safety_claim_guard" else ""
    return (
        f'<section id="safety_claim_guard" data-module="safety_claim_guard"'
        f' class="module{active}" data-module-status="{_e(status)}">'
        f'<div class="mod-head"><h2>Safety / Claim Guard</h2>'
        f'<p class="purpose">Que se puede decir, que no, y el estado del boundary.</p></div>'
        f'<div class="grid g2">{_claim_guard_card(guard_notes, "safety_module")}{risk_card}</div>'
        f"{guard_state_card}{boundary_card}</section>"
    )


def _source_fields_ledger(data: Mapping[str, Any]) -> str:
    """Every source_fields declaration from the contract, in one drawer card."""
    rows: dict[str, Any] = {}
    for entry in data.get("module_status_summary") or []:
        fields = ", ".join(entry.get("source_fields") or [])
        if fields:
            rows[str(entry.get("module_id", ""))] = fields
    for section in ("candidate_pipeline", "system_health_board", "blocked_queue_summary"):
        fields = ", ".join((data.get(section) or {}).get("source_fields") or [])
        if fields:
            rows[section] = fields
    return _card(
        "Source fields ledger (source_fields por seccion del contrato)",
        _kv(rows),
        attrs='data-audit="source_fields"',
    )


def _assumptions_ledger(data: Mapping[str, Any]) -> str:
    economics = data.get("economics") or {}
    pipeline = data.get("candidate_pipeline") or {}
    richness = data.get("input_richness") or {}
    items = [
        f"Reserva teorica de riesgo: {RISK_RESERVE_RATE:.0%} del precio"
        " (supuesto local del Money Cockpit; no es salida del motor).",
        f"Piso minimo de margen: {MARGIN_FLOOR_PCT:.0f}% del precio"
        " (guardrail local Fase 1).",
        "Escenarios y sensitivity grid: calculos locales derivados del fixture;"
        " no son forecast de ventas ni datos de mercado.",
        "Score de prioridad de angulos: heuristica local riesgo-ajustada,"
        " derivada del claim_risk del contrato.",
    ]
    if economics.get("notes"):
        items.append(f"Economia: {economics.get('notes')}")
    if pipeline.get("pipeline_note"):
        items.append(f"Pipeline: {pipeline.get('pipeline_note')}")
    if richness.get("policy"):
        items.append(f"Politica de brief: {richness.get('policy')}")
    return _card(
        "Assumptions ledger (supuestos locales declarados)",
        _ul(items, "plain warn"),
        attrs='data-audit="assumptions_ledger"',
    )


def _score_explanation(data: Mapping[str, Any]) -> str:
    scores = data.get("scores") or {}
    decision = data.get("decision") or {}
    return _card(
        "Score explanation (sin recalculo)",
        _kv(scores)
        + "<h4>Reason codes</h4>"
        + "".join(_chip(code, "muted") for code in decision.get("reason_codes") or [])
        + '<p class="honesty">Scores y umbral tal como vienen del contrato; el'
        " renderer no recalcula ni repondera nada.</p>",
        attrs='data-audit="score_explanation"',
    )


def _input_support_audit(data: Mapping[str, Any]) -> str:
    """Technical input support map (output keys + source paths); drawer-only
    per R5 evidence separation. The main stage shows only the commercial
    summary (_commercial_copy_support)."""
    pack = data.get("marketing_pack") or {}
    support_rows = [
        f"{entry.get('output_key', '')} <- "
        + (", ".join(entry.get("support_fields") or []) or "(sin soporte)")
        + ("" if entry.get("supported") else " [NO SOPORTADO: fallback generico]")
        for entry in pack.get("input_support_map") or []
    ]
    return _card(
        "Mapa de soporte de inputs (nada inventado)",
        _ul(support_rows)
        + "<h4>Inputs faltantes</h4>"
        + _ul(pack.get("missing_marketing_inputs") or [], "plain warn"),
        attrs='data-contract-section="input_support_map"',
    )


def _render_evidence_drawer(data: Mapping[str, Any]) -> str:
    """Right-side Evidence/Audit drawer, closed by default. All technical
    audit surfaces live here, out of the main stage."""
    provenance = data.get("provenance") or {}
    evidence = data.get("evidence") or {}
    surface = data.get("capability_surface_map") or {}
    tier_blocks = "".join(
        f'<h4 data-capability-tier="{_e(tier)}">{_e(tier)}</h4>' + _ul(surface.get(tier) or [])
        for tier in ("real_now", "fixture_only", "future_or_not_connected", "forbidden_to_claim")
    )
    boundary_chips = "".join(
        _chip(key, "go" if value else "risk")
        for key, value in (data.get("safety_boundary") or {}).items()
    )
    provenance_card = _card(
        "Provenance (caja negra)",
        _kv(provenance),
        attrs='data-contract-section="provenance"',
    )
    boundary_card = _card(
        "Safety boundary Fase 1",
        '<div class="field-chips">' + boundary_chips + "</div>",
        attrs='data-contract-section="safety_boundary"',
    )
    base_head = str(provenance.get("base_head", ""))
    chain_steps = (
        (
            "Fixture congelado",
            f"{provenance.get('source_fixture', '')} - base_head {base_head[:12]}",
        ),
        (
            "ViewModel determinista",
            f"schema {data.get('schema_version', '')} - {provenance.get('adapter_status', '')}",
        ),
        ("Renderer visual", VISUAL_VERSION),
        (
            "HTML estatico offline",
            "sin red de runtime - sin reloj de runtime - mismo fixture, mismo output",
        ),
    )
    chain = (
        '<div class="card" data-marker="evidence_chain">'
        "<h3>Cadena de evidencia (determinista)</h3>"
        '<div class="evidence-chain">'
        + "".join(
            f'<div class="chain-step"><span class="cs-n">{index:02d}</span>'
            f"<div><b>{_e(title)}</b>"
            f'<span class="cs-d">{_e(detail)}</span></div></div>'
            for index, (title, detail) in enumerate(chain_steps, start=1)
        )
        + "</div></div>"
    )
    return (
        "<!--EVIDENCE_DRAWER_START-->"
        '<aside class="evidence-drawer" data-evidence-drawer hidden'
        ' data-role="evidence_black_box" data-marker="premium_evidence_black_box">'
        '<div class="drawer-head"><span>Evidence / Audit Drawer</span>'
        '<button type="button" class="link-btn" data-drawer-close>Cerrar</button></div>'
        '<div class="drawer-body">'
        '<div class="honesty-banner" data-principle="operator_in_control"'
        ' data-determinism="deterministic_renderer" data-network="no_runtime_network">'
        "Render determinista - sin reloj de runtime - sin red de runtime"
        " - fixture congelado - operador-en-control</div>"
        + chain
        + provenance_card
        + _source_fields_ledger(data)
        + _score_explanation(data)
        + _assumptions_ledger(data)
        + _input_support_audit(data)
        + _capability_strip(data)
        + f'<div class="card" data-contract-section="capability_surface_map">'
        f"<h3>Capability Surface Map</h3>{tier_blocks}</div>"
        + _render_brain_map(data)
        + boundary_card
        + _card(
            "Notas y artefactos",
            _ul(evidence.get("notes") or []) + _ul(evidence.get("artifacts") or []),
        )
        + "</div></aside>"
        "<!--EVIDENCE_DRAWER_END-->"
    )


def _render_evidence(data: Mapping[str, Any], active_module: str) -> str:
    """Main-stage Evidence stub: commercial summary only; the technical audit
    lives in the right-side drawer (see the drawer gate tests)."""
    return (
        f'<section id="evidence" data-module="evidence"'
        f' class="module{" active" if active_module == "evidence" else ""}">'
        f'<div class="mod-head"><h2>Evidence</h2>'
        f'<p class="purpose">La caja negra tecnica vive en el Evidence Drawer;'
        f" aqui solo el resumen.</p></div>"
        f'<div class="card evidence-stub">'
        f"<h3>Auditoria tecnica</h3>"
        f'<p class="op-summary">Origen de datos, cadena determinista, mapa de'
        f" capacidades, ledger de supuestos y explicacion del score estan en el"
        f" drawer de auditoria (no saturan la vista comercial).</p>"
        f'<div class="field-chips">'
        + _chip("render determinista", "steel")
        + _chip("sin red de runtime", "steel")
        + _chip("fixture congelado", "steel")
        + "</div>"
        f'<button type="button" class="drawer-btn" data-drawer-open>'
        f"Ver evidencia</button></div></section>"
    )


def _render_learning_feedback(data: Mapping[str, Any], active_module: str) -> str:
    learning = data.get("learning_plan") or {}
    schema_fields = (learning.get("operator_observations_schema") or {}).get("fields") or []
    slots = "".join(f'<div class="slot">{_e(field)} -&gt; (pendiente)</div>' for field in schema_fields)
    return (
        f'<section id="learning_feedback" data-module="learning_feedback"'
        f' class="module{" active" if active_module == "learning_feedback" else ""}"'
        f' data-module-status="future">'
        f'<div class="mod-head"><h2>Learning / Feedback</h2>'
        f'<p class="purpose">Placeholder honesto: esquema definido, datos en vivo no conectados.</p></div>'
        f'<div class="future-box"><span class="fb-tag">FUTURO - DATOS EN VIVO NO CONECTADOS</span>'
        f'<p>Sin analytics, sin fetch de datos, sin claims de PMF. El operador registrara'
        f' observaciones manualmente en Fase 2.</p><div class="slots">{slots}</div></div>'
        f'<div class="grid g2">'
        f"{_card('Continuar / Revisar / Matar', '<h4>Continuar si</h4>' + _ul(learning.get('continue_if') or [], 'plain go') + '<h4>Revisar si</h4>' + _ul(learning.get('review_if') or [], 'plain warn') + '<h4>Matar si</h4>' + _ul(learning.get('kill_if') or [], 'plain risk'))}"
        f"{_card('Senales', '<h4>Primera venta</h4>' + _ul(learning.get('first_sale_signals') or [], 'plain go') + '<h4>Riesgo</h4>' + _ul(learning.get('risk_signals') or [], 'plain risk'))}"
        f"</div>{_payload_blocks(data, 'learning_plan')}</section>"
    )


def _render_blocked_queue(data: Mapping[str, Any], active_module: str) -> str:
    summary = data.get("blocked_queue_summary") or {}
    queue = data.get("blocked_queue") or []
    blocked_count = int(summary.get("blocked_count") or 0)

    banner = (
        '<div class="blocked-banner">HAY PRODUCTOS BLOQUEADOS - NUNCA LISTOS PARA PREPARAR'
        " SIN DECISION DEL OPERADOR</div>"
        if blocked_count
        else ""
    )
    summary_block = (
        f'<div class="card" data-contract-section="blocked_queue_summary">'
        f"<h3>Blocked Queue Summary</h3>"
        + _kv(
            {
                "blocked_count": summary.get("blocked_count", 0),
                "can_prepare": summary.get("can_prepare", False),
            }
        )
        + "<h4>Reason codes</h4>"
        + "".join(_chip(code, "risk") for code in summary.get("reason_codes") or [])
        + "<h4>Acciones requeridas del operador</h4>"
        + _ul(summary.get("required_operator_actions") or [], "plain warn")
        + "</div>"
    )
    item_blocks = []
    for item in queue:
        actions = _ul(
            [
                f"{action.get('label', '')} [{action.get('kind', '')}]"
                for action in item.get("operator_actions") or []
            ],
            "plain warn",
        )
        item_blocks.append(
            f'<div class="card blocked-item" data-marker="repair_or_reject_only">'
            f'<h3>{_e(item.get("product_name", ""))}</h3>'
            + _kv(
                {
                    "reason": item.get("reason", ""),
                    "severity": item.get("severity", ""),
                    "can_recover": item.get("can_recover", False),
                }
            )
            + "".join(_chip(code, "risk") for code in item.get("reason_codes") or [])
            + "<h4>Decision del operador (solo reparar o rechazar)</h4>"
            + actions
            + "</div>"
        )
    items_html = "".join(item_blocks) or _card(
        "Cola", '<p class="empty">Cola de bloqueados vacia.</p>'
    )
    active = " active" if active_module == "blocked_queue" else ""
    return (
        f'<section id="blocked_queue" data-module="blocked_queue" class="module{active}">'
        f'<div class="mod-head"><h2>Blocked Queue</h2>'
        f'<p class="purpose">Productos detenidos por claims o economia; el operador decide.</p></div>'
        f"{banner}{summary_block}{items_html}</section>"
    )


_INLINE_CSS = """
:root{--bg:#08090d;--bg-soft:#0c0e14;--panel:#11141c;--panel-2:#161a24;--panel-3:#1c2130;
--line:#272e3f;--line-soft:#1e2432;--ink:#edeff4;--ink-2:#b7bfcc;--ink-3:#7f8a9d;--ink-4:#556076;
--gold:#d8b36a;--gold-2:#ecd09a;--gold-soft:#221b0e;--gold-line:#4a3a17;
--steel:#8aabd4;--steel-soft:#121b28;--steel-line:#2b3d55;
--go:#37c68f;--go-soft:#0c231b;--go-line:#1c4a38;
--warn:#dfa64e;--warn-soft:#261d0d;--warn-line:#4e3d18;
--risk:#e05e55;--risk-soft:#271213;--risk-line:#552726;
--violet:#a488ea;--violet-soft:#1b1530;--violet-line:#3a2e5e;
--mono:"Cascadia Code","Consolas",ui-monospace,monospace;
--sans:"Segoe UI",system-ui,-apple-system,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
[hidden]{display:none!important}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.5}
.shell{display:grid;grid-template-columns:248px 1fr;min-height:100vh}
#module_rail{position:sticky;top:0;height:100vh;overflow-y:auto;
background:linear-gradient(180deg,#0b0d13,#08090d);
border-right:1px solid var(--line-soft);padding:18px 12px;display:flex;flex-direction:column;gap:4px}
#module_rail .logo{font-weight:800;font-size:15px;letter-spacing:.06em;padding:6px 10px 16px;
border-bottom:1px solid var(--line-soft);margin-bottom:10px}
#module_rail .logo span{color:var(--gold);font-weight:700}
#module_rail .logo small{display:block;font-size:9.5px;font-weight:600;color:var(--ink-4);
text-transform:uppercase;letter-spacing:.14em;margin-top:3px}
.nav-item{display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:9px;cursor:pointer;
border:1px solid transparent;user-select:none;transition:background .12s,border-color .12s}
.nav-item:hover{background:var(--panel-2)}
.nav-item.active{background:var(--steel-soft);border-color:var(--steel-line);
box-shadow:inset 2px 0 0 var(--gold)}
.nav-item .n{font-family:var(--mono);font-size:10px;font-weight:700;color:var(--ink-4);
width:23px;height:23px;border-radius:6px;background:var(--panel-3);
display:flex;align-items:center;justify-content:center;flex-shrink:0}
.nav-item.active .n{background:var(--gold);color:#1b1406}
.nav-item .t{font-size:12px;font-weight:700;letter-spacing:.01em;color:var(--ink-2)}
.nav-item.active .t{color:var(--ink)}
.nav-item .b{margin-left:auto;font-size:9px;font-weight:800;letter-spacing:.05em;padding:2px 6px;border-radius:5px}
.b-pass{color:var(--go);background:var(--go-soft)} .b-warning{color:var(--warn);background:var(--warn-soft)}
.b-blocked{color:var(--risk);background:var(--risk-soft)} .b-empty{color:var(--ink-3);background:var(--panel-3)}
.b-future{color:var(--violet);background:var(--violet-soft)} .b-audit{color:var(--steel);background:var(--steel-soft)}
.rail-foot{margin-top:auto;padding:14px 10px 4px;font-size:10px;color:var(--ink-4);line-height:1.8;
border-top:1px solid var(--line-soft);font-family:var(--mono)}
.main{min-width:0}
.cockpit{position:sticky;top:0;z-index:50;background:rgba(8,9,13,.97);
border-bottom:1px solid var(--gold-line);padding:12px 26px 10px}
.ck-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.ck-top{padding-bottom:9px;border-bottom:1px solid var(--line-soft)}
.ck-money{padding-top:9px}
.ck-id .p-name{font-size:15.5px;font-weight:800;letter-spacing:.01em}
.ck-id .p-meta{font-size:11px;color:var(--ink-4);font-family:var(--mono)}
.spacer{flex:1}
.metric{display:flex;flex-direction:column;padding:2px 14px;border-left:2px solid var(--line-soft)}
.metric:first-child{border-left:0;padding-left:0}
.m-label{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-4)}
.m-value{font-size:17px;font-weight:800;font-family:var(--mono);letter-spacing:.01em}
.m-gold{color:var(--gold-2)} .m-ink{color:var(--ink)}
.m-sub{font-size:10px;color:var(--ink-3)}
.metric-empty{font-size:11.5px;color:var(--ink-3);font-style:italic}
.chip{display:inline-block;font-size:10.5px;padding:3px 9px;border-radius:6px;margin:2px;font-family:var(--mono)}
.chip-go{background:var(--go-soft);color:var(--go);border:1px solid var(--go-line)}
.chip-warn{background:var(--warn-soft);color:var(--warn);border:1px solid var(--warn-line)}
.chip-risk{background:var(--risk-soft);color:var(--risk);border:1px solid var(--risk-line)}
.chip-muted{background:var(--panel-3);color:var(--ink-2);border:1px solid var(--line-soft)}
.chip-steel{background:var(--steel-soft);color:var(--steel);border:1px solid var(--steel-line);
font-size:9.5px;font-weight:700;letter-spacing:.06em}
.chip-gold{background:var(--gold-soft);color:var(--gold-2);border:1px solid var(--gold-line);
font-size:9.5px;font-weight:800;letter-spacing:.06em}
.chip-boundary{background:var(--risk-soft);color:#e8a9a5;border:1px solid var(--risk-line);
font-size:9.5px;font-weight:700;letter-spacing:.06em}
.chip-alias{background:var(--gold-soft);color:var(--gold-2);border:1px solid var(--gold-line);
font-size:10px;font-weight:800;letter-spacing:.05em}
.cta{border:0;border-radius:8px;padding:9px 16px;font-weight:800;font-size:12px;cursor:pointer;
font-family:var(--sans);letter-spacing:.02em}
.cta-go{background:linear-gradient(180deg,var(--gold-2),var(--gold));color:#1b1406;
box-shadow:0 1px 8px rgba(216,179,106,.25)}
.cta-warn{background:var(--warn);color:#241a02}
.cta-muted{background:var(--panel-3);color:var(--ink-3);cursor:default}
.content{padding:24px 26px 60px;max-width:1240px}
.module{display:none}
.module.active{display:block}
.mod-head h2{font-size:21px;font-weight:800;letter-spacing:.01em}
.mod-head .purpose{font-size:12.5px;color:var(--ink-3);margin:2px 0 16px}
.card{background:linear-gradient(180deg,var(--panel-2),var(--panel));border:1px solid var(--line-soft);
border-radius:14px;padding:15px 17px;margin-bottom:14px;box-shadow:0 1px 2px rgba(0,0,0,.35)}
.card h3{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-3);
margin-bottom:11px;padding-bottom:8px;border-bottom:1px solid var(--line-soft);display:flex;align-items:center;gap:7px}
.card h3::before{content:"";width:3px;height:11px;border-radius:2px;background:var(--gold);flex-shrink:0}
.grid{display:grid;gap:14px}
.g2{grid-template-columns:1fr 1fr}
.g3{grid-template-columns:1fr 1fr 1fr}
.grid .card{margin-bottom:0}
table.kv{border-collapse:collapse;width:100%;font-size:12.5px}
table.kv th,table.kv td{border-bottom:1px dashed var(--line-soft);padding:5px 6px;text-align:left;vertical-align:top}
table.kv th{color:var(--ink-3);font-weight:700;white-space:nowrap}
ul.plain{list-style:none}
ul.plain li{padding:4px 0 4px 16px;position:relative;color:var(--ink-2);font-size:12.5px}
ul.plain li::before{content:"";position:absolute;left:2px;top:11px;width:6px;height:6px;border-radius:2px;background:var(--steel)}
ul.plain.go li::before{background:var(--go)} ul.plain.warn li::before{background:var(--warn)}
ul.plain.risk li::before{background:var(--risk)}
.status{font-size:10px;font-weight:800;letter-spacing:.06em;padding:4px 11px;border-radius:14px}
.status-pass{background:var(--go-soft);color:var(--go);border:1px solid var(--go-line)}
.status-warning{background:var(--warn-soft);color:var(--warn);border:1px solid var(--warn-line)}
.status-blocked{background:var(--risk-soft);color:var(--risk);border:1px solid var(--risk-line)}
.status-empty{background:var(--panel-3);color:var(--ink-3);border:1px solid var(--line-soft)}
.status-future{background:var(--violet-soft);color:var(--violet);border:1px solid var(--violet-line)}
.status-audit{background:var(--steel-soft);color:var(--steel);border:1px solid var(--steel-line)}
.honesty{font-size:11.5px;color:var(--ink-3);font-style:italic;margin-top:8px}
.honesty-banner{background:var(--panel-2);border:1px dashed var(--line);border-radius:10px;
padding:9px 14px;font-size:11.5px;color:var(--ink-3);font-family:var(--mono);margin-bottom:14px}
.boundary-banner{background:var(--steel-soft);border:1px solid var(--steel-line);border-radius:10px;
padding:9px 14px;font-size:11px;font-weight:700;letter-spacing:.05em;color:var(--steel);
font-family:var(--mono);margin-bottom:14px}
.warning{background:var(--warn-soft);border:1px solid var(--warn-line);border-radius:10px;padding:9px 12px;
color:#e8cf9d;font-size:12.5px;margin-bottom:12px}
.warn-strip{background:var(--warn-soft);border:1px solid var(--warn-line);border-radius:10px;padding:10px 14px;
font-size:12.5px;color:#e8cf9d;margin-top:12px}
.blocked-banner{background:var(--risk-soft);border:1px solid var(--risk-line);border-radius:10px;padding:12px 16px;
color:var(--risk);font-weight:800;font-size:13px;margin-bottom:14px;letter-spacing:.03em}
.disabled{background:var(--panel-2);border:1px dashed var(--line);border-radius:10px;padding:12px 14px;
color:var(--ink-3);font-size:12.5px}
.empty{color:var(--ink-3);font-size:12px}
.mod-row{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px dashed var(--line-soft);font-size:12.5px}
.mod-row:last-child{border-bottom:0}
.mod-row span:first-child{flex:1;color:var(--ink-2)}
.mod-badge{font-family:var(--mono);font-size:10.5px;color:var(--ink-3)}
.action-item{display:flex;gap:10px;align-items:flex-start;background:var(--bg-soft);
border:1px solid var(--line-soft);border-radius:11px;padding:11px 13px;margin-bottom:8px;cursor:pointer;
transition:border-color .12s}
.action-item:hover{border-color:var(--gold-line)}
.action-item[data-primary="true"]{border-color:var(--gold-line);
background:linear-gradient(160deg,#171307,var(--bg-soft))}
.action-item .ck{width:20px;height:20px;border-radius:6px;border:2px solid var(--gold);flex-shrink:0;margin-top:1px}
.action-item.done .ck{background:var(--go);border-color:var(--go)}
.action-item.done .a-label{text-decoration:line-through;color:var(--ink-3)}
.action-item .prio{font-family:var(--mono);font-size:10px;font-weight:800;color:var(--gold-2);
background:var(--gold-soft);border:1px solid var(--gold-line);border-radius:6px;
padding:2px 7px;flex-shrink:0;margin-top:2px}
.action-item .a-label{font-size:12.5px;font-weight:700}
.action-item .a-note{font-size:11.5px;color:var(--ink-3)}
.action-item .a-src{font-size:9.5px;color:var(--ink-4);font-family:var(--mono);margin-top:3px}
.action-item .a-jump{margin-left:auto;flex-shrink:0;font-size:11px;color:var(--steel);font-weight:700;
background:var(--steel-soft);border:1px solid var(--steel-line);border-radius:6px;padding:3px 9px;white-space:nowrap}
.local-note{font-size:10.5px;color:var(--ink-3);font-style:italic;margin-top:6px}
.score-row{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px dashed var(--line-soft)}
.score-row:last-child{border-bottom:0}
.score-row .lbl{width:170px;font-size:12px;color:var(--ink-2)}
.score-row .bar{flex:1;height:8px;border-radius:4px;background:var(--panel-3);overflow:hidden}
.score-row .bar i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,#3d5a85,var(--steel))}
.score-row .val{width:44px;text-align:right;font-family:var(--mono);font-size:12px}
.field-chips{display:flex;flex-wrap:wrap;gap:4px}
.studio{display:grid;grid-template-columns:1fr 280px;gap:14px;align-items:start}
.guard-rail{position:sticky;top:118px}
.guard-card{background:var(--panel);border:1px solid var(--warn-line);border-radius:13px;overflow:hidden}
.guard-head{background:var(--warn-soft);padding:9px 13px;font-size:11px;font-weight:800;
letter-spacing:.08em;text-transform:uppercase;color:var(--warn)}
.guard-body{padding:11px 13px;font-size:12px}
.guard-body h4{font-size:10px;text-transform:uppercase;letter-spacing:.08em;margin:8px 0 3px}
.guard-body h4.ok{color:var(--go)} .guard-body h4.warn{color:var(--warn)} .guard-body h4.no{color:var(--risk)}
.guard-summary{border-top:1px dashed var(--line-soft);padding-top:8px;margin-top:8px;color:var(--ink-2);font-size:11.5px}
.copyblock{background:var(--bg-soft);border:1px solid var(--line);border-radius:11px;margin-bottom:10px;overflow:hidden}
.cb-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 12px;
background:linear-gradient(180deg,var(--panel-3),var(--panel-2));border-bottom:1px solid var(--line-soft)}
.cb-title{font-size:10.5px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-2)}
.copy-btn{font-size:11px;font-weight:800;color:#1b1406;background:linear-gradient(180deg,var(--gold-2),var(--gold));
border:0;border-radius:6px;padding:4px 13px;cursor:pointer;font-family:var(--sans);letter-spacing:.02em}
.copy-btn.done{background:var(--go);color:#04150d}
.cb-body{padding:11px 13px;font-size:12px;color:#cdd8e8;white-space:pre-wrap;font-family:var(--mono);
max-height:320px;overflow:auto}
details{margin-bottom:10px}
details summary{cursor:pointer;font-size:12px;color:var(--ink-2);padding:6px 0}
.payload-drawer{background:var(--bg-soft);border:1px solid var(--gold-line);border-radius:11px;padding:4px 12px 8px}
.payload-drawer>summary{font-size:11.5px;font-weight:800;letter-spacing:.05em;color:var(--gold-2);
text-transform:uppercase;padding:8px 0}
.lab-nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;background:var(--bg-soft);
border:1px solid var(--line-soft);border-radius:11px;padding:6px}
.lab-tab{font-size:12px;font-weight:700;color:var(--ink-3);padding:6px 13px;border-radius:8px;
cursor:pointer;border:1px solid transparent;user-select:none;transition:color .12s,background .12s}
.lab-tab:hover{color:var(--ink-2);background:var(--panel-2)}
.lab-tab.active{background:var(--violet-soft);color:#cbb8ff;border-color:var(--violet-line)}
.lab-panel{display:none}
.lab-panel.active{display:block}
.conf-strip{display:flex;gap:6px;flex-wrap:wrap}
.conf-pill{font-size:10.5px;padding:4px 9px;border-radius:12px;font-family:var(--mono);
border:1px solid var(--line-soft);background:var(--panel-2);color:var(--ink-2)}
.conf-pill b{color:var(--go)}
.angle-card,.hyp-card{background:var(--bg-soft);border:1px solid var(--line-soft);border-radius:11px;
padding:12px 14px;margin-bottom:10px;font-size:12.5px}
.angle-card .a-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.a-why{background:var(--go-soft);border-radius:8px;padding:7px 10px;font-size:11.5px;color:#9ed8bd;margin-top:8px}
.a-fail{background:var(--risk-soft);border-radius:8px;padding:7px 10px;font-size:11.5px;color:#e8a9a5;margin-top:6px}
.risk-note{border-left:3px solid var(--warn);background:var(--warn-soft);border-radius:0 8px 8px 0;
padding:8px 11px;font-size:11.5px;color:#e8cf9d;margin-top:8px}
.risk-note.risk-low{border-color:var(--go);background:var(--go-soft);color:#9ed8bd}
.risk-note.risk-prohibited{border-color:var(--risk);background:var(--risk-soft);color:#e8a9a5}
.risk-note .risk-tag{font-weight:800;text-transform:uppercase;font-size:10px;letter-spacing:.05em}
.risk-note .safe{color:#bfe9d6}
.budget-banner{background:var(--gold-soft);border:1px dashed var(--gold-line);border-radius:10px;padding:10px 14px;
font-size:12px;color:var(--gold-2);margin-bottom:14px;font-family:var(--mono)}
.future-box{border:1px dashed var(--violet-line);background:var(--violet-soft);border-radius:13px;padding:14px 16px;margin-bottom:14px}
.fb-tag{font-size:10px;font-weight:800;letter-spacing:.08em;color:var(--violet);border:1px solid var(--violet-line);
border-radius:5px;padding:2px 8px;display:inline-block;margin-bottom:8px}
.future-box p{font-size:12px;color:var(--ink-2)}
.slots{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}
.slot{border:1px dashed var(--line);border-radius:8px;padding:8px 10px;font-size:11px;color:var(--ink-3);font-family:var(--mono)}
.snapshot{border-color:var(--go-line);background:linear-gradient(160deg,#0d1f19,var(--panel))}
.snapshot h3{color:var(--go)} .snapshot h3::before{background:var(--go)}
.snap-col h4{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;color:var(--ink-3)}
.snap-col h4.ok{color:var(--go)} .snap-col h4.warn{color:var(--warn)} .snap-col h4.go{color:var(--steel)}
.snap-col h4.no{color:var(--risk)}
.snap-primary{background:linear-gradient(180deg,var(--gold-2),var(--gold));color:#1b1406;border-radius:9px;
padding:9px 12px;font-weight:800;font-size:12.5px;cursor:pointer;margin-bottom:10px}
.op-top{display:flex;align-items:center;gap:8px}
.op-summary{font-size:12px;color:var(--ink-2)}
.op-next{font-size:11.5px;color:var(--ink-3)}
.mod-head h2 .mod-badge{font-size:11px;margin-left:6px}
.honesty-footer{margin-top:32px;padding:14px 0;border-top:1px solid var(--line-soft);
font-size:10.5px;color:var(--ink-4);text-align:center;font-family:var(--mono);line-height:1.9}
.link-btn{background:none;border:1px solid var(--line);border-radius:6px;color:var(--ink-3);
font-size:10px;font-family:var(--mono);padding:2px 9px;cursor:pointer}
.link-btn:hover{color:var(--ink-2);border-color:var(--steel-line)}
.brief{border-color:var(--steel-line);background:linear-gradient(165deg,#111a28,var(--panel))}
.brief h3{color:var(--steel)} .brief h3::before{background:var(--steel)}
.brief .brief-why{font-size:12.5px;color:var(--ink-2);margin:8px 0}
.brief-hero{margin-bottom:16px}
.verdict-hero{background:linear-gradient(165deg,#101d17,var(--bg-soft));border:1px solid var(--go-line);
border-radius:12px;padding:14px 16px}
.vh-tag{display:block;font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.12em;
color:var(--ink-4);margin-bottom:8px}
.vh-outcome{font-size:16px;font-weight:800;letter-spacing:.02em;color:var(--go);font-family:var(--mono)}
.vh-gate{font-size:10.5px;color:var(--ink-3);font-family:var(--mono);margin-bottom:4px}
.brief-card{background:var(--bg-soft);border:1px solid var(--line-soft);border-radius:12px;padding:14px 16px}
.money-card{border-color:var(--gold-line);background:linear-gradient(165deg,#191307,var(--bg-soft))}
.money-card .metric{border-left:0;padding:4px 0}
.risk-card{border-color:var(--warn-line)}
.trust-boundary{margin-top:16px;border-top:1px dashed var(--risk-line);padding-top:12px}
.trust-boundary h4{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--risk);margin-bottom:6px}
.strip .strip-col{padding:8px 0;border-bottom:1px dashed var(--line-soft)}
.strip .strip-col:last-child{border-bottom:0}
.strip-label{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.07em;
text-transform:uppercase;color:var(--ink-3);width:170px;vertical-align:top;padding-top:4px}
.brainmap{border-color:var(--steel-line)}
.brainmap h3{color:var(--steel)} .brainmap h3::before{background:var(--steel)}
.bmap{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}
.bnode{border-radius:10px;padding:9px 10px;display:flex;flex-direction:column;gap:3px;
border:1px solid var(--line-soft);background:var(--bg-soft)}
.bn-name{font-size:11px;font-weight:800;letter-spacing:.02em}
.bn-tier{font-size:8.5px;font-weight:800;letter-spacing:.1em;font-family:var(--mono)}
.bn-src{font-size:8.5px;color:var(--ink-4);font-family:var(--mono);word-break:break-all}
.bnode-go{border-color:var(--go-line)} .bnode-go .bn-tier{color:var(--go)}
.bnode-steel{border-color:var(--steel-line)} .bnode-steel .bn-tier{color:var(--steel)}
.bnode-violet{border-color:var(--violet-line)} .bnode-violet .bn-tier{color:var(--violet)}
.bnode-risk{border-color:var(--risk-line)} .bnode-risk .bn-tier{color:var(--risk)}
.bnode-muted .bn-tier{color:var(--ink-3)}
.stack{display:flex;flex-direction:column}
.stack-step{display:flex;gap:12px;padding:2px 0}
.stack-rail-line{display:flex;flex-direction:column;align-items:center;width:16px}
.stack-rail-line::after{content:"";flex:1;width:2px;background:var(--line-soft);margin-top:2px}
.stack-step:last-child .stack-rail-line::after{display:none}
.stack-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;margin-top:4px}
.dot-pass{background:var(--go)} .dot-warning{background:var(--warn)} .dot-blocked{background:var(--risk)}
.dot-empty{background:var(--ink-3)} .dot-future{background:var(--violet)} .dot-audit{background:var(--steel)}
.stack-body{flex:1;padding-bottom:14px}
.stack-body h4{font-size:13px;font-weight:800;margin-bottom:0}
.stack-body h5{font-size:10px;text-transform:uppercase;letter-spacing:.08em;margin:6px 0 2px}
.stack-body h5.warn{color:var(--warn)}
.stack-source{font-size:10px;color:var(--ink-4);font-family:var(--mono);margin-top:4px}
.listing-title{font-size:17px;font-weight:800}
.listing-subtitle{font-size:12.5px;color:var(--ink-2);margin-bottom:8px}
.price-block{display:flex;align-items:baseline;gap:10px}
.price-now{font-size:22px;font-weight:800;font-family:var(--mono);color:var(--gold-2)}
.price-compare{font-size:13px;color:var(--ink-3);text-decoration:line-through;font-family:var(--mono)}
.listing-preview{border-color:var(--gold-line)}
.listing-preview h3{color:var(--gold-2)}
.lp-frame{display:grid;grid-template-columns:180px 1fr;gap:16px;align-items:start}
.lp-img{border:1px dashed var(--line);border-radius:10px;min-height:150px;display:flex;
align-items:center;justify-content:center;text-align:center;font-size:10.5px;color:var(--ink-4);
font-family:var(--mono);background:var(--bg-soft);padding:10px}
.lp-title{font-size:16px;font-weight:800}
.lp-sub{font-size:12px;color:var(--ink-2);margin-bottom:6px}
.lp-note{font-size:10.5px;color:var(--ink-4);font-style:italic;margin-top:8px;
border-top:1px dashed var(--line-soft);padding-top:6px}
.evidence-chain{display:flex;flex-direction:column;gap:0}
.chain-step{display:flex;gap:12px;align-items:flex-start;padding:9px 0;
border-bottom:1px dashed var(--line-soft)}
.chain-step:last-child{border-bottom:0}
.chain-step .cs-n{font-family:var(--mono);font-size:10px;font-weight:800;color:var(--steel);
background:var(--steel-soft);border:1px solid var(--steel-line);border-radius:6px;
width:26px;height:22px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.chain-step b{font-size:12.5px;display:block}
.chain-step .cs-d{font-size:10.5px;color:var(--ink-3);font-family:var(--mono);display:block;word-break:break-all}
.session-gate{position:fixed;inset:0;z-index:200;background:rgba(5,6,9,.94);
display:flex;align-items:center;justify-content:center;padding:20px}
.gate-card{background:linear-gradient(170deg,#12151d,#0b0d12);border:1px solid var(--gold-line);
border-radius:18px;padding:34px 38px;max-width:440px;width:100%;text-align:center;
box-shadow:0 18px 60px rgba(0,0,0,.6)}
.gate-brand{font-size:13px;font-weight:800;letter-spacing:.2em;color:var(--ink-3);margin-bottom:14px}
.gate-brand span{color:var(--gold)}
.gate-card h1{font-size:22px;font-weight:800;letter-spacing:.01em;margin-bottom:4px}
.gate-sub{font-size:12px;color:var(--ink-3);margin-bottom:14px}
.gate-modes{margin-bottom:18px}
.gate-label{display:block;font-size:10px;font-weight:800;text-transform:uppercase;
letter-spacing:.1em;color:var(--ink-4);text-align:left;margin-bottom:6px}
.gate-input{width:100%;background:var(--bg-soft);border:1px solid var(--line);border-radius:9px;
color:var(--ink);font-size:13px;font-family:var(--sans);padding:10px 12px;margin-bottom:14px;outline:none}
.gate-input:focus{border-color:var(--gold-line)}
.gate-enter{width:100%;border:0;border-radius:9px;padding:11px 16px;font-weight:800;font-size:13px;
cursor:pointer;font-family:var(--sans);letter-spacing:.03em;color:#1b1406;
background:linear-gradient(180deg,var(--gold-2),var(--gold));box-shadow:0 2px 12px rgba(216,179,106,.28)}
.gate-disclaimer{font-size:10.5px;color:var(--ink-4);margin-top:14px;line-height:1.7}
.gate-fixture{font-size:9.5px;color:var(--ink-4);font-family:var(--mono);margin-top:8px}
.selector{border-color:var(--gold-line)}
.selector h3{color:var(--gold-2)}
.sel-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin-bottom:10px}
.sel-card{background:var(--bg-soft);border:1px solid var(--line-soft);border-radius:12px;
padding:11px 13px;cursor:pointer;transition:border-color .12s,background .12s}
.sel-card:hover{border-color:var(--steel-line)}
.sel-card.active{border-color:var(--gold);background:linear-gradient(165deg,#191307,var(--bg-soft));
box-shadow:0 0 0 1px var(--gold-line)}
.sel-card .sc-top{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:6px}
.sel-card .sc-name{font-size:12.5px;font-weight:800;line-height:1.35;margin-bottom:4px}
.sel-card .sc-money{font-size:11px;font-family:var(--mono);color:var(--gold-2)}
.sel-card .sc-next{font-size:10.5px;color:var(--ink-3);margin-top:2px}
.sel-card .sc-rich{font-size:9.5px;color:var(--ink-4);font-family:var(--mono);margin-top:4px}
.sel-compare summary{font-size:11px;color:var(--steel);font-weight:700}
.draft-field{margin-bottom:12px}
.draft-label{display:flex;align-items:center;gap:8px;font-size:10px;font-weight:800;
text-transform:uppercase;letter-spacing:.09em;color:var(--ink-3);margin-bottom:5px}
.dirty-chip{font-size:8.5px;padding:1px 7px}
.draft-input{width:100%;background:var(--bg);border:1px solid var(--line);border-radius:9px;
color:var(--ink);font-size:12.5px;font-family:var(--sans);padding:9px 11px;outline:none;
resize:vertical;line-height:1.5}
.draft-input:focus{border-color:var(--gold-line);background:var(--bg-soft)}
.draft-input:hover{border-color:var(--line)}
.draft-hint{display:block;font-size:10px;color:var(--ink-4);font-style:italic;margin-top:4px}
.reset-btn{background:var(--panel-3);border:1px solid var(--line);border-radius:7px;
color:var(--ink-2);font-size:11px;font-weight:700;font-family:var(--sans);
padding:6px 13px;cursor:pointer;margin-top:2px}
.reset-btn:hover{border-color:var(--steel-line);color:var(--ink)}
.prog-row{display:flex;align-items:center;gap:12px;padding:7px 0;border-bottom:1px dashed var(--line-soft)}
.prog-row:last-of-type{border-bottom:0}
.prog-label{width:130px;font-size:11px;font-weight:700;color:var(--ink-3);
text-transform:uppercase;letter-spacing:.06em}
.prog-bar{flex:1;height:8px;border-radius:4px;background:var(--panel-3);overflow:hidden}
.prog-bar i{display:block;height:100%;width:0;border-radius:4px;
background:linear-gradient(90deg,var(--gold),var(--gold-2));transition:width .2s}
.prog-val{font-family:var(--mono);font-size:11.5px;color:var(--gold-2);white-space:nowrap}
.export-panel{border-color:var(--gold-line);background:linear-gradient(165deg,#171205,var(--panel))}
.export-panel h3{color:var(--gold-2)}
.candidate-shell[hidden]{display:none}
@media(max-width:1100px){.bmap{grid-template-columns:repeat(3,1fr)}}
@media(max-width:960px){.shell{grid-template-columns:1fr}
#module_rail{position:static;height:auto;flex-direction:row;flex-wrap:wrap}
.g2,.g3,.studio,.slots,.lp-frame{grid-template-columns:1fr}.guard-rail{position:static}
.bmap{grid-template-columns:repeat(2,1fr)}}
""".strip()


_INLINE_JS = """
(function () {
  "use strict";

  // Browser-local memory only (localStorage): operator alias, checks, drafts,
  // tabs, selected candidate. No backend, no account, no real authentication,
  // nothing leaves the machine.
  var CHECKS_PREFIX = "r109b_checks_";
  var TABS_PREFIX = "r109b_tabs_";
  var DRAFTS_PREFIX = "r109b_drafts_";
  var SESSION_KEY = "r109b_operator_session";
  var WORKSPACE_KEY = "r109b_workspace_state";

  function readJson(key) {
    try {
      return JSON.parse(window.localStorage.getItem(key)) || {};
    } catch (err) { return {}; }
  }

  function writeJson(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch (err) { /* local-only; storage may be unavailable */ }
  }

  function rootOf(el) {
    var root = el && el.closest ? el.closest("[data-candidate-root]") : null;
    return root || document.body;
  }

  function fixtureIdOf(el) {
    var root = rootOf(el);
    return root.getAttribute("data-candidate-root") ||
      document.body.getAttribute("data-fixture-id");
  }

  function allRoots() {
    return document.querySelectorAll("[data-candidate-root]");
  }

  // --- module rail + marketing tabs, scoped per candidate root ---

  function saveTabs(root, patch) {
    var key = TABS_PREFIX + (root.getAttribute("data-candidate-root") || "single");
    var tabs = readJson(key);
    for (var name in patch) {
      if (Object.prototype.hasOwnProperty.call(patch, name)) {
        tabs[name] = patch[name];
      }
    }
    writeJson(key, tabs);
  }

  function activateModule(root, moduleId, remember) {
    var sections = root.querySelectorAll("[data-module]");
    for (var i = 0; i < sections.length; i++) {
      sections[i].classList.toggle(
        "active", sections[i].getAttribute("data-module") === moduleId);
    }
    var navItems = root.querySelectorAll("[data-nav-module]");
    for (var j = 0; j < navItems.length; j++) {
      if (navItems[j].classList.contains("nav-item")) {
        navItems[j].classList.toggle(
          "active", navItems[j].getAttribute("data-nav-module") === moduleId);
      }
    }
    if (remember) { saveTabs(root, { module: moduleId }); }
    window.scrollTo(0, 0);
  }

  function activateLabPanel(root, panelId, remember) {
    var panels = root.querySelectorAll("[data-lab-panel]");
    for (var i = 0; i < panels.length; i++) {
      panels[i].classList.toggle("active", panels[i].id === panelId);
    }
    var tabs = root.querySelectorAll("[data-lab-tab]");
    for (var j = 0; j < tabs.length; j++) {
      tabs[j].classList.toggle(
        "active", tabs[j].getAttribute("data-lab-tab") === panelId);
    }
    if (remember) { saveTabs(root, { labTab: panelId }); }
  }

  function restoreTabs(root) {
    // Never override the blocked-first default: only restore when the
    // default module is command_center (no blocked items dominate).
    if (root.getAttribute("data-default-module") !== "command_center") {
      return;
    }
    var key = TABS_PREFIX + (root.getAttribute("data-candidate-root") || "single");
    var tabs = readJson(key);
    if (tabs.module &&
        root.querySelector('[data-module="' + tabs.module + '"]')) {
      activateModule(root, tabs.module, false);
    }
    if (tabs.labTab &&
        root.querySelector('[data-lab-panel][id="' + tabs.labTab + '"]')) {
      activateLabPanel(root, tabs.labTab, false);
    }
  }

  // --- candidate switcher (workspace mode; local show/hide only) ---

  function selectCandidate(fid, remember) {
    var roots = allRoots();
    for (var i = 0; i < roots.length; i++) {
      if (roots[i].getAttribute("data-candidate-root") === fid) {
        roots[i].removeAttribute("hidden");
      } else {
        roots[i].setAttribute("hidden", "");
      }
    }
    var cards = document.querySelectorAll("[data-candidate-select]");
    for (var j = 0; j < cards.length; j++) {
      cards[j].classList.toggle(
        "active", cards[j].getAttribute("data-candidate-select") === fid);
    }
    if (remember) { writeJson(WORKSPACE_KEY, { selected: fid }); }
    window.scrollTo(0, 0);
  }

  function restoreCandidate() {
    if (document.body.getAttribute("data-mode") !== "workspace_mode") { return; }
    var state = readJson(WORKSPACE_KEY);
    if (state.selected &&
        document.querySelector('[data-candidate-root="' + state.selected + '"]')) {
      selectCandidate(state.selected, false);
    }
  }

  // --- editable local drafts (never mutate the fixture/ViewModel) ---

  function draftsKey(fid) { return DRAFTS_PREFIX + fid; }

  function updateDirty(el) {
    var wrap = el.closest ? el.closest("[data-draft-wrap]") : null;
    if (!wrap) { return; }
    var chip = wrap.querySelector('[data-role="draft_dirty_state"]');
    if (!chip) { return; }
    if (el.value !== el.defaultValue) {
      chip.removeAttribute("hidden");
    } else {
      chip.setAttribute("hidden", "");
    }
  }

  function onDraftInput(event) {
    var el = event.target;
    if (!el || !el.getAttribute || el.getAttribute("data-draft-field") === null) {
      return;
    }
    var fid = fixtureIdOf(el);
    var drafts = readJson(draftsKey(fid));
    var fieldKey = el.getAttribute("data-draft-field");
    if (el.value === el.defaultValue) {
      delete drafts[fieldKey];
    } else {
      drafts[fieldKey] = el.value;
    }
    writeJson(draftsKey(fid), drafts);
    updateDirty(el);
    updateProgress(rootOf(el));
  }

  function restoreDrafts() {
    var fields = document.querySelectorAll("[data-draft-field]");
    for (var i = 0; i < fields.length; i++) {
      var el = fields[i];
      var drafts = readJson(draftsKey(fixtureIdOf(el)));
      var fieldKey = el.getAttribute("data-draft-field");
      if (Object.prototype.hasOwnProperty.call(drafts, fieldKey)) {
        el.value = drafts[fieldKey];
      }
      updateDirty(el);
    }
  }

  function resetDraftSection(button) {
    var card = button.closest(".card") || rootOf(button);
    var fields = card.querySelectorAll("[data-draft-field]");
    var fid = fixtureIdOf(button);
    var drafts = readJson(draftsKey(fid));
    for (var i = 0; i < fields.length; i++) {
      fields[i].value = fields[i].defaultValue;
      delete drafts[fields[i].getAttribute("data-draft-field")];
      updateDirty(fields[i]);
    }
    writeJson(draftsKey(fid), drafts);
    updateProgress(rootOf(button));
  }

  function draftAppendix(root) {
    var fid = root.getAttribute("data-candidate-root") ||
      document.body.getAttribute("data-fixture-id");
    var drafts = readJson(draftsKey(fid));
    var keys = [];
    for (var key in drafts) {
      if (Object.prototype.hasOwnProperty.call(drafts, key)) { keys.push(key); }
    }
    if (!keys.length) { return ""; }
    keys.sort();
    var out = "\\n\\n=== DRAFTS LOCALES DEL OPERADOR (memoria del navegador," +
      " no salida del motor) ===";
    for (var i = 0; i < keys.length; i++) {
      out += "\\n\\n[" + keys[i] + "]\\n" + drafts[keys[i]];
    }
    return out;
  }

  // --- local progress (checks + drafts), per candidate root ---

  function updateProgress(root) {
    var checks = root.querySelectorAll("[data-local-check]");
    var done = 0;
    for (var i = 0; i < checks.length; i++) {
      if (checks[i].classList.contains("done")) { done++; }
    }
    var checkOut = root.querySelectorAll("[data-checklist-progress]");
    for (var j = 0; j < checkOut.length; j++) {
      checkOut[j].textContent = done + " / " + checks.length;
    }
    var pct = checks.length ? Math.round((done * 100) / checks.length) : 0;
    var bars = root.querySelectorAll("[data-checklist-bar]");
    for (var k = 0; k < bars.length; k++) {
      bars[k].style.width = pct + "%";
    }
    var fields = root.querySelectorAll("[data-draft-field]");
    var dirty = 0;
    for (var m = 0; m < fields.length; m++) {
      if (fields[m].value !== fields[m].defaultValue) { dirty++; }
    }
    var draftOut = root.querySelectorAll("[data-draft-progress]");
    for (var n = 0; n < draftOut.length; n++) {
      draftOut[n].textContent = dirty + " campo(s) con draft local";
    }
  }

  function updateAllProgress() {
    var roots = allRoots();
    for (var i = 0; i < roots.length; i++) { updateProgress(roots[i]); }
  }

  // --- operator session gate: local browser session, NOT real authentication ---

  function applyAlias(alias) {
    var chips = document.querySelectorAll("[data-operator-alias-chip]");
    for (var i = 0; i < chips.length; i++) {
      if (alias) {
        chips[i].textContent = "OPERADOR: " + alias;
        chips[i].removeAttribute("hidden");
      } else {
        chips[i].textContent = "";
        chips[i].setAttribute("hidden", "");
      }
    }
  }

  function enterWorkbench() {
    var input = document.getElementById("operator_alias_input");
    var alias = input ? input.value.replace(/[<>"']/g, "").slice(0, 40).trim() : "";
    writeJson(SESSION_KEY, { alias: alias, entered: true });
    applyAlias(alias);
    var gate = document.getElementById("operator_session_gate");
    if (gate) { gate.setAttribute("hidden", ""); }
  }

  function resetSession() {
    try { window.localStorage.removeItem(SESSION_KEY); } catch (err) { /* local-only */ }
    applyAlias("");
    var gate = document.getElementById("operator_session_gate");
    if (gate) { gate.removeAttribute("hidden"); }
    var input = document.getElementById("operator_alias_input");
    if (input) { input.value = ""; }
  }

  function initSession() {
    var session = readJson(SESSION_KEY);
    var gate = document.getElementById("operator_session_gate");
    if (session.entered) {
      if (gate) { gate.setAttribute("hidden", ""); }
      applyAlias(session.alias || "");
    } else {
      var input = document.getElementById("operator_alias_input");
      if (input && session.alias) { input.value = session.alias; }
    }
  }

  // --- copy buttons (payloads + packets; full packet appends local drafts) ---

  function copyPayload(button) {
    var root = rootOf(button);
    var targetId = button.getAttribute("data-copy-target");
    var source = root.querySelector('[id="' + targetId + '"]') ||
      document.getElementById(targetId);
    if (!source) { return; }
    var text = source.textContent;
    if (button.hasAttribute("data-append-drafts")) {
      text += draftAppendix(root);
    }
    var original = button.textContent;
    function done(ok) {
      button.textContent = ok ? "Copiado" : "Copia manual";
      button.classList.add("done");
      window.setTimeout(function () {
        button.textContent = original;
        button.classList.remove("done");
      }, 1400);
    }
    function fallbackCopy() {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      document.body.removeChild(area);
      done(ok);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () { done(true); }, fallbackCopy);
    } else {
      fallbackCopy();
    }
  }

  // --- local checkmarks, keyed per candidate root ---

  function toggleCheck(item) {
    var key = CHECKS_PREFIX + fixtureIdOf(item);
    var checks = readJson(key);
    var checkId = item.getAttribute("data-local-check");
    checks[checkId] = !checks[checkId];
    item.classList.toggle("done", !!checks[checkId]);
    writeJson(key, checks);
    updateProgress(rootOf(item));
  }

  function restoreChecks() {
    var items = document.querySelectorAll("[data-local-check]");
    for (var i = 0; i < items.length; i++) {
      var checks = readJson(CHECKS_PREFIX + fixtureIdOf(items[i]));
      if (checks[items[i].getAttribute("data-local-check")]) {
        items[i].classList.add("done");
      }
    }
  }

  document.addEventListener("click", function (event) {
    var el = event.target;
    if (!el.closest) { return; }
    if (el.closest("[data-gate-enter]")) { enterWorkbench(); return; }
    if (el.closest("[data-session-reset]")) { resetSession(); return; }
    var resetBtn = el.closest("[data-draft-reset]");
    if (resetBtn) { resetDraftSection(resetBtn); return; }
    var copyButton = el.closest("[data-copy-button]");
    if (copyButton) { copyPayload(copyButton); return; }
    var candidate = el.closest("[data-candidate-select]");
    if (candidate) {
      selectCandidate(candidate.getAttribute("data-candidate-select"), true);
      return;
    }
    var check = el.closest("[data-local-check]");
    if (check) { toggleCheck(check); return; }
    var labTab = el.closest("[data-lab-tab]");
    if (labTab) {
      activateLabPanel(rootOf(labTab), labTab.getAttribute("data-lab-tab"), true);
      return;
    }
    var nav = el.closest("[data-nav-module]");
    if (nav) {
      activateModule(rootOf(nav), nav.getAttribute("data-nav-module"), true);
      return;
    }
  });

  document.addEventListener("input", onDraftInput);

  restoreChecks();
  restoreDrafts();
  initSession();
  var roots = allRoots();
  for (var i = 0; i < roots.length; i++) { restoreTabs(roots[i]); }
  restoreCandidate();
  updateAllProgress();
})();
""".strip()


def _candidate_shell(
    data: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    selected_fid: str,
) -> str:
    """One candidate's full workbench shell, wrapped in a data-candidate-root
    container so all local memory (checks, drafts, tabs) is scoped per candidate."""
    summary = data.get("blocked_queue_summary") or {}
    active_module = "blocked_queue" if int(summary.get("blocked_count") or 0) else "command_center"

    sections = "".join(
        (
            _render_command_center(data, active_module, candidates, selected_fid),
            _render_decision_center(data, active_module),
            _render_product_lab(data, active_module),
            _render_economics(data, active_module),
            _render_shopify_studio(data, active_module),
            _render_marketing_engine(data, active_module),
            _render_safety(data, active_module),
            _render_evidence(data, active_module),
            _render_learning_feedback(data, active_module),
            _render_blocked_queue(data, active_module),
        )
    )
    hidden = "" if data.get("fixture_id") == selected_fid else " hidden"
    return "".join(
        (
            f'<div class="candidate-shell" data-candidate-root="{_e(data["fixture_id"])}"'
            f' data-default-module="{_e(active_module)}"{hidden}>',
            '<div class="shell">',
            _render_rail(data, active_module),
            '<div class="main">',
            _render_header(data),
            '<div class="content">',
            sections,
            '<footer class="honesty-footer" data-principle="operator_in_control"'
            ' data-memory="browser_local_memory local_only_persistence">'
            "Memoria local del navegador (localStorage): alias del operador, checklists,"
            " drafts y tabs. Sin backend - sin cuenta - sin autenticacion real.<br>"
            "Sin escrituras en vivo - sin gasto - sin red - fixture congelado"
            ' - operador-en-control &nbsp;<button type="button" class="link-btn"'
            ' data-session-reset>Reiniciar sesion local</button></footer>',
            "</div></div></div>",
            _render_evidence_drawer(data),
            "</div>",
        )
    )


def _document(
    title_suffix: str, body_attrs: str, gate_html: str, shells_html: str
) -> str:
    document = "".join(
        (
            "<!DOCTYPE html>\n",
            '<html lang="es">\n<head>\n<meta charset="utf-8">\n',
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
            f"<title>SYNAPSE OS - {_e(RENDERER_MARKER)} - {_e(title_suffix)}</title>\n",
            f"<style>{_INLINE_CSS}</style>\n</head>\n",
            f'<body data-renderer="{_e(RENDERER_MARKER)}" data-flow="{_e(FLOW_MARKER)}"',
            f"{body_attrs}>\n",
            gate_html,
            shells_html,
            f"\n<script>\n{_INLINE_JS}\n</script>\n",
            "</body>\n</html>\n",
        )
    )
    found = scan_forbidden_tokens(document)
    if found:
        raise ValueError(f"Forbidden tokens in rendered visual output: {found}")
    return document


def render_visual_html(view_model: WorkbenchViewModel) -> str:
    """Render one fixture state as a self-contained functional workspace HTML."""
    data = view_model.to_dict()
    candidates = [_candidate_summary(data)]
    selected_fid = str(data["fixture_id"])
    body_attrs = (
        f' data-fixture-id="{_e(data["fixture_id"])}"'
        f' data-schema-version="{_e(data["schema_version"])}"'
        f' data-mode="single_candidate"'
    )
    return _document(
        str(data["fixture_id"]),
        body_attrs,
        _render_session_gate(data),
        _candidate_shell(data, candidates, selected_fid),
    )


def render_workspace_html(view_models: Sequence[WorkbenchViewModel]) -> str:
    """Render several fixture states as one multi-candidate workspace HTML.

    All candidates are embedded statically; switching is pure local JS
    (show/hide per data-candidate-root). Preparable candidates sort first;
    the first candidate is selected by default.
    """
    datas = [view_model.to_dict() for view_model in view_models]
    if not datas:
        raise ValueError("workspace mode needs at least one fixture ViewModel")
    datas.sort(
        key=lambda data: (
            0 if (data.get("blocked_queue_summary") or {}).get("can_prepare") else 1,
            str(data.get("fixture_id", "")),
        )
    )
    candidates = [_candidate_summary(data) for data in datas]
    selected_fid = candidates[0]["fid"]
    shells = "".join(
        _candidate_shell(data, candidates, selected_fid) for data in datas
    )
    schema_versions = sorted({str(data.get("schema_version", "")) for data in datas})
    body_attrs = (
        f' data-fixture-id="a8_r109a_workspace"'
        f' data-schema-version="{_e(";".join(schema_versions))}"'
        f' data-mode="workspace_mode"'
        f' data-candidate-count="{len(datas)}"'
    )
    gate = _render_session_gate(
        {"fixture_id": f"workspace multi-candidato ({len(datas)} estados)"}
    )
    return _document(
        f"workspace ({len(datas)} candidatos)", body_attrs, gate, shells
    )


def render_fixture_to_file(fixture_path: str | Path, output_path: str | Path) -> Path:
    view_model = build_view_model_from_path(fixture_path)
    document = render_visual_html(view_model)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(document)
    return target


def render_fixtures_to_workspace_file(
    fixture_paths: Sequence[str | Path], output_path: str | Path
) -> Path:
    view_models = [build_view_model_from_path(path) for path in fixture_paths]
    document = render_workspace_html(view_models)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(document)
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m synapse.ui.operator_workbench_visual",
        description="A8-R109B offline functional operator workspace render of"
        " R109A workbench fixtures.",
    )
    parser.add_argument("--fixture", help="Path to one fixture JSON.")
    parser.add_argument(
        "--output",
        help="Output HTML path (single render with --fixture; multi-candidate"
        " workspace with --fixture-dir).",
    )
    parser.add_argument("--fixture-dir", help="Directory with fixture JSON files.")
    parser.add_argument(
        "--output-dir",
        help="Output directory for per-fixture renders with --fixture-dir.",
    )
    args = parser.parse_args(argv)

    if args.fixture and args.output:
        target = render_fixture_to_file(args.fixture, args.output)
        print(f"rendered={target.as_posix()}")
        return 0

    if args.fixture_dir:
        fixture_dir = Path(args.fixture_dir)
        fixture_paths = sorted(fixture_dir.glob("*.json"))
        if not fixture_paths:
            parser.error(f"No fixture JSON files found in: {fixture_dir}")
        if args.output_dir:
            output_dir = Path(args.output_dir)
            for fixture_path in fixture_paths:
                target = render_fixture_to_file(
                    fixture_path, output_dir / f"{fixture_path.stem}.html"
                )
                print(f"rendered={target.as_posix()}")
            return 0
        if args.output:
            target = render_fixtures_to_workspace_file(fixture_paths, args.output)
            print(f"rendered={target.as_posix()}")
            return 0

    parser.error(
        "Use --fixture with --output, --fixture-dir with --output-dir, or"
        " --fixture-dir with --output for the embedded workspace."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
