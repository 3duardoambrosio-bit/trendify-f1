"""A8-R109A — Workbench data contract + deterministic offline renderer tests.

Covers: fixture parsing, ViewModel contract, determinism, self-contained HTML,
forbidden-token scans, input richness (R105.3), blocked queue, claim guard
adjacency, provenance/safety, byte-exact copy payloads, and the render CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synapse.ui import operator_workbench_renderer as wb_renderer
from synapse.ui import operator_workbench_view_model as wb_vm

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "a8_r109a"
DOC_PATH = REPO_ROOT / "docs" / "a8_r109a" / "WORKBENCH_DATA_RENDERER_CONTRACT.md"

FIXTURE_NAMES = ("recommended", "blocked", "low_input", "empty_shortlist")

R109A_FILES = (
    REPO_ROOT / "synapse" / "ui" / "operator_workbench_view_model.py",
    REPO_ROOT / "synapse" / "ui" / "operator_workbench_renderer.py",
    Path(__file__).resolve(),
    DOC_PATH,
) + tuple(FIXTURE_DIR / f"{name}.json" for name in FIXTURE_NAMES)

REQUIRED_TOP_LEVEL_FIELDS = (
    "schema_version",
    "fixture_id",
    "render_mode",
    "source_kind",
    "generated_at_policy",
    "product",
    "decision",
    "economics",
    "scores",
    "input_richness",
    "claim_guard",
    "shopify_pack",
    "marketing_pack",
    "learning_plan",
    "blocked_queue",
    "operator_actions",
    "provenance",
    "safety_boundary",
    "evidence",
    "copy_payloads",
)

REQUIRED_SHOPIFY_FIELDS = (
    "title",
    "subtitle",
    "short_description",
    "long_description",
    "bullets",
    "benefits",
    "specifications",
    "faq",
    "seo_title",
    "seo_meta_description",
    "handle",
    "tags",
    "category",
    "price",
    "compare_at_price",
    "shipping_note",
    "refund_claim_note",
    "claim_safe_disclaimer",
    "image_checklist",
    "publish_checklist",
    "missing_inputs",
)

REQUIRED_MARKETING_FIELDS = (
    "strategy_summary",
    "core_angle",
    "why_this_angle",
    "buyer_profile",
    "audience",
    "pain_points",
    "desire",
    "objections",
    "hooks",
    "headlines",
    "primary_texts",
    "short_ads",
    "long_ads",
    "captions",
    "ugc_scripts",
    "video_scripts",
    "image_ad_concepts",
    "channel_packs",
    "testing_plan",
    "claim_guard",
    "confidence",
    "input_richness_warning",
    # Marketing Pack V2 depth (A8-R109A-I2)
    "angle_matrix",
    "creative_hypotheses",
    "claim_risk_by_copy",
    "input_support_map",
    "missing_marketing_inputs",
    "confidence_by_section",
    "testing_plan_with_thresholds",
)

REQUIRED_ANGLE_FIELDS = (
    "angle_id",
    "angle_name",
    "promise_type",
    "target_segment",
    "pain_addressed",
    "desire_addressed",
    "objection_addressed",
    "proof_needed",
    "claim_risk",
    "safe_wording",
    "why_it_might_work",
    "why_it_might_fail",
)

REQUIRED_HYPOTHESIS_FIELDS = (
    "hypothesis_id",
    "hypothesis",
    "variable_tested",
    "expected_signal",
    "failure_signal",
    "minimum_evidence_needed",
    "channel",
    "linked_angle_id",
)

REQUIRED_COPY_RISK_FIELDS = (
    "copy_key",
    "risk_level",
    "risky_terms",
    "prohibited_terms",
    "safe_rewrite",
    "reason",
)

REQUIRED_CONFIDENCE_SECTIONS = (
    "strategy_confidence",
    "hook_confidence",
    "ad_copy_confidence",
    "channel_pack_confidence",
    "claim_safety_confidence",
    "testing_plan_confidence",
)

REQUIRED_LEARNING_FIELDS = (
    "hypotheses",
    "evidence_needed",
    "first_sale_signals",
    "risk_signals",
    "continue_if",
    "review_if",
    "kill_if",
    "operator_observations_schema",
    "no_pmf_claim",
    "no_analytics_fetch",
    "operator_in_control",
)

REQUIRED_SAFETY_FIELDS = (
    "fase_1_read_only",
    "dry_run",
    "no_live_writes",
    "no_spend",
    "no_fulfillment",
    "no_shopify_live",
    "no_dropi_live",
    "no_meta_live",
    "no_credentials_required",
    "no_external_network",
    "operator_in_control",
    "future_gate_required_for_live",
)

REQUIRED_PROVENANCE_FIELDS = (
    "source_fixture",
    "source_kind",
    "adapter_status",
    "base_head",
    "fase_1_status",
    "island",
    "deterministic_renderer",
    "no_runtime_network",
    "no_runtime_clock",
    "copy_payload_count",
    "evidence_notes",
)

REQUIRED_COPY_PAYLOAD_KEYS = (
    "shopify_title",
    "shopify_price",
    "shopify_short_description",
    "shopify_long_description",
    "shopify_bullets",
    "shopify_full_pack",
    "marketing_hooks",
    "marketing_short_ads",
    "marketing_long_ads",
    "marketing_full_pack",
    "marketing_full_pack_v2",
    "learning_snapshot",
    "safety_summary",
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
    return wb_renderer.render_workbench_html(_build(name))


def _section_html(document: str, section_id: str) -> str:
    marker = f'<section id="{section_id}"'
    start = document.index(marker)
    end = document.index("</section>", start)
    return document[start:end]


# --- 1. fixtures exist and parse ---------------------------------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_exists_and_parses(name: str) -> None:
    path = _fixture_path(name)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data["fixture_id"] == f"a8_r109a_{name}"
    assert data["source_kind"] == "frozen_local_fixture"


# --- 2. ViewModel builds with the full contract -------------------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_view_model_builds_with_required_contract(name: str) -> None:
    view_model = _build(name)
    data = view_model.to_dict()

    for field_name in REQUIRED_TOP_LEVEL_FIELDS:
        assert field_name in data, f"missing top-level field: {field_name}"

    assert data["schema_version"] == wb_vm.SCHEMA_VERSION
    assert data["render_mode"] == "offline_static_html"
    assert data["generated_at_policy"] == "deterministic_no_runtime_clock"

    for field_name in REQUIRED_SHOPIFY_FIELDS:
        assert field_name in data["shopify_pack"], f"shopify_pack missing: {field_name}"
    for field_name in REQUIRED_MARKETING_FIELDS:
        assert field_name in data["marketing_pack"], f"marketing_pack missing: {field_name}"
    for field_name in REQUIRED_LEARNING_FIELDS:
        assert field_name in data["learning_plan"], f"learning_plan missing: {field_name}"

    assert isinstance(data["blocked_queue"], list)
    assert isinstance(data["operator_actions"], list)


# --- 3. ViewModel determinism --------------------------------------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_view_model_deterministic_for_repeated_builds(name: str) -> None:
    first = _build(name)
    second = _build(name)
    assert first == second
    assert first.to_json() == second.to_json()
    assert first.to_dict() == second.to_dict()


# --- 4. renderer determinism ----------------------------------------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_renderer_deterministic_for_repeated_renders(name: str) -> None:
    assert _render(name) == _render(name)


# --- 5. rendered HTML self-contained ---------------------------------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_rendered_html_self_contained(name: str) -> None:
    document = _render(name)
    assert document.startswith("<!DOCTYPE html>")
    assert document.rstrip().endswith("</html>")
    assert "<style>" in document  # inline CSS only
    assert "<script" not in document  # R109A renders without any script
    for section_id in wb_renderer.SECTION_ORDER:
        assert f'<section id="{section_id}"' in document, f"missing section: {section_id}"


# --- 6. forbidden network tokens absent from renderer output ----------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_rendered_html_has_no_forbidden_network_tokens(name: str) -> None:
    document = _render(name)
    for token in _forbidden_network_tokens():
        assert token not in document, f"forbidden network token in HTML: {token}"
    assert wb_renderer.scan_forbidden_tokens(document) == []


# --- 7. forbidden tokens absent from R109A source files ----------------------------

@pytest.mark.parametrize("path", R109A_FILES, ids=lambda p: p.name)
def test_r109a_files_have_no_forbidden_tokens(path: Path) -> None:
    assert path.is_file(), f"missing R109A file: {path}"
    content = path.read_text(encoding="utf-8")
    for token in _forbidden_network_tokens() + _forbidden_write_tokens():
        assert token not in content, f"forbidden token {token!r} in {path.name}"


# --- 8. input richness classifications ----------------------------------------------

def test_input_richness_classifications() -> None:
    recommended = _build("recommended").to_dict()["input_richness"]
    low_input = _build("low_input").to_dict()["input_richness"]

    assert recommended["classification"] in ("INPUT_RICH", "INPUT_PARTIAL")
    assert recommended["classification"] == "INPUT_RICH"
    assert recommended["warning"] == ""

    assert low_input["classification"] == "INPUT_LOW"
    assert low_input["filled_count"] < low_input["total_fields"]


# --- 9. low_input warning + low-confidence copy ---------------------------------------

def test_low_input_warning_and_low_confidence() -> None:
    data = _build("low_input").to_dict()
    warning = wb_vm.LOW_INPUT_WARNING

    assert data["input_richness"]["warning"] == warning
    assert data["marketing_pack"]["input_richness_warning"] == warning

    confidence = data["marketing_pack"]["confidence"]
    assert confidence["level"] == "low"
    assert confidence["expert_method_applied"] is False

    document = _render("low_input")
    assert warning in document

    enrich_actions = [
        action for action in data["operator_actions"] if action["kind"] == "enrich_input"
    ]
    assert enrich_actions, "low_input must expose enrichment operator actions"
    assert all(action["target"].startswith("operator_input.") for action in enrich_actions)


# --- 10. blocked fixture populates blocked_queue ----------------------------------------

def test_blocked_fixture_creates_blocked_queue() -> None:
    data = _build("blocked").to_dict()
    queue = data["blocked_queue"]
    assert len(queue) >= 1

    item = queue[0]
    for key in (
        "product_name",
        "reason",
        "reason_codes",
        "severity",
        "operator_actions",
        "can_recover",
        "safety_boundary",
    ):
        assert key in item, f"blocked_queue item missing: {key}"

    assert item["product_name"] == "Parche Reductor Detox Nocturno"
    assert item["reason_codes"] == ["CLAIM_PROHIBITED_HEALTH", "MARGIN_BELOW_FLOOR"]
    assert item["severity"] == "high"
    assert item["can_recover"] is True

    kinds = {action["kind"] for action in item["operator_actions"]}
    assert "reject_product" in kinds
    assert kinds & {"repair_claims", "repair_economics"}

    document = _render("blocked")
    blocked_section = _section_html(document, "blocked-queue")
    assert "Parche Reductor Detox Nocturno" in blocked_section

    for name in ("recommended", "low_input", "empty_shortlist"):
        assert _build(name).to_dict()["blocked_queue"] == []


# --- 11. empty_shortlist creates no fake copy ---------------------------------------------

def test_empty_shortlist_has_no_fake_product_copy() -> None:
    data = _build("empty_shortlist").to_dict()

    assert data["product"] == {}
    assert data["shopify_pack"]["enabled"] is False
    assert data["shopify_pack"]["disabled_reason"] == "no_recommended_product_in_shortlist"
    assert data["shopify_pack"]["title"] == ""
    assert data["shopify_pack"]["bullets"] == []

    assert data["marketing_pack"]["enabled"] is False
    assert data["marketing_pack"]["hooks"] == []
    assert data["marketing_pack"]["short_ads"] == []

    assert data["copy_payloads"]["enabled"] is False
    assert data["copy_payloads"]["disabled_reason"] == "no_recommended_product_in_shortlist"
    assert data["copy_payloads"]["items"] == []
    assert data["copy_payloads"]["count"] == 0

    next_actions = [a for a in data["operator_actions"] if a["kind"] == "build_shortlist"]
    assert next_actions, "empty shortlist must explain the next action"

    # Safety/provenance/evidence shell must survive the empty state.
    assert data["safety_boundary"]["no_live_writes"] is True
    assert data["provenance"]["island"] == "A8-R109A"
    assert data["evidence"]["notes"]

    document = _render("empty_shortlist")
    assert "shortlist esta vacia" in document


# --- 12/13. claim guard adjacency in rendered HTML -------------------------------------------

@pytest.mark.parametrize("section_id", ("shopify-pack", "marketing-pack"))
@pytest.mark.parametrize("name", ("recommended", "blocked", "low_input"))
def test_claim_guard_adjacent_to_copy_surfaces(name: str, section_id: str) -> None:
    document = _render(name)
    section = _section_html(document, section_id)
    assert 'class="claim-guard-adjacent"' in section
    assert "Claim Guard (adyacente)" in section

    claim_guard = _build(name).to_dict()["claim_guard"]
    if claim_guard["prohibited_claims"]:
        assert claim_guard["prohibited_claims"][0] in section


def test_claim_guard_data_present_in_view_model_packs() -> None:
    data = _build("recommended").to_dict()
    for key in ("allowed_claims", "risky_claims", "prohibited_claims", "safe_wording",
                "claim_guard_summary"):
        assert key in data["claim_guard"]
    assert data["claim_guard"]["risky_claims"], "recommended must keep at least one risky claim"

    shopify_notes = data["shopify_pack"]["claim_guard_notes"]
    marketing_notes = data["marketing_pack"]["claim_guard"]
    assert shopify_notes["adjacent_to"] == "shopify_pack"
    assert marketing_notes["adjacent_to"] == "marketing_pack"
    assert shopify_notes["summary"] == data["claim_guard"]["claim_guard_summary"]
    assert marketing_notes["summary"] == data["claim_guard"]["claim_guard_summary"]


# --- 14. provenance seal ------------------------------------------------------------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_provenance_seal_present(name: str) -> None:
    data = _build(name).to_dict()
    provenance = data["provenance"]
    for field_name in REQUIRED_PROVENANCE_FIELDS:
        assert field_name in provenance, f"provenance missing: {field_name}"

    assert provenance["base_head"] == "c189cb09f963417596f2b6a02bfbd9e9ae2459a2"
    assert provenance["island"] == "A8-R109A"
    assert provenance["deterministic_renderer"] is True
    assert provenance["no_runtime_network"] is True
    assert provenance["no_runtime_clock"] is True
    assert provenance["source_fixture"].endswith(f"{name}.json")

    document = _render(name)
    seal = _section_html(document, "provenance-seal")
    assert 'class="provenance-seal"' in seal
    assert "SELLO DE PROVENANCE" in seal
    assert provenance["base_head"] in seal


# --- 15. safety boundary --------------------------------------------------------------------------

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_safety_boundary_present_and_true(name: str) -> None:
    data = _build(name).to_dict()
    boundary = data["safety_boundary"]
    for field_name in REQUIRED_SAFETY_FIELDS:
        assert boundary.get(field_name) is True, f"safety_boundary.{field_name} must be True"

    section = _section_html(_render(name), "safety-boundary")
    assert "no_live_writes" in section
    assert "future_gate_required_for_live" in section


# --- 16. copy payload registry ----------------------------------------------------------------------

@pytest.mark.parametrize("name", ("recommended", "blocked", "low_input"))
def test_copy_payload_registry_complete(name: str) -> None:
    payloads = _build(name).to_dict()["copy_payloads"]
    assert payloads["enabled"] is True
    items = {item["key"]: item for item in payloads["items"]}
    assert tuple(items) == REQUIRED_COPY_PAYLOAD_KEYS
    assert payloads["count"] == len(REQUIRED_COPY_PAYLOAD_KEYS)

    for item in items.values():
        for field_name in ("key", "label", "section", "text", "claim_guard_ref", "source_fields"):
            assert field_name in item, f"copy payload missing: {field_name}"
        assert item["source_fields"], "each payload must declare source fields"

    section = _section_html(_render(name), "copy-payload-registry")
    for key in REQUIRED_COPY_PAYLOAD_KEYS:
        assert f'data-payload-key="{key}"' in section


# --- 17. byte-exact copy payloads for the recommended fixture -----------------------------------------

EXPECTED_SHOPIFY_TITLE = "Organizador de Cables Magnetico Pro"

EXPECTED_SHOPIFY_FULL_PACK = """SHOPIFY PACK
============
Producto: Organizador de Cables Magnetico Pro
Subtitulo: Escritorio ordenado sin adhesivos que fallan
Handle: organizador-cables-magnetico-pro
Categoria: Hogar y Oficina > Organizacion
Tags: organizador, cables, home-office, escritorio, magnetico
Precio: MXN 349.00
Precio de comparacion: MXN 449.00

