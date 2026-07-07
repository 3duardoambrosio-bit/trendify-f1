"""A8-R109B-I1B — Operator Workbench visual flow renderer tests.

Covers: all four fixture states render, stable R109B/contract markers, state
rules (blocked dominates, low_input degrades, empty invents nothing), copy
button markers, determinism, forbidden-token scans, the render CLI, and the
R3 premium operator OS shell (session gate, cockpit, executive brief,
playbook, brain map, premium Shopify/Marketing/Evidence, local-only memory).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse.ui import operator_workbench_renderer as wb_renderer
from synapse.ui import operator_workbench_visual as wb_visual
from synapse.ui import operator_workbench_view_model as wb_vm

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "a8_r109a"
DOC_PATH = REPO_ROOT / "docs" / "a8_r109b" / "VISUAL_FLOW_CONTRACT.md"

FIXTURE_NAMES = ("recommended", "blocked", "low_input", "empty_shortlist")

R109B_FILES = (
    REPO_ROOT / "synapse" / "ui" / "operator_workbench_visual.py",
    Path(__file__).resolve(),
    DOC_PATH,
)

# Stable R109B markers the generated HTML must expose.
REQUIRED_R109B_MARKERS = (
    "operator_workbench_visual",
    "r109b_visual_flow",
    "module_rail",
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
)

# R109A.1 contract surface markers consumed by the visual layer.
REQUIRED_CONTRACT_MARKERS = (
    "module_status_summary",
    "candidate_pipeline",
    "blocked_queue_summary",
    "action_queue",
    "system_health_board",
    "capability_surface_map",
    "claim_guard",
)


def _forbidden_network_tokens() -> tuple[str, ...]:
    # Assembled from halves so this test file never contains the literal tokens.
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


def _forbidden_write_tokens() -> tuple[str, ...]:
    halves = (
        ("requests", ".post"),
        ("httpx", ".post"),
        ("_http_post", "("),
        ("_http_post_multipart", "("),
        ("forward_shopify_order", "("),
        ("create_product", "("),
        ("publish_campaign", "("),
    )
    return tuple(left + right for left, right in halves)


def _fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def _build(name: str) -> wb_vm.WorkbenchViewModel:
    return wb_vm.build_view_model_from_path(_fixture_path(name))


def _render(name: str) -> str:
    return wb_visual.render_visual_html(_build(name))


# --- 1. module imports and exposes the expected API ----------------------------

def test_visual_module_importable_api() -> None:
    assert callable(wb_visual.render_visual_html)
    assert callable(wb_visual.render_fixture_to_file)
    assert callable(wb_visual.main)
    assert wb_visual.RENDERER_MARKER == "operator_workbench_visual"
    assert wb_visual.FLOW_MARKER == "r109b_visual_flow"


# --- 2. all four fixtures render, deterministically -----------------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_all_fixtures_render_deterministically(name: str) -> None:
    document = _render(name)
    assert document.startswith("<!DOCTYPE html>")
    assert document.rstrip().endswith("</html>")
    assert document == _render(name), "visual render must be deterministic"


# --- 3. recommended exposes R109B + contract markers and copy buttons ------------

def test_recommended_contains_required_markers() -> None:
    document = _render("recommended")

    for marker in REQUIRED_R109B_MARKERS:
        assert marker in document, f"missing R109B marker: {marker}"
    for marker in REQUIRED_CONTRACT_MARKERS:
        assert marker in document, f"missing contract marker: {marker}"

    # Module rail entries come from module_status_summary, not renderer inference.
    for module_id in ("command_center", "shopify_studio", "marketing_engine"):
        assert f'data-nav-module="{module_id}"' in document
    assert 'data-source-contract="module_status_summary"' in document

    # Copy buttons over canonical payloads (real button markup, not just JS).
    assert '<button type="button" class="copy-btn" data-copy-button' in document
    assert 'data-copy-target="payload_shopify_title"' in document
    assert 'data-copy-target="payload_marketing_hooks"' in document

    # Selling-prep flow: primary prepare CTA present.
    assert 'data-cta="prepare"' in document

    # Claim guard adjacency next to both copy studios.
    assert 'data-adjacent-to="shopify_pack"' in document
    assert 'data-adjacent-to="marketing_pack"' in document

    # Marketing Engine workspace tabs.
    for tab_id, _label in wb_visual.LAB_TABS:
        assert f'data-lab-tab="{tab_id}"' in document


# --- 3b. recommended must feel like a sell-prep workspace (I1B-R1) ----------------

SELL_PREP_MARKERS = (
    "selling_pack_snapshot",
    "ready_now",
    "missing_before_publish",
    "operator_next_actions",
    "shopify_payload_copy",
    "marketing_payload_copy",
    "claim_guard_adjacent",
    "operator_in_control",
)


def test_recommended_feels_like_sell_prep_workspace() -> None:
    document = _render("recommended")

    for marker in SELL_PREP_MARKERS:
        assert marker in document, f"missing sell-prep marker: {marker}"

    # Operator-in-control CTA wording; never live-publish language.
    assert "Preparar venta con operador-en-control" in document
    for phrase in ("Publicar ahora", "Launch", "Enviar a Meta", "publish now"):
        assert phrase not in document, f"live-write language leaked: {phrase}"
    for token in _forbidden_write_tokens():
        assert token not in document, f"write token in rendered HTML: {token}"

    # Shopify Studio is a listing-prep panel, not a green audit table.
    assert 'data-no-publish="true"' in document
    assert "No se publica desde aqui" in document

    # The two pending rewrites are named with their surfaces and reasons.
    assert 'data-rewrites-pending="true"' in document
    assert 'data-rewrite-surface="headlines"' in document
    assert 'data-rewrite-surface="long_ads"' in document

    # Operator cards replace raw module rows in Command Center.
    assert 'data-operator-cards="true"' in document
    for module_id in ("product_lab", "economics", "shopify_studio", "marketing_engine", "safety_claim_guard"):
        assert f'data-operator-card="{module_id}"' in document

    # Snapshot names the concrete gaps from the contract.
    assert "fotos_reales_producto" in document
    assert "confirmacion_stock_proveedor" in document

    # Honesty footer.
    assert "operador-en-control" in document


# --- 3c. recommended amplifies the full system surface (I1B-R2) -------------------

R2_AMPLIFICATION_MARKERS = (
    "commercial_intelligence_brief",
    "synapse_already_did",
    "publish_blockers",
    "operator_first_move",
    "synapse_refuses_to_do",
    "anticipation_queue",
    "capability_surface_strip",
    "commercial_readiness_stack",
    "shopify_listing_builder",
    "shopify_payload_copy",
    "no_live_publish",
    "marketing_war_room",
    "marketing_payload_copy",
    "rewrites_pending",
    "claim_guard_adjacent",
    "testing_plan_with_thresholds",
    "input_support_map",
    "evidence_black_box",
    "provenance",
    "safety_boundary",
    "operator_in_control",
)


def test_recommended_amplifies_full_system_surface() -> None:
    document = _render("recommended")

    for marker in R2_AMPLIFICATION_MARKERS:
        assert marker in document, f"missing R2 amplification marker: {marker}"

    # The brief tells the operator what the system did, from real fields only.
    assert "SYNAPSE Commercial Brief" in document
    assert "Evaluo el margen de contribucion" in document
    assert "Clasifico la riqueza del brief" in document
    assert "Construyo el borrador del Shopify pack" in document
    assert "Construyo el marketing pack" in document
    assert "rewrites seguros" in document
    assert "Preservo el boundary" in document

    # Anticipation queue explains why/unlocks/prevents per action.
    assert "Por que importa:" in document
    assert "Que desbloquea:" in document
    assert "Que riesgo evita:" in document

    # Readiness stack covers the seven commercial steps.
    for step in (
        "product_lab",
        "economics",
        "shopify_studio",
        "marketing_engine",
        "safety_claim_guard",
        "evidence",
        "learning_feedback",
    ):
        assert f'data-stack-step="{step}"' in document, f"stack missing step: {step}"

    # Refusals stay explicit (anti-overclaim surface).
    assert "product_market_fit" in document
    assert "autonomous_spend" in document


# --- 3d. R3 premium operator OS shell (I1B-R3) -------------------------------------

R3_PREMIUM_MARKERS = (
    # session gate + local memory (explicitly NOT real authentication)
    "operator_session_gate",
    "local_session_only",
    "operator_alias_memory",
    "browser_local_memory",
    "local_only_persistence",
    "localStorage",
    # top cockpit
    "premium_top_cockpit",
    "money_metrics_bar",
    "safety_boundary_chip",
    # executive operating brief
    "executive_operating_brief",
    "commercial_verdict_card",
    "money_readiness_card",
    "risk_control_card",
    "trust_boundary_card",
    # anticipation playbook
    "anticipation_playbook",
    "persisted_checklist",
    "unlocks",
    "prevents",
    # brain map
    "synapse_brain_map",
    "system_capability_nodes",
    "real_now",
    "fixture_only",
    "future_or_not_connected",
    "forbidden_to_claim",
    # premium shopify builder
    "premium_shopify_builder",
    "listing_preview",
    "publish_readiness_checklist",
    "payload_drawer",
    "shopify_payload_copy",
    "no_live_publish",
    # marketing war room
    "premium_marketing_war_room",
    "strategy_snapshot",
    "angle_cards",
    "hooks_bank",
    "ad_copy_console",
    "channel_script_pack",
    "no_spend_boundary",
    "marketing_payload_copy",
    # evidence black box
    "premium_evidence_black_box",
    "evidence_chain",
    "provenance",
    "deterministic_renderer",
    "no_runtime_network",
    "safety_boundary",
    "operator_in_control",
)


def test_recommended_renders_premium_operator_os() -> None:
    document = _render("recommended")

    for marker in R3_PREMIUM_MARKERS:
        assert marker in document, f"missing R3 premium marker: {marker}"

    # Session gate is local-only and never claims real authentication.
    assert "SYNAPSE Operator Session" in document
    assert "No es autenticacion real" in document
    assert "Entrar al Workbench" in document
    assert 'id="operator_alias_input"' in document
    assert "data-session-reset" in document
    for phrase in ("login seguro", "autenticacion segura", "password", "contrasena"):
        assert phrase not in document.lower(), f"security claim leaked: {phrase}"

    # Money metrics are formatted as financial figures from fixture economics.
    assert "MXN 152.00" in document  # contribution margin
    assert "Breakeven CPA" in document
    assert "43.6%" in document

    # Playbook actions carry unlocks/prevents context and local persistence.
    assert "data-unlocks=" in document
    assert "data-prevents=" in document
    assert 'class="prio"' in document

    # Brain map nodes declare their tier from the contract, boundaries included.
    assert 'data-brain-node="shopify_publish_flow"' in document
    assert 'data-brain-node="no_spend"' in document
    assert 'data-node-tier="forbidden_to_claim"' in document
    assert "BOUNDARY ACTIVO" in document

    # Evidence chain is deterministic and names the frozen fixture.
    assert 'data-marker="evidence_chain"' in document
    assert "Cadena de evidencia" in document

    # Local memory is labeled as browser-local, never as an account.
    assert "Memoria local del navegador" in document
    assert "Sin backend - sin cuenta - sin autenticacion real" in document


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_all_states_keep_session_gate_and_cockpit_honest(name: str) -> None:
    document = _render(name)

    # The OS shell (gate, cockpit, brain map, local-memory footer) renders in
    # every state without faking data.
    assert 'data-marker="operator_session_gate"' in document
    assert 'data-marker="premium_top_cockpit"' in document
    assert 'data-marker="synapse_brain_map"' in document
    assert "browser_local_memory" in document
    assert "No es autenticacion real" in document


# --- 3e. R4 functional operator workspace (I1B-R4) ---------------------------------

R4_FUNCTIONAL_MARKERS = (
    # candidate selector / switcher
    "product_selector",
    "candidate_switcher",
    "candidate_list",
    "selected_candidate_state",
    "candidate_comparison",
    # editable drafts + persistence
    "editable_operator_drafts",
    "local_draft_editor",
    "draft_dirty_state",
    "reset_to_system_output",
    "operator_notes",
    "browser_local_memory",
    "localStorage",
    # copy / export workflow
    "selling_packet_export",
    "copy_full_selling_packet",
    "supplier_confirmation_message",
    "shopify_listing_packet",
    "marketing_packet",
    "claim_safe_copy_packet",
    # functional marketing engine
    "functional_marketing_engine",
    "recommended_first_angle",
    "copy_priority_order",
    "rewrite_queue",
    "claim_safe_version",
    "manual_test_plan",
    "expected_signal",
    "failure_signal",
    "manual_observation_notes",
    "no_fake_performance_claims",
    # functional shopify studio
    "functional_shopify_studio",
    "listing_editor",
    "listing_preview",
    "missing_assets_checklist",
    "publish_readiness_checklist",
    "no_live_publish",
    # command center hub
    "command_center_hub",
    "local_progress_summary",
    "checklist_progress",
    "draft_progress",
    "anticipation_playbook",
)


def test_recommended_is_functional_operator_workspace() -> None:
    document = _render("recommended")

    for marker in R4_FUNCTIONAL_MARKERS:
        assert marker in document, f"missing R4 functional marker: {marker}"

    # Editable local drafts: real inputs/textareas seeded with system output.
    for field in (
        "shopify_title",
        "shopify_subtitle",
        "shopify_price_note",
        "shopify_bullets",
        "shopify_short_description",
        "shopify_long_description",
        "shopify_seo_title",
        "shopify_seo_meta_description",
        "marketing_hooks",
        "marketing_headlines",
        "marketing_primary_texts",
        "marketing_short_ads",
        "marketing_long_ads",
        "marketing_captions",
        "marketing_observation_notes",
        "operator_notes",
    ):
        assert f'data-draft-field="{field}"' in document, f"missing draft field: {field}"
    assert "<textarea" in document
    assert 'data-draft-reset="shopify_listing"' in document
    assert 'data-draft-reset="marketing_copy"' in document
    # Drafts are explicitly local-only and never engine recomputation.
    assert "no modifican el fixture" in document
    assert "no recalcula" in document

    # Selector shows the embedded candidate with money + next action context.
    assert 'data-candidate-select="a8_r109a_recommended"' in document
    assert "margen/unidad" in document

    # Export workflow: full packet + individual packets, copy-ready.
    assert 'id="packet_full"' in document
    assert "SELLING PACKET LOCAL" in document
    assert "data-append-drafts" in document
    assert 'data-copy-target="packet_supplier_sh"' in document

    # Functional marketing: risk-adjusted first angle, no efficacy claims.
    assert "risk-adjusted first angle" in document
    assert "Sin datos de rendimiento reales" in document
    assert 'id="lab_firsttest"' in document

    # Candidate roots scope local memory per fixture.
    assert 'data-candidate-root="a8_r109a_recommended"' in document


# --- 3f. R4 workspace mode: multi-candidate embedded switcher ----------------------

def _render_workspace() -> str:
    view_models = [_build(name) for name in FIXTURE_NAMES]
    return wb_visual.render_workspace_html(view_models)


def test_workspace_mode_embeds_and_switches_candidates() -> None:
    document = _render_workspace()

    assert document.startswith("<!DOCTYPE html>")
    assert 'data-mode="workspace_mode"' in document
    assert "workspace_mode" in document

    # All four fixture states embedded as candidate roots.
    for name in FIXTURE_NAMES:
        assert f'data-candidate-root="a8_r109a_{name}"' in document, name
        assert f'data-candidate-select="a8_r109a_{name}"' in document, name

    # Preparable candidate is selected by default; the others start hidden.
    assert (
        'data-candidate-root="a8_r109a_recommended" data-default-module="command_center">'
        in document
    )
    for name in ("blocked", "low_input", "empty_shortlist"):
        assert (
            f'data-candidate-root="a8_r109a_{name}"'
            f' data-default-module="{"blocked_queue" if name == "blocked" else "command_center"}" hidden>'
            in document
        ), f"{name} must start hidden"

    # Selector card facts: product names, states, and blocker context coexist.
    assert "Organizador de Cables Magnetico Pro" in document
    assert "Parche Reductor Detox Nocturno" in document
    assert "Sin candidato en shortlist" in document
    assert 'data-marker="candidate_comparison"' in document
    assert 'data-marker="selected_candidate_state"' in document

    # State protections survive embedding: blocked copy stays suppressed and
    # the blocked candidate still opens on its blocked queue.
    assert 'data-copy-suppressed="shopify_pack"' in document
    assert "blocked_editing_disabled" in document
    assert "empty_state_no_product" in document
    assert "enrichment_workspace" in document

    # Deterministic and clean.
    assert document == _render_workspace(), "workspace render must be deterministic"
    for token in _forbidden_network_tokens() + _forbidden_write_tokens():
        assert token not in document, f"forbidden token in workspace HTML: {token}"
    assert wb_renderer.scan_forbidden_tokens(document) == []


def test_cli_renders_workspace(tmp_path: Path) -> None:
    output_path = tmp_path / "workspace.html"
    exit_code = wb_visual.main(
        ["--fixture-dir", str(FIXTURE_DIR), "--output", str(output_path)]
    )
    assert exit_code == 0
    assert output_path.is_file()
    assert output_path.read_text(encoding="utf-8") == _render_workspace()


# --- 3g. R5 evidence separation + marker alignment (I1B-R5-FIX1) -------------------

DRAWER_START = "<!--EVIDENCE_DRAWER_START-->"
DRAWER_END = "<!--EVIDENCE_DRAWER_END-->"

# Technical audit surfaces that must never leak into the commercial main stage.
MAIN_STAGE_FORBIDDEN_TECH_MARKERS = (
    'data-contract-section="input_support_map"',
    "Mapa de soporte de inputs",
    'data-audit="source_fields"',
    'data-contract-section="provenance"',
    'data-contract-section="capability_surface_map"',
    'data-audit="score_explanation"',
    'data-audit="assumptions_ledger"',
)

# The same surfaces must stay available for audit inside the drawer.
DRAWER_REQUIRED_TECH_MARKERS = (
    'data-contract-section="input_support_map"',
    'data-contract-section="provenance"',
    'data-audit="source_fields"',
    'data-contract-section="capability_surface_map"',
    'data-audit="score_explanation"',
    'data-audit="assumptions_ledger"',
)


def _split_drawers(document: str) -> tuple[str, str]:
    """Split a rendered document into (main stage, concatenated drawer HTML)."""
    main_parts: list[str] = []
    drawer_parts: list[str] = []
    rest = document
    while DRAWER_START in rest:
        before, _sep, tail = rest.partition(DRAWER_START)
        drawer, _sep, rest = tail.partition(DRAWER_END)
        main_parts.append(before)
        drawer_parts.append(drawer)
    main_parts.append(rest)
    return "".join(main_parts), "".join(drawer_parts)


def test_recommended_first_angle_is_the_official_marker() -> None:
    # recommended_first_angle is the official marker for the first recommended
    # angle; the shorter legacy name is not required and never emitted as an
    # attribute of its own.
    document = _render("recommended")
    assert 'data-marker="recommended_first_angle"' in document
    assert 'data-marker="recommended_angle"' not in document

    workspace = _render_workspace()
    assert 'data-marker="recommended_first_angle"' in workspace
    assert 'data-marker="recommended_angle"' not in workspace


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_technical_audit_lives_only_in_evidence_drawer(name: str) -> None:
    document = _render(name)
    main_stage, drawers = _split_drawers(document)
    assert drawers, "evidence drawer must be present"
    for marker in MAIN_STAGE_FORBIDDEN_TECH_MARKERS:
        assert marker not in main_stage, (
            f"technical audit marker leaked into main stage ({name}): {marker}"
        )
    for marker in DRAWER_REQUIRED_TECH_MARKERS:
        assert marker in drawers, f"drawer missing technical marker ({name}): {marker}"


def test_workspace_keeps_evidence_separation() -> None:
    main_stage, drawers = _split_drawers(_render_workspace())
    assert drawers, "workspace must embed evidence drawers"
    for marker in MAIN_STAGE_FORBIDDEN_TECH_MARKERS:
        assert marker not in main_stage, (
            f"technical audit marker leaked into workspace main stage: {marker}"
        )
    for marker in DRAWER_REQUIRED_TECH_MARKERS:
        assert marker in drawers, f"workspace drawer missing technical marker: {marker}"


def test_marketing_main_keeps_commercial_support_summary() -> None:
    document = _render("recommended")
    main_stage, _drawers = _split_drawers(document)

    assert 'data-marker="commercial_copy_support"' in main_stage
    assert "Soporte comercial del copy" in main_stage
    assert "Que facts soportan esta estrategia" in main_stage
    assert "Copy respaldado por datos del producto" in main_stage
    assert "Que inputs faltan antes de confiar en el copy" in main_stage
    # Commercial wording only: never the raw technical support-row format.
    assert "NO SOPORTADO: fallback generico" not in main_stage


# --- 3h. R6 premium surface / operator power pass (A8-R109B-R6) --------------------

R6_PREMIUM_SURFACE_MARKERS = (
    # economics cockpit
    "money_cockpit",
    "kpi_strip",
    "margin_waterfall",
    "guardrail_console",
    "local_static_simulator",
    "sensitivity_grid",
    # pipeline operational board
    "pipeline_stage_track",
    # shopify power surfaces
    "publish_gap_console",
    "storefront_preview",
    # marketing hierarchy
    "dominant_angle",
    "challenger_angle",
    "hook_leaderboard",
    "rewrite_action_row",
)


def test_recommended_premium_surface_power_pass() -> None:
    document = _render("recommended")

    for marker in R6_PREMIUM_SURFACE_MARKERS:
        assert marker in document, f"missing R6 premium surface marker: {marker}"

    # Economics reads like a cockpit: hero KPI band, floor marker on the
    # waterfall, executive guardrail tiles, and a static local simulator that
    # declares itself local (no engine recompute, no market data).
    assert 'class="kpi-hero"' in document
    assert 'class="wf-floor"' in document
    assert "Guardrail console" in document
    assert "Perdida maxima teorica del primer test" in document
    assert "Simulador local de margen" in document
    assert "sin recalculo del motor" in document

    # Pipeline: featured recommended card + stage-track segments per candidate.
    assert 'data-candidate-kind="recommended"' in document
    assert 'class="st-seg' in document

    # Shopify: publish gaps named from the contract, storefront-chrome preview
    # explicitly labeled as a local, unpublished draft.
    assert "pendientes antes de publicar" in document
    assert 'class="gap-count"' in document
    assert 'class="lp-chrome"' in document
    assert "no publicado" in document

    # Marketing: dominant/challenger hierarchy, leaderboard honest about pack
    # order, actionable rewrite queue (copy claim-safe version + local check),
    # denser tabs with honest counters.
    assert "ANGULO DOMINANTE - P1" in document
    assert "CHALLENGER - P2" in document
    assert "nunca rendimiento" in document
    assert 'data-copy-target="rw_q_headlines"' in document
    assert 'data-local-check="rewrite_headlines"' in document
    assert '<span class="tab-count">' in document


def test_r6_operator_controls_are_wired_locally() -> None:
    # The evidence drawer and angle-choice buttons must have matching handlers
    # in the inline script (local-only interactions; still zero network).
    document = _render("recommended")
    assert "data-drawer-open" in document
    assert "data-evidence-drawer" in document
    assert "data-select-angle" in document
    for js_hook in (
        '[data-drawer-open]',
        '[data-drawer-close]',
        '[data-select-angle]',
        "r109b_angles_",
    ):
        assert js_hook in document, f"missing local JS wiring: {js_hook}"


def test_r6_keeps_state_protections() -> None:
    blocked = _render("blocked")
    # A blocked product never gets sell-prep power surfaces or actionable
    # rewrite copy targets.
    assert "publish_gap_console" not in blocked
    assert "storefront_preview" not in blocked
    assert 'data-marker="rewrite_action_row"' not in blocked
    assert 'data-copy-target="rw_q_' not in blocked
    assert 'data-copy-target="rw_main_' not in blocked

    empty = _render("empty_shortlist")
    # An empty shortlist invents no cockpit guardrails, simulator, marketing
    # hierarchy, or publish-gap console.
    assert "guardrail_console" not in empty
    assert "local_static_simulator" not in empty
    assert "dominant_angle" not in empty
    assert "hook_leaderboard" not in empty
    assert "publish_gap_console" not in empty
    assert "storefront_preview" not in empty


# --- 4. blocked: queue/safety dominate; no prepare CTA ---------------------------

def test_blocked_state_dominates_without_prepare_cta() -> None:
    document = _render("blocked")

    assert 'data-contract-section="blocked_queue_summary"' in document
    assert "Parche Reductor Detox Nocturno" in document
    assert "CLAIM_PROHIBITED_HEALTH" in document

    # Never a ready-to-prepare CTA on a blocked product.
    assert 'data-cta="prepare"' not in document
    assert "NUNCA LISTOS PARA PREPARAR" in document

    # Blocked module opens first and copy is suppressed in both studios.
    assert '<section id="blocked_queue" data-module="blocked_queue" class="module active">' in document
    assert 'data-copy-suppressed="shopify_pack"' in document
    assert 'data-copy-suppressed="marketing_pack"' in document
    assert "COPY BLOQUEADO POR CLAIMS PROHIBIDOS" in document

    # No sell-prep affordances on a blocked product (I1B-R1).
    assert 'data-contract-section="selling_pack_snapshot"' not in document
    assert 'data-no-publish="true"' not in document, "blocked keeps the hard NO PUBLICAR banner"
    assert "Preparar venta con operador-en-control" not in document

    # No commercial brief either: the brief is a preparable-product surface (I1B-R2).
    assert "commercial_intelligence_brief" not in document
    assert 'data-marker="no_live_publish"' not in document

    # R3: no copy-ready payload sections at all on a blocked product; the
    # suppressed placeholders never carry the copy-ready markers.
    assert "shopify_payload_copy" not in document
    assert "marketing_payload_copy" not in document
    assert 'data-marker="payload_drawer"' not in document
    assert 'data-marker="listing_preview"' not in document
    assert "executive_operating_brief" not in document
    assert "commercial_verdict_card" not in document

    # R4: editing disabled, repair/reject only, no selling packet as ready.
    assert 'data-marker="blocked_editing_disabled"' in document
    assert 'data-marker="repair_or_reject_only"' in document
    assert "no utilizable hasta reparar" in document
    assert 'data-marker="listing_editor"' not in document
    assert 'data-draft-field="shopify_title"' not in document
    assert 'data-draft-field="marketing_hooks"' not in document
    assert "selling_packet_export" not in document
    assert "copy_full_selling_packet" not in document
    assert "supplier_confirmation_message" not in document
    assert 'data-packet-unavailable="true"' in document
    # Operator notes remain the only editable surface.
    assert 'data-draft-field="operator_notes"' in document


# --- 5. low_input: enrichment gaps and degraded confidence visible ----------------

def test_low_input_shows_enrichment_and_warnings() -> None:
    document = _render("low_input")

    assert "INPUT_LOW" in document
    assert wb_vm.LOW_INPUT_WARNING in document
    assert 'data-enrichment-gaps="true"' in document
    assert "enrich_input_" in document  # enrichment actions from the action queue
    assert 'data-cta="prepare"' not in document
    assert "generic_low_confidence" in document
    # No sell-prep snapshot without a preparable product (I1B-R1).
    assert 'data-contract-section="selling_pack_snapshot"' not in document
    # R3: enrichment-first, no executive brief implying a preparable product.
    assert "executive_operating_brief" not in document
    # R4: enrichment workspace with local notes; no full selling packet.
    assert 'data-marker="enrichment_workspace"' in document
    assert 'data-draft-field="enrichment_notes"' in document
    assert "Necesita enriquecimiento antes del sell-prep" in document
    assert "selling_packet_export" not in document
    assert "copy_full_selling_packet" not in document
    assert 'data-packet-unavailable="true"' in document


# --- 6. empty_shortlist: nothing fake ---------------------------------------------

def test_empty_shortlist_invents_nothing() -> None:
    document = _render("empty_shortlist")

    assert "Sin candidato en shortlist" in document
    assert 'data-cta="prepare"' not in document
    assert '<button type="button" class="copy-btn" data-copy-button' not in document, (
        "no copy buttons without a product"
    )
    assert 'data-copy-target="payload_' not in document
    assert 'data-shopify-disabled="true"' in document
    assert 'data-marketing-disabled="true"' in document
    assert "no_recommended_product_in_shortlist" in document
    # No product copy from other fixtures can leak in.
    assert "Organizador de Cables" not in document
    assert "Parche Reductor" not in document
    # No sell-prep snapshot without a product (I1B-R1).
    assert 'data-contract-section="selling_pack_snapshot"' not in document
    # R3: no fake listing preview, payload drawer, or money metrics either.
    assert 'data-marker="listing_preview"' not in document
    assert 'data-marker="payload_drawer"' not in document
    assert "Sin metricas de dinero" in document
    assert "executive_operating_brief" not in document
    # R4: explicit empty state, no product editor, no packets.
    assert 'data-marker="empty_state_no_product"' in document
    assert 'data-marker="listing_editor"' not in document
    assert 'data-draft-field="shopify_title"' not in document
    assert 'data-draft-field="marketing_hooks"' not in document
    assert "selling_packet_export" not in document
    assert "copy_full_selling_packet" not in document
    assert 'data-packet-unavailable="true"' in document


# --- 7. forbidden tokens: rendered output and R109B source files ------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_rendered_visual_has_no_forbidden_network_tokens(name: str) -> None:
    document = _render(name)
    for token in _forbidden_network_tokens():
        assert token not in document, f"forbidden network token in visual HTML: {token}"
    assert wb_renderer.scan_forbidden_tokens(document) == []
    # Inline script allowed, external script never.
    assert "<script>" in document


@pytest.mark.parametrize("path", R109B_FILES, ids=lambda p: p.name)
def test_r109b_files_have_no_forbidden_tokens(path: Path) -> None:
    assert path.is_file(), f"missing R109B file: {path}"
    content = path.read_text(encoding="utf-8")
    for token in _forbidden_network_tokens() + _forbidden_write_tokens():
        assert token not in content, f"forbidden token {token!r} in {path.name}"


# --- 8. status badges come from the contract, not renderer inference ---------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_rail_badges_match_module_status_summary(name: str) -> None:
    data = _build(name).to_dict()
    document = _render(name)
    for entry in data["module_status_summary"]:
        module_id = entry["module_id"]
        status = entry["status"]
        assert (
            f'data-nav-module="{module_id}" data-module-status="{status}"' in document
        ), f"rail must carry contract status for {module_id}"


# --- 9. deterministic CLI render ----------------------------------------------------

def test_cli_renders_single_fixture(tmp_path: Path) -> None:
    output_path = tmp_path / "recommended.html"
    exit_code = wb_visual.main(
        ["--fixture", str(_fixture_path("recommended")), "--output", str(output_path)]
    )
    assert exit_code == 0
    assert output_path.is_file()
    assert output_path.read_text(encoding="utf-8") == _render("recommended")


def test_cli_renders_fixture_dir(tmp_path: Path) -> None:
    exit_code = wb_visual.main(
        ["--fixture-dir", str(FIXTURE_DIR), "--output-dir", str(tmp_path)]
    )
    assert exit_code == 0
    for name in FIXTURE_NAMES:
        target = tmp_path / f"{name}.html"
        assert target.is_file()
        assert target.read_text(encoding="utf-8") == _render(name)