Descripcion corta:
Organizador magnetico para hasta 6 cables de carga y datos. Base con respaldo antideslizante, sin herramientas y sin adhesivos permanentes.

Descripcion larga:
El Organizador de Cables Magnetico Pro mantiene tus cables de carga y datos en su lugar sobre el escritorio o el buro. Sujeta hasta 6 cables segun especificacion del fabricante, con una base magnetica de respaldo antideslizante que se reubica sin danar la superficie. Pensado para home office en Mexico: se instala sin herramientas y sin adhesivos permanentes.

Bullets:
- Sujeta hasta 6 cables de carga y datos.
- Base magnetica con respaldo antideslizante.
- Instalacion sin herramientas ni adhesivos permanentes.
- Compatible con cables USB-A, USB-C y Lightning.
- Tamano compacto para escritorio, buro o cocina.

Beneficios:
- Cables siempre a la mano al momento de cargar.
- Evita pescar cables caidos detras del mueble.
- Se reubica sin danar la superficie.

Especificaciones:
- Material: ABS con iman de neodimio
- Capacidad: 6 ranuras para cable
- Dimensiones: 9.5 x 3.2 x 1.8 cm
- Peso: 48 g

FAQ:
P: Raya o dana el escritorio?
R: No. La base usa respaldo antideslizante reposicionable; no usa adhesivo permanente.
P: Funciona con cables gruesos?
R: Sujeta cables de hasta 5 mm de diametro, el estandar de cables de carga.
P: Cuando llega mi pedido?
R: Tiempos de envio se confirman con el proveedor antes de publicar; este paquete es de preparacion local.

SEO titulo: Organizador de Cables Magnetico Pro | Escritorio sin enredos
SEO meta descripcion: Organizador magnetico para hasta 6 cables. Base antideslizante, instalacion sin herramientas. Ideal para home office.

Nota de envio: Envio nacional estandar; tiempos y costos se confirman con el proveedor antes de publicar.
Nota de devoluciones: Politica de devolucion de 30 dias por defecto; confirmar con el proveedor antes de publicar.
Disclaimer claim-safe: Imagenes de referencia del proveedor. Capacidades sujetas a especificaciones del fabricante.

Inputs faltantes:
- fotos_reales_producto
- confirmacion_stock_proveedor

CLAIM GUARD (Shopify):
Resumen: Riesgo de claims bajo; evitar promesas absolutas y claims de productividad medible.
Permitidos:
- Sujeta hasta 6 cables segun especificacion del fabricante.
- Base magnetica con respaldo antideslizante.
- Instalacion sin herramientas.
Riesgosos:
- "Nunca mas se te caera un cable": promesa absoluta; usar redaccion condicional.
Prohibidos:
- Claims de productividad medible sin evidencia de mercado.
Redaccion segura:
- Usar "ayuda a mantener" en lugar de "garantiza".
- Citar la capacidad como especificacion del fabricante."""

EXPECTED_MARKETING_FULL_PACK = """MARKETING PACK
==============
Resumen de estrategia: Angulo de orden y practicidad para home office; entrada por dolor cotidiano (cables caidos y enredados) con demostracion visual simple.
Angulo central: Deja de pescar cables detras del escritorio.
Por que este angulo: El dolor es visual, universal en home office y demostrable en video corto sin claims de rendimiento.
Perfil del comprador: Persona de 25-45 que trabaja o estudia desde casa en Mexico, con escritorio compartido entre trabajo y uso personal.

Audiencias:
- Personas de 25-45 en Mexico que trabajan o estudian desde casa con escritorio propio.

Dolores:
- Los cables se caen detras del escritorio y hay que pescarlos.
- Cables enredados entre trabajo, celular y tablet.

Deseos:
- Escritorio ordenado sin gastar en muebles nuevos.
- Encontrar cada cable a la mano al momento de cargar.

Objeciones:
- Ya probe organizadores adhesivos y se despegan.
- Parece algo que puedo improvisar con cinta.

Hooks:
- Otra vez se te cayo el cable detras del escritorio?
- Tu escritorio no esta desordenado: le falta esto.
- El accesorio de menos de $350 que ordena tu home office.
- Regalo util de menos de $350: si existe.
- Tu setup merece dejar de pelear con los cables.

Headlines:
- Cables en su lugar, siempre a la mano.
- Orden magnetico para tu escritorio.
- Se acabo pescar cables.

Textos primarios:
- Sujeta hasta 6 cables de carga y datos en un solo modulo compacto. Base magnetica con respaldo antideslizante: se instala sin herramientas y se reubica sin danar tu escritorio.
- Si trabajas desde casa, ya conoces el ritual de pescar el cable que se cayo detras del escritorio. Este organizador magnetico lo mantiene a la mano, junto con otros 5.

Anuncios cortos:
- Cables caidos detras del escritorio? Este organizador magnetico los mantiene a la mano. Hasta 6 cables, sin herramientas.
- Home office ordenado con un solo accesorio: organizador magnetico para 6 cables, base antideslizante.

Anuncios largos:
- El cable siempre se cae en el peor momento. Este organizador magnetico sujeta hasta 6 cables de carga y datos sobre tu escritorio, con base de respaldo antideslizante que se reubica sin danar la superficie. Sin herramientas, sin adhesivos permanentes. Pedido bajo demanda para Mexico.

Captions:
- El fin del cable perdido detras del escritorio.
- 6 cables, un solo lugar.

Guiones UGC:
- Apertura: mostrar el cable cayendo detras del escritorio. Desarrollo: colocar el organizador y acomodar 6 cables. Cierre: jalar un cable y mostrar que el resto queda en su lugar.

Guiones de video:
- Escena 1 (0-3s): cable cayendo detras del escritorio. Escena 2 (3-10s): instalacion sin herramientas. Escena 3 (10-20s): 6 cables ordenados, tiron de prueba. Cierre: oferta y precio.

Conceptos de imagen:
- Antes/despues del escritorio con y sin organizador.
- Primer plano de las 6 ranuras con cables de colores.

Confianza: medium_high (structured_rich_input_no_market_validation)
Nota de confianza: Brief rico; la validacion final requiere datos reales de mercado (Fase 2).

CLAIM GUARD (Marketing):
Resumen: Riesgo de claims bajo; evitar promesas absolutas y claims de productividad medible.
Permitidos:
- Sujeta hasta 6 cables segun especificacion del fabricante.
- Base magnetica con respaldo antideslizante.
- Instalacion sin herramientas.
Riesgosos:
- "Nunca mas se te caera un cable": promesa absoluta; usar redaccion condicional.
Prohibidos:
- Claims de productividad medible sin evidencia de mercado.
Redaccion segura:
- Usar "ayuda a mantener" en lugar de "garantiza".
- Citar la capacidad como especificacion del fabricante."""


EXPECTED_MARKETING_FULL_PACK_V2 = """MARKETING PACK V2
=================
Angulo central: Deja de pescar cables detras del escritorio.
Resumen de estrategia: Angulo de orden y practicidad para home office; entrada por dolor cotidiano (cables caidos y enredados) con demostracion visual simple.

CONFIANZA POR SECCION:
- strategy_confidence: medium_high (resumen de estrategia + matriz de angulos)
- hook_confidence: medium_high (numero y variedad de hooks)
- ad_copy_confidence: medium_high (cobertura de formatos de anuncio)
- channel_pack_confidence: medium_high (channel packs definidos)
- claim_safety_confidence: medium (claims riesgosos senalados por el claim guard)
- testing_plan_confidence: medium_high (umbrales de exito y alto definidos)

MATRIZ DE ANGULOS:
[A1] Dolor cotidiano: el cable perdido
- promise_type: alivio_de_dolor
- target_segment: Home office MX 25-45 con escritorio propio.
- pain_addressed: Los cables se caen detras del escritorio y hay que pescarlos.
- desire_addressed: Encontrar cada cable a la mano al momento de cargar.
- objection_addressed: Ya probe organizadores adhesivos y se despegan.
- proof_needed: Video de demostracion del proveedor mostrando la base antideslizante.
- claim_risk: low
- safe_wording: Ayuda a mantener los cables a la mano; sin promesas absolutas.
- por_que_puede_funcionar: El dolor es visual, universal en home office y demostrable en los primeros 3 segundos.
- por_que_puede_fallar: El dolor puede percibirse trivial y no justificar la compra inmediata.

[A2] Orden visual del escritorio
- promise_type: aspiracional_orden
- target_segment: Estudiantes con escritorio propio.
- pain_addressed: Escritorio hecho un desastre entre clases y trabajo.
- desire_addressed: Escritorio ordenado sin gastar en muebles nuevos.
- objection_addressed: Parece algo que puedo improvisar con cinta.
- proof_needed: Fotos reales antes/despues del escritorio.
- claim_risk: medium
- safe_wording: Un escritorio mas ordenado; nunca prometer productividad medible.
- por_que_puede_funcionar: El antes/despues genera scroll-stop y es facil de producir.
- por_que_puede_fallar: Roza el claim prohibido de productividad medible; exige disciplina de copy.

[A3] Regalo practico de bajo riesgo
- promise_type: regalo_practico
- target_segment: Compradores de accesorios de organizacion para regalar.
- pain_addressed: No saber que regalar util sin gastar de mas.
- desire_addressed: Un regalo util de menos de $350.
- objection_addressed: Un organizador no parece suficiente regalo.
- proof_needed: Foto del empaque real del proveedor.
- claim_risk: low
- safe_wording: Describir como accesorio practico; sin promesas de satisfaccion del receptor.
- por_que_puede_funcionar: Precio de regalo y utilidad inmediata percibida.
- por_que_puede_fallar: Fuera de temporada de regalos el angulo pierde fuerza.

HIPOTESIS CREATIVAS:
[H1] El hook de dolor (cable caido) supera al hook aspiracional en CTR.
- variable_tested: hook de apertura
- expected_signal: CTR mayor en la variante de dolor con alcance comparable.
- failure_signal: CTR plano o menor que la variante aspiracional.
- minimum_evidence_needed: Dos creativos con el mismo copy base y alcance comparable observado por el operador.
- channel: meta_feed
- linked_angle_id: A1

[H2] El formato demostracion retiene mas que la foto estatica en video corto.
- variable_tested: formato del creativo
- expected_signal: Retencion de 3 segundos mayor en la demostracion.
- failure_signal: Retencion igual o menor que la foto estatica.
- minimum_evidence_needed: Dos publicaciones organicas comparables observadas por el operador.
- channel: video_corto_organico
- linked_angle_id: A2

[H3] Mostrar el precio en el creativo no degrada el CTR del angulo de regalo.
- variable_tested: precio visible en el creativo
- expected_signal: CTR estable con precio visible.
- failure_signal: Caida clara de CTR al mostrar el precio.
- minimum_evidence_needed: Una tanda con y sin precio visible sobre el mismo publico.
- channel: meta_feed
- linked_angle_id: A3

RIESGO DE CLAIMS POR COPY:
- hooks | riesgo: low | terminos riesgosos: (ninguno) | terminos prohibidos: (ninguno)
  rewrite seguro: Mantener preguntas de dolor sin promesa absoluta.
  razon: Hooks descriptivos de dolor cotidiano; no contienen claims.
- headlines | riesgo: medium | terminos riesgosos: siempre | terminos prohibidos: (ninguno)
  rewrite seguro: Cables en su lugar, a la mano.
  razon: El absoluto 'siempre' roza la promesa absoluta senalada por el claim guard.
- primary_texts | riesgo: low | terminos riesgosos: (ninguno) | terminos prohibidos: (ninguno)
  rewrite seguro: Mantener las especificaciones del fabricante como unica fuente de capacidad.
  razon: Texto basado en especificaciones verificables del fabricante.
- short_ads | riesgo: low | terminos riesgosos: (ninguno) | terminos prohibidos: (ninguno)
  rewrite seguro: Mantener beneficios descriptivos sin cuantificar resultados.
  razon: Anuncios cortos descriptivos; sin promesas de resultado.
- long_ads | riesgo: medium | terminos riesgosos: siempre se cae | terminos prohibidos: (ninguno)
  rewrite seguro: El cable se cae en el peor momento.
  razon: El 'siempre' aplica al dolor y no a la promesa; aceptable con revision, no repetirlo en la promesa.

MAPA DE SOPORTE DE INPUTS:
- strategy_summary <- marketing.strategy_summary, operator_input.market_context, operator_input.target_audience [soportado]
- core_angle <- marketing.core_angle, operator_input.pain_points [soportado]
- hooks <- marketing.hooks, operator_input.pain_points, operator_input.customer_language [soportado]
- headlines <- marketing.headlines, operator_input.desires [soportado]
- primary_texts <- marketing.primary_texts, operator_input.differentiators, operator_input.proof_elements [soportado]
- short_ads <- marketing.short_ads, operator_input.pain_points [soportado]
- long_ads <- marketing.long_ads, operator_input.proof_elements, operator_input.objections [soportado]
- angle_matrix <- marketing.angle_matrix, operator_input.pain_points, operator_input.desires [soportado]
- creative_hypotheses <- marketing.creative_hypotheses, marketing.angle_matrix [soportado]

PLAN DE PRUEBAS CON UMBRALES:
Boundary de presupuesto (solo dry-run): Boundary teorico de primera prueba: hasta MXN 1500.00 para la primera tanda; Fase 1 es dry-run, sin gasto real.
Senales de exito:
- CTR de la variante de dolor por encima de la variante aspiracional.
- CPA observado por debajo de MXN 106.40 (70% del breakeven).
Senales de advertencia:
- CTR alto con conversion baja en la pagina de producto.
- CPA entre 70% y 100% del breakeven.
Senales de alto:
- CPA sostenido por encima de MXN 152.00 (breakeven).
- Cualquier necesidad de un claim prohibido para sostener el angulo.
Continuar si:
- CPA observado menor o igual al 70% del breakeven durante la primera tanda de pruebas.
Revisar si:
- CPA entre 70% y 100% del breakeven.
- CTR bajo con CPM razonable.
Matar si:
- CPA sostenido por encima del breakeven.
- Vender requiere un claim prohibido.
No concluir:
- No concluir product-market fit por una tanda de pruebas.
- No extrapolar el CPM de una semana a rendimiento estable.
- No atribuir ventas organicas al creativo pagado sin observacion del operador.
Sin claim de PMF: si. Sin fetch de analytics: si.

CLAIM GUARD (Marketing V2):
Resumen: Riesgo de claims bajo; evitar promesas absolutas y claims de productividad medible.
Permitidos:
- Sujeta hasta 6 cables segun especificacion del fabricante.
- Base magnetica con respaldo antideslizante.
- Instalacion sin herramientas.
Riesgosos:
- "Nunca mas se te caera un cable": promesa absoluta; usar redaccion condicional.
Prohibidos:
- Claims de productividad medible sin evidencia de mercado.
Redaccion segura:
- Usar "ayuda a mantener" en lugar de "garantiza".
- Citar la capacidad como especificacion del fabricante."""


def test_recommended_copy_payloads_byte_exact() -> None:
    payloads = _build("recommended").to_dict()["copy_payloads"]
    items = {item["key"]: item["text"] for item in payloads["items"]}

    assert items["shopify_title"] == EXPECTED_SHOPIFY_TITLE
    assert items["shopify_title"].encode("utf-8") == EXPECTED_SHOPIFY_TITLE.encode("utf-8")

    assert items["shopify_full_pack"] == EXPECTED_SHOPIFY_FULL_PACK
    assert (
        items["shopify_full_pack"].encode("utf-8")
        == EXPECTED_SHOPIFY_FULL_PACK.encode("utf-8")
    )

    assert items["marketing_full_pack"] == EXPECTED_MARKETING_FULL_PACK
    assert (
        items["marketing_full_pack"].encode("utf-8")
        == EXPECTED_MARKETING_FULL_PACK.encode("utf-8")
    )

    assert items["marketing_full_pack_v2"] == EXPECTED_MARKETING_FULL_PACK_V2
    assert (
        items["marketing_full_pack_v2"].encode("utf-8")
        == EXPECTED_MARKETING_FULL_PACK_V2.encode("utf-8")
    )


# --- 18. deterministic CLI render -----------------------------------------------------------------------

def test_cli_renders_single_fixture_to_expected_file(tmp_path: Path) -> None:
    output_path = tmp_path / "recommended.html"
    exit_code = wb_renderer.main(
        ["--fixture", str(_fixture_path("recommended")), "--output", str(output_path)]
    )
    assert exit_code == 0
    assert output_path.is_file()

    written = output_path.read_text(encoding="utf-8")
    assert written == _render("recommended")

    # Second render must be byte-identical.
    wb_renderer.main(
        ["--fixture", str(_fixture_path("recommended")), "--output", str(output_path)]
    )
    assert output_path.read_text(encoding="utf-8") == written


def test_cli_renders_fixture_dir(tmp_path: Path) -> None:
    exit_code = wb_renderer.main(
        ["--fixture-dir", str(FIXTURE_DIR), "--output-dir", str(tmp_path)]
    )
    assert exit_code == 0
    for name in FIXTURE_NAMES:
        target = tmp_path / f"{name}.html"
        assert target.is_file()
        assert target.read_text(encoding="utf-8") == _render(name)


# --- Marketing Pack V2 depth gate (A8-R109A-I2) --------------------------------

MAJOR_COPY_SURFACES = ("hooks", "headlines", "primary_texts", "short_ads", "long_ads")


def _marketing(name: str) -> dict:
    return _build(name).to_dict()["marketing_pack"]


def test_recommended_angle_matrix_has_depth() -> None:
    angles = _marketing("recommended")["angle_matrix"]
    assert len(angles) >= 3

    angle_ids = [angle["angle_id"] for angle in angles]
    assert len(set(angle_ids)) == len(angle_ids), "angle ids must be unique"

    for angle in angles:
        for field_name in REQUIRED_ANGLE_FIELDS:
            assert field_name in angle, f"angle missing: {field_name}"
            assert angle[field_name], f"angle field empty: {field_name}"
        # The honesty pair is mandatory per angle.
        assert angle["why_it_might_work"]
        assert angle["why_it_might_fail"]


def test_recommended_creative_hypotheses_have_depth() -> None:
    pack = _marketing("recommended")
    hypotheses = pack["creative_hypotheses"]
    assert len(hypotheses) >= 3

    angle_ids = {angle["angle_id"] for angle in pack["angle_matrix"]}
    for hypothesis in hypotheses:
        for field_name in REQUIRED_HYPOTHESIS_FIELDS:
            assert field_name in hypothesis, f"hypothesis missing: {field_name}"
            assert hypothesis[field_name], f"hypothesis field empty: {field_name}"
        assert hypothesis["linked_angle_id"] in angle_ids, "hypothesis must link a real angle"


def test_recommended_has_five_hooks_minimum() -> None:
    assert len(_marketing("recommended")["hooks"]) >= 5


@pytest.mark.parametrize("name", ("recommended", "blocked", "low_input"))
def test_claim_risk_by_copy_covers_major_surfaces(name: str) -> None:
    entries = {entry["copy_key"]: entry for entry in _marketing(name)["claim_risk_by_copy"]}
    for surface in MAJOR_COPY_SURFACES:
        assert surface in entries, f"claim_risk_by_copy missing surface: {surface}"
        for field_name in REQUIRED_COPY_RISK_FIELDS:
            assert field_name in entries[surface]
        assert entries[surface]["reason"], "each copy risk entry needs a reason"
        assert entries[surface]["safe_rewrite"], "each copy risk entry needs a safe rewrite"


def test_blocked_marketing_is_constrained_by_claim_risk() -> None:
    pack = _marketing("blocked")
    entries = pack["claim_risk_by_copy"]
    assert all(entry["risk_level"] == "prohibited" for entry in entries)
    assert all(entry["prohibited_terms"] for entry in entries)
    assert pack["confidence_by_section"]["claim_safety_confidence"]["level"] == "blocked"
    assert pack["angle_matrix"] == []
    assert pack["creative_hypotheses"] == []


def test_input_support_map_references_real_fixture_fields() -> None:
    for name in ("recommended", "low_input"):
        fixture = json.loads(_fixture_path(name).read_text(encoding="utf-8"))
        support_map = _marketing(name)["input_support_map"]
        assert support_map, "input_support_map must not be empty for product fixtures"

        for entry in support_map:
            for path in entry["support_fields"]:
                section, _, field_name = path.partition(".")
                value = (fixture.get(section) or {}).get(field_name)
                assert value, f"support field {path} is not actually filled in {name}.json"
            if entry["supported"]:
                assert entry["support_fields"], "supported outputs must cite fields"
            else:
                assert entry["support_fields"] == []
                assert "no usar como claim" in entry["notes"]

    # Recommended brief supports every output; nothing may ride unsupported.
    assert all(entry["supported"] for entry in _marketing("recommended")["input_support_map"])
    # The poor brief must leave outputs explicitly unsupported.
    assert any(not entry["supported"] for entry in _marketing("low_input")["input_support_map"])


def test_confidence_by_section_is_not_one_global_score() -> None:
    sections = _marketing("recommended")["confidence_by_section"]
    assert tuple(sorted(sections)) == tuple(sorted(REQUIRED_CONFIDENCE_SECTIONS))
    for entry in sections.values():
        assert entry["level"]
        assert entry["basis"]
    levels = {entry["level"] for entry in sections.values()}
    assert len(levels) >= 2, "confidence must differ by section, not one global score"


def test_testing_plan_with_thresholds_complete() -> None:
    plan = _marketing("recommended")["testing_plan_with_thresholds"]
    assert "dry-run" in plan["first_test_budget_boundary_dry_run_only"]
    for key in (
        "success_signals",
        "warning_signals",
        "stop_signals",
        "continue_if",
        "review_if",
        "kill_if",
        "what_not_to_conclude",
    ):
        assert plan[key], f"testing_plan_with_thresholds.{key} must not be empty"
    assert plan["no_pmf_claim"] is True
    assert plan["no_analytics_fetch"] is True


def test_low_input_degrades_marketing_depth_confidence() -> None:
    pack = _marketing("low_input")
    sections = pack["confidence_by_section"]
    for section in (
        "strategy_confidence",
        "hook_confidence",
        "ad_copy_confidence",
        "channel_pack_confidence",
        "testing_plan_confidence",
    ):
        assert sections[section]["level"] == "low", f"{section} must degrade to low"

    missing = pack["missing_marketing_inputs"]
    assert missing, "low_input must list missing marketing inputs"
    assert any(item.startswith("operator_input.") for item in missing)
    assert any(item.startswith("marketing.") for item in missing)


def test_empty_shortlist_has_no_fake_marketing_v2() -> None:
    pack = _marketing("empty_shortlist")
    assert pack["enabled"] is False
    assert pack["angle_matrix"] == []
    assert pack["creative_hypotheses"] == []
    assert pack["claim_risk_by_copy"] == []
    assert pack["input_support_map"] == []
    for entry in pack["confidence_by_section"].values():
        assert entry["level"] == "none"

    payload_keys = [
        item["key"] for item in _build("empty_shortlist").to_dict()["copy_payloads"]["items"]
    ]
    assert "marketing_full_pack_v2" not in payload_keys


def test_marketing_v2_sections_rendered_in_audit_html() -> None:
    section = _section_html(_render("recommended"), "marketing-pack")
    for anchor in (
        'id="angle-matrix"',
        'id="creative-hypotheses"',
        'id="claim-risk-by-copy"',
        'id="input-support-map"',
        'id="missing-marketing-inputs"',
        'id="confidence-by-section"',
        'id="testing-plan-thresholds"',
    ):
        assert anchor in section, f"marketing audit HTML missing anchor: {anchor}"
    assert "[A1] Dolor cotidiano: el cable perdido" in section
    assert "strategy_confidence" in section
    assert 'data-payload-key="marketing_full_pack_v2"' in _section_html(
        _render("recommended"), "copy-payload-registry"
    )
