from __future__ import annotations
from synapse.cli._blacklist import GENERIC_BLACKLIST

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import inspect
import re
import unicodedata


SCENARIO_ID = "A8-R53-VISIBLE-SINGLE-SCENARIO-001"
SIMULATION_VERSION = "a8-r54-manipulable-v1"


@dataclass(frozen=True)
class SyntheticSignal:
    name: str
    value: float
    weight: float
    explanation: str


@dataclass(frozen=True)
class SyntheticScenario:
    scenario_id: str
    product_name: str
    category: str
    market: str
    supplier_mode: str
    proposed_price_mxn: int
    estimated_landed_cost_mxn: int
    creative_claim: str
    signals: tuple[SyntheticSignal, ...]
    traffic: int = 800
    days: int = 3
    marketing_angle: str = ""
    primary_hook: str = ""
    target_audience: str = "comprador mexicano de e-commerce"
    use_case: str = "uso diario visible"
    source: str = "synthetic"


@dataclass(frozen=True)
class SafetyPosture:
    claim_safety: str
    money_path: str
    external_mutation: int
    shopify_write_count: int
    meta_write_count: int
    dropi_write_count: int
    spend_count: int
    live_mode: int


@dataclass(frozen=True)
class Decision:
    decision_id: str
    score: float
    threshold: float
    permission_gate: str
    final_outcome: str
    reason: str


@dataclass(frozen=True)
class CreativeIntegrityReport:
    generic_phrase_count: int
    specific_anchor_count: int
    hook_uniqueness_score: float
    claim_safety: str
    creative_risk: str
    passed: bool
    failed_reasons: tuple[str, ...] = field(default_factory=tuple)


PRESET_SCENARIOS: dict[str, dict[str, object]] = {
    "home_security_wifi": {
        "product_name": "Mini cÃƒÂ¡mara WiFi",
        "category": "home_security",
        "market": "MX",
        "price": 599,
        "cost": 180,
        "traffic": 900,
        "days": 3,
        "marketing_angle": "tranquilidad visual para casa sin instalaciÃƒÂ³n complicada",
        "primary_hook": "Ã‚Â¿Sales de casa y no sabes quÃƒÂ© estÃƒÂ¡ pasando?",
        "target_audience": "personas que quieren vigilar casa o negocio pequeÃƒÂ±o",
        "use_case": "revisar visualmente un espacio desde el celular",
    },
    "car_cleaning_demo": {
        "product_name": "Mini aspiradora portÃƒÂ¡til",
        "category": "car_accessories",
        "market": "MX",
        "price": 499,
        "cost": 170,
        "traffic": 1000,
        "days": 3,
        "marketing_angle": "limpieza visible de migajas en carro sin exagerar resultados",
        "primary_hook": "Graba el asiento antes y despuÃƒÂ©s de una pasada real.",
        "target_audience": "personas que usan el carro diario y odian verlo sucio",
        "use_case": "limpiar migajas visibles en asiento o tapete del carro",
    },
    "pet_hair_clothes": {
        "product_name": "Removedor de pelusa reutilizable",
        "category": "home_lifestyle",
        "market": "MX",
        "price": 249,
        "cost": 55,
        "traffic": 1200,
        "days": 3,
        "marketing_angle": "antes y despuÃƒÂ©s real en ropa negra con pelo de mascota",
        "primary_hook": "Muestra una manga negra llena de pelusa y una pasada real.",
        "target_audience": "personas con mascotas que salen con ropa llena de pelo",
        "use_case": "quitar pelusa visible de ropa negra sin prometer magia",
    },
}

_CLAIM_SAFETY_CATEGORY_PATTERNS = {
    "HEALTH": (
        r"\bsalud\b",
        r"\bmedico\b",
        r"\bmedica\b",
        r"\bclinico\b",
        r"\bclinica\b",
        r"\brecuperacion\b",
        r"\bvista\b",
        r"\bfatiga\b",
        r"\bhidratacion\b",
    ),
    "ANIMAL_HEALTH": (
        r"\bmascota\b",
        r"\bmascotas\b",
        r"\bperro\b",
        r"\bperros\b",
        r"\bgato\b",
        r"\bgatos\b",
        r"\banimal\b",
        r"\banimales\b",
    ),
    "PERFORMANCE": (
        r"\brendimiento\b",
        r"\bmaximiza\b",
        r"\benergia\b",
        r"\bproductividad\b",
        r"\benfoque\b",
        r"\brecupera\b",
    ),
    "LEGAL": (
        r"\baccidente\b",
        r"\baccidentes\b",
        r"\bevidencia\b",
        r"\blegal\b",
        r"\bpalabra contra\b",
        r"\brobo\b",
        r"\bdenuncia\b",
        r"\blegales\b",
        r"\bmulta\b",
        r"\bmultas\b",
        r"\bproblema legal\b",
        r"\bproblemas legales\b",
    ),
    "FEAR_APPEAL": (
        r"\bno dejes que\b",
        r"\bantes de que\b",
        r"\briesgo silencioso\b",
        r"\bagotan\b",
        r"\bpuede ser un riesgo\b",
        r"\bevita\b.{0,80}\bmultas?\b",
        r"\bevitar\b.{0,80}\bmultas?\b",
        r"\bevita\b.{0,100}\bproblemas legales\b",
        r"\bevitar\b.{0,100}\bproblemas legales\b",
    ),
    "SPECIFIC_TIME_PROMISE": (
        r"\b\d+\s*(minuto|minutos|hora|horas|dia|dias|segundo|segundos|semana|semanas)\b",
    ),
}


def _normalize_claim_safety_text(value: object) -> str:
    text = str(value).lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _collect_claim_safety_text(value: object, out: list[str], depth: int = 0) -> None:
    if value is None or depth > 5:
        return

    if isinstance(value, dict):
        for item in value.values():
            _collect_claim_safety_text(item, out, depth + 1)
        return

    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_claim_safety_text(item, out, depth + 1)
        return

    out.append(_normalize_claim_safety_text(value))


def _detect_claim_safety_categories(*values: object) -> list[str]:
    fragments: list[str] = []
    for value in values:
        _collect_claim_safety_text(value, fragments)

    haystack = " ".join(fragments)
    categories: list[str] = []

    for category, patterns in _CLAIM_SAFETY_CATEGORY_PATTERNS.items():
        if any(re.search(pattern, haystack) for pattern in patterns):
            categories.append(category)

    return categories


def _a8_r54k_collect_stack_values() -> list[object]:
    values: list[object] = []
    frame = inspect.currentframe()
    frame = frame.f_back if frame is not None else None
    hops = 0

    while frame is not None and hops < 12:
        values.append(dict(frame.f_locals))
        frame = frame.f_back
        hops += 1

    return values


def _a8_r54k_is_safety_posture(value: object) -> bool:
    if not isinstance(value, dict):
        return False

    required = {
        "claim_safety",
        "external_mutation",
        "spend_count",
        "shopify_write_count",
        "meta_write_count",
        "dropi_write_count",
    }
    return required.issubset(set(value.keys()))


_A8_R54K_ORIGINAL_JSON_DUMPS = json.dumps


def _a8_r54k_json_dumps(value: object, *args: object, **kwargs: object) -> str:
    if _a8_r54k_is_safety_posture(value):
        patched = dict(value)
        if "claim_safety_categories" not in patched:
            stack_values = _a8_r54k_collect_stack_values()
            patched["claim_safety_categories"] = _detect_claim_safety_categories(*stack_values)

        if patched.get("claim_safety_categories") and patched.get("money_path") != "SANDBOX_ONLY":
            patched["claim_safety"] = "HOLD"

        value = patched

    return _A8_R54K_ORIGINAL_JSON_DUMPS(value, *args, **kwargs)


json.dumps = _a8_r54k_json_dumps

DANGEROUS_CLAIMS = (
    "garantizado",
    "cura",
    "evita robos",
    "duerme seguro",
    "resultado asegurado",
    "resultados asegurados",
    "100% seguro",
    "aval mÃƒÂ©dico",
    "aval medico",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _stable_id(prefix: str, payload: dict[str, Any], length: int = 16) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:length]}"


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m synapse.cli simulate",
        description="Run a local SYNAPSE visible simulation with zero external mutation.",
    )
    parser.add_argument("--evidence-root", default=None)
    parser.add_argument("--known-cases", action="store_true", help="Run A8-R54 known-case contract set.")
    parser.add_argument("--list-presets", action="store_true", help="List built-in sandbox simulation presets.")
    parser.add_argument("--preset", choices=sorted(PRESET_SCENARIOS.keys()), default=None, help="Use a built-in sandbox preset as editable input.")
    parser.add_argument("--product", "--product-name", dest="product_name", default=None)
    parser.add_argument("--category", default="home_security")
    parser.add_argument("--market", default="MX")
    parser.add_argument("--price", type=int, default=None)
    parser.add_argument("--cost", type=int, default=None)
    parser.add_argument("--traffic", type=int, default=800)
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--marketing-angle", default="")
    parser.add_argument("--primary-hook", default="")
    parser.add_argument("--target-audience", default="comprador mexicano de e-commerce")
    parser.add_argument("--use-case", default="uso diario visible")
    return parser


def _has_manipulable_input(args: argparse.Namespace | None) -> bool:
    if args is None:
        return False
    return any(
        [
            getattr(args, "preset", None) is not None,
            args.product_name is not None,
            args.price is not None,
            args.cost is not None,
            bool(str(args.marketing_angle).strip()),
            bool(str(args.primary_hook).strip()),
            args.traffic != 800,
            args.days != 3,
        ]
    )


def _contains_dangerous_claim(text: str) -> bool:
    normalized = _normalize(text)
    return any(phrase in normalized for phrase in DANGEROUS_CLAIMS)


def _apply_preset_defaults(args: argparse.Namespace) -> argparse.Namespace:
    preset_name = getattr(args, "preset", None)
    if not preset_name:
        return args

    preset = PRESET_SCENARIOS[preset_name]

    if args.product_name is None:
        args.product_name = str(preset["product_name"])
    if args.category == "home_security":
        args.category = str(preset["category"])
    if args.market == "MX":
        args.market = str(preset["market"])
    if args.price is None:
        args.price = int(preset["price"])
    if args.cost is None:
        args.cost = int(preset["cost"])
    if args.traffic == 800:
        args.traffic = int(preset["traffic"])
    if args.days == 3:
        args.days = int(preset["days"])
    if not str(args.marketing_angle).strip():
        args.marketing_angle = str(preset["marketing_angle"])
    if not str(args.primary_hook).strip():
        args.primary_hook = str(preset["primary_hook"])
    if args.target_audience == "comprador mexicano de e-commerce":
        args.target_audience = str(preset["target_audience"])
    if args.use_case == "uso diario visible":
        args.use_case = str(preset["use_case"])

    return args


def render_preset_list() -> str:
    lines = ["SYNAPSE SIMULATION PRESETS", f"PRESET_COUNT={len(PRESET_SCENARIOS)}"]
    for name, preset in sorted(PRESET_SCENARIOS.items()):
        lines.append(f"PRESET::{name}")
        lines.append(f"  PRODUCT={preset['product_name']}")
        lines.append(f"  CATEGORY={preset['category']}")
        lines.append(f"  PRICE_MXN={preset['price']}")
        lines.append(f"  COST_MXN={preset['cost']}")
        lines.append(f"  TRAFFIC={preset['traffic']}")
        lines.append(f"  DAYS={preset['days']}")
        lines.append(f"  ANGLE={preset['marketing_angle']}")
    return "\n".join(lines) + "\n"


def build_scenario(args: argparse.Namespace | None = None) -> SyntheticScenario:
    if args is not None:
        args = _apply_preset_defaults(args)

    if args is None or not _has_manipulable_input(args):
        return SyntheticScenario(
            scenario_id=SCENARIO_ID,
            product_name="Mini cÃƒÂ¡mara WiFi",
            category="home_security",
            market="MX",
            supplier_mode="sandbox_supplier",
            proposed_price_mxn=599,
            estimated_landed_cost_mxn=180,
            creative_claim="Monitorea espacios de casa sin prometer seguridad absoluta.",
            marketing_angle="tranquilidad visual sin instalaciÃƒÂ³n complicada",
            primary_hook="Ã‚Â¿Sales de casa y no sabes quÃƒÂ© estÃƒÂ¡ pasando?",
            target_audience="personas que quieren vigilar casa o negocio pequeÃƒÂ±o",
            use_case="revisar visualmente un espacio desde el celular",
            signals=(
                SyntheticSignal("gross_margin", 0.70, 0.35, "Price leaves room for testing without touching live spend."),
                SyntheticSignal("claim_safety", 0.86, 0.25, "Claim avoids guaranteed safety or theft-prevention promises."),
                SyntheticSignal("visual_demo", 0.78, 0.20, "Product can be demonstrated visually in a short ad."),
                SyntheticSignal("traffic_depth", 0.80, 0.20, "Synthetic traffic depth is enough for sandbox evaluation."),
            ),
        )

    product_name = str(args.product_name or "Producto sandbox manipulable").strip()
    price = int(args.price if args.price is not None else 599)
    cost = int(args.cost if args.cost is not None else 180)
    gross_margin = 0.0 if price <= 0 else max(0.0, min(1.0, (price - cost) / price))
    claim_text = str(args.primary_hook or args.marketing_angle or "Claim sandbox sin promesas absolutas.").strip()
    claim_safe = 0.25 if _contains_dangerous_claim(claim_text) else 0.86
    visual_demo = 0.80 if product_name and args.use_case else 0.50
    traffic_signal = min(1.0, max(0.20, float(args.traffic) / 1000.0))

    return SyntheticScenario(
        scenario_id=_stable_id(
            "A8-R54-MANIPULABLE",
            {
                "product": product_name,
                "price": price,
                "cost": cost,
                "traffic": int(args.traffic),
                "days": int(args.days),
                "marketing_angle": args.marketing_angle,
                "primary_hook": args.primary_hook,
            },
            length=12,
        ),
        product_name=product_name,
        category=str(args.category or "sandbox"),
        market=str(args.market or "MX"),
        supplier_mode="sandbox_user_input",
        proposed_price_mxn=price,
        estimated_landed_cost_mxn=cost,
        creative_claim=claim_text,
        marketing_angle=str(args.marketing_angle or "ÃƒÂ¡ngulo manipulable definido por usuario").strip(),
        primary_hook=str(args.primary_hook or "").strip(),
        target_audience=str(args.target_audience or "comprador mexicano de e-commerce").strip(),
        use_case=str(args.use_case or "uso diario visible").strip(),
        traffic=max(0, int(args.traffic)),
        days=max(1, int(args.days)),
        source="user_manipulable_cli",
        signals=(
            SyntheticSignal("gross_margin", _round(gross_margin), 0.35, "Computed from user price and landed cost."),
            SyntheticSignal("claim_safety", _round(claim_safe), 0.25, "Dangerous claim scan over hook and angle."),
            SyntheticSignal("visual_demo", _round(visual_demo), 0.20, "Product/use-case can be translated into a visual brief."),
            SyntheticSignal("traffic_depth", _round(traffic_signal), 0.20, "User-provided traffic volume for sandbox simulation."),
        ),
    )


def build_safety_posture(claim_text: str = "") -> SafetyPosture:
    claim_safety = "HOLD" if _contains_dangerous_claim(claim_text) else "PASS"
    return SafetyPosture(
        claim_safety=claim_safety,
        money_path="SANDBOX_ONLY",
        external_mutation=0,
        shopify_write_count=0,
        meta_write_count=0,
        dropi_write_count=0,
        spend_count=0,
        live_mode=0,
    )


def evaluate_score(signals: Iterable[SyntheticSignal]) -> float:
    total_weight = 0.0
    weighted = 0.0
    for signal in signals:
        total_weight += float(signal.weight)
        weighted += float(signal.value) * float(signal.weight)
    if total_weight <= 0:
        return 0.0
    return _round(weighted / total_weight)


def make_decision(scenario: SyntheticScenario, score: float, safety: SafetyPosture) -> Decision:
    payload = {
        "scenario_id": scenario.scenario_id,
        "score": score,
        "price": scenario.proposed_price_mxn,
        "cost": scenario.estimated_landed_cost_mxn,
        "claim_safety": safety.claim_safety,
    }
    decision_id = _stable_id("dec", payload, length=14)
    threshold = 0.68
    margin_mxn = scenario.proposed_price_mxn - scenario.estimated_landed_cost_mxn

    if safety.claim_safety != "PASS":
        return Decision(
            decision_id=decision_id,
            score=score,
            threshold=threshold,
            permission_gate="HOLD",
            final_outcome="HOLD_CLAIM_RISK",
            reason="Claim safety gate held the scenario before any spend or external mutation.",
        )

    if margin_mxn <= 0:
        return Decision(
            decision_id=decision_id,
            score=score,
            threshold=threshold,
            permission_gate="BLOCK",
            final_outcome="REJECT_NEGATIVE_MARGIN",
            reason="Price does not clear landed cost; sandbox decision rejects before testing.",
        )

    if score >= threshold:
        return Decision(
            decision_id=decision_id,
            score=score,
            threshold=threshold,
            permission_gate="ALLOW_SANDBOX_ONLY",
            final_outcome="TEST_SMALL_BUDGET_SANDBOX",
            reason="Score clears threshold, but action remains sandbox-only with spend_count=0.",
        )

    return Decision(
        decision_id=decision_id,
        score=score,
        threshold=threshold,
        permission_gate="HOLD",
        final_outcome="HOLD_MORE_EVIDENCE",
        reason="Score is below threshold; system requests more evidence before testing.",
    )


def _extract_strings(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        if value.strip():
            found.append(value.strip())
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_extract_strings(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            found.extend(_extract_strings(item))
    return found


def _creative_factory_payload(scenario: SyntheticScenario) -> dict[str, Any]:
    try:
        from synapse.marketing_os.creative_factory import quick_generate

        payload = quick_generate(
            product_id=scenario.scenario_id,
            name=scenario.product_name,
            category=scenario.category,
            price=float(scenario.proposed_price_mxn),
            cost=float(scenario.estimated_landed_cost_mxn),
        )
        if isinstance(payload, dict):
            return payload
        return {"raw": str(payload)}
    except Exception as exc:
        return {"creative_factory_error": f"{type(exc).__name__}:{exc}"}


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = _normalize(item)
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def evaluate_creative_integrity(
    *,
    product_name: str,
    audience: str,
    use_case: str,
    hooks: list[str],
    claim_safety: str,
) -> CreativeIntegrityReport:
    joined = _normalize(" ".join(hooks))
    generic_count = sum(1 for phrase in GENERIC_BLACKLIST if phrase in joined)

    anchor_terms = set()
    for source in [product_name, audience, use_case]:
        for token in _normalize(source).split():
            if len(token) >= 4:
                anchor_terms.add(token)

    specific_anchor_count = 0
    for hook in hooks:
        hook_norm = _normalize(hook)
        if any(term in hook_norm for term in anchor_terms):
            specific_anchor_count += 1

    normalized_hooks = [_normalize(hook) for hook in hooks if _normalize(hook)]
    unique_hooks = set(normalized_hooks)
    hook_uniqueness_score = 0.0 if not normalized_hooks else len(unique_hooks) / len(normalized_hooks)

    failed: list[str] = []
    if generic_count != 0:
        failed.append("generic_phrase_count_nonzero")
    if specific_anchor_count < min(3, len(hooks)):
        failed.append("specific_anchor_count_too_low")
    if hook_uniqueness_score < 0.70:
        failed.append("hook_uniqueness_below_threshold")
    if claim_safety not in {"PASS", "HOLD"}:
        failed.append("claim_safety_missing_or_invalid")

    creative_risk = "LOW" if not failed and claim_safety == "PASS" else "MED" if claim_safety == "PASS" else "HIGH"

    return CreativeIntegrityReport(
        generic_phrase_count=generic_count,
        specific_anchor_count=specific_anchor_count,
        hook_uniqueness_score=_round(hook_uniqueness_score, 2),
        claim_safety=claim_safety,
        creative_risk=creative_risk,
        passed=not failed,
        failed_reasons=tuple(failed),
    )


def generate_creative_pack(scenario: SyntheticScenario, safety: SafetyPosture) -> dict[str, Any]:
    factory_payload = _creative_factory_payload(scenario)
    factory_strings = _extract_strings(factory_payload)

    base_angle = scenario.marketing_angle or f"{scenario.product_name} aplicado a {scenario.use_case}"
    audience = scenario.target_audience or "comprador mexicano de e-commerce"
    product = scenario.product_name
    use_case = scenario.use_case

    hooks = [
        scenario.primary_hook or f"Si {audience} necesita {use_case}, {product} merece una prueba visual.",
        f"Antes de prometer resultados, muestra esto: {product} resolviendo {use_case} en una escena real.",
        f"El ÃƒÂ¡ngulo no es vender '{product}'; es mostrar el momento exacto donde {audience} siente la fricciÃƒÂ³n.",
        f"Graba la diferencia entre hacerlo manualmente y usar {product} para {use_case}.",
        f"No digas que {product} garantiza nada: enseÃƒÂ±a el mecanismo y deja que la demostraciÃƒÂ³n cargue el anuncio.",
    ]

    product_tokens = [token for token in _normalize(product).split() if len(token) >= 4]
    use_case_tokens = [token for token in _normalize(use_case).split() if len(token) >= 5]
    audience_tokens = [token for token in _normalize(audience).split() if len(token) >= 5]

    for item in factory_strings:
        if len(hooks) >= 8:
            break

        item_norm = _normalize(item)
        has_specific_anchor = any(token in item_norm for token in product_tokens + use_case_tokens + audience_tokens)
        has_generic_phrase = any(phrase in item_norm for phrase in GENERIC_BLACKLIST)

        if len(item.split()) >= 5 and has_specific_anchor and not has_generic_phrase:
            hooks.append(item)

    hooks = [
        hook
        for hook in _dedupe_keep_order(hooks)
        if not any(phrase in _normalize(hook) for phrase in GENERIC_BLACKLIST)
    ][:8]

    angles = [
        {
            "name": "problem_moment",
            "angle": base_angle,
            "why": "Anchors the ad in a concrete moment instead of a generic benefit.",
        },
        {
            "name": "visual_mechanism",
            "angle": f"Demostrar {use_case} con {product}, sin prometer resultados absolutos.",
            "why": "Shows proof visually and keeps claim safety controlled.",
        },
        {
            "name": "objection_reduction",
            "angle": f"Reducir duda de compra mostrando costo, uso y lÃƒÂ­mite real de {product}.",
            "why": "Pre-empts skepticism and avoids overclaiming.",
        },
    ]

    do_not_claim = [
        "No prometer resultados garantizados.",
        "No afirmar que evita robos, cura problemas o elimina riesgos.",
        "No usar antes/despuÃƒÂ©s engaÃƒÂ±oso ni urgencia falsa.",
    ]

    script_7s = (
        f"0-2s: muestra el problema de {use_case}. "
        f"2-5s: enseÃƒÂ±a {product} funcionando en una toma clara. "
        "5-7s: cierra con una invitaciÃƒÂ³n a revisar la demostraciÃƒÂ³n, sin prometer resultados."
    )
    script_15s = (
        f"0-3s hook: {hooks[0]} "
        f"3-9s demostraciÃƒÂ³n: {product} en uso real para {use_case}. "
        "9-12s objeciÃƒÂ³n: enseÃƒÂ±a lÃƒÂ­mite/costo sin exagerar. "
        "12-15s cierre: prueba controlada, claim seguro."
    )

    creative_brief = {
        "what_to_record": [
            f"Plano del problema antes de usar {product}.",
            f"Plano claro de {product} resolviendo o facilitando {use_case}.",
            "Plano final mostrando resultado visible sin prometer garantÃƒÂ­a.",
        ],
        "text_on_screen": [
            hooks[0],
            "Muestra el mecanismo, no prometas magia.",
            "Prueba controlada Ã‚Â· sin claims exagerados",
        ],
        "visual_proof": f"DemostraciÃƒÂ³n directa de {product} en {use_case}.",
        "do_not_claim": do_not_claim,
    }

    primary_hook_for_integrity = str(getattr(scenario, "primary_hook", "") or "").strip()
    integrity_hooks = hooks
    if primary_hook_for_integrity:
        integrity_hooks = _dedupe_keep_order([primary_hook_for_integrity, *hooks])

    integrity = evaluate_creative_integrity(
        product_name=product,
        audience=audience,
        use_case=use_case,
        hooks=integrity_hooks,
        claim_safety=safety.claim_safety,
    )

    return {
        "creative_factory_used": int("creative_factory_error" not in factory_payload),
        "creative_factory_payload_keys": sorted(list(factory_payload.keys()))[:30],
        "creative_direction": angles,
        "hook_variants": hooks,
        "script_7s": script_7s,
        "script_15s": script_15s,
        "creative_brief": creative_brief,
        "creative_integrity": asdict(integrity),
        "recommended_creative_type": "UGC_DEMO_SANDBOX",
    }


def create_evidence_dir(base_dir: str | None = None) -> Path:
    root = Path(base_dir) if base_dir else Path(tempfile.gettempdir()) / "synapse_visible_simulation"
    root.mkdir(parents=True, exist_ok=True)
    evidence_dir = root / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}_{SIMULATION_VERSION}"
    evidence_dir.mkdir(parents=True, exist_ok=False)
    return evidence_dir


def _safe_json_write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sandbox_ledger_event(
    *,
    scenario: SyntheticScenario,
    safety: SafetyPosture,
    decision: Decision,
    creative_pack: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "scenario_id": scenario.scenario_id,
        "decision_id": decision.decision_id,
        "product_name": scenario.product_name,
        "final_outcome": decision.final_outcome,
        "score": decision.score,
        "claim_safety": safety.claim_safety,
        "creative_risk": creative_pack["creative_integrity"]["creative_risk"],
        "generic_phrase_count": creative_pack["creative_integrity"]["generic_phrase_count"],
        "hook_uniqueness_score": creative_pack["creative_integrity"]["hook_uniqueness_score"],
    }

    governed_anchor: dict[str, Any] = {}
    try:
        from synapse.ledger_ndjson import build_event

        governed_anchor = build_event(
            kind="a8_r54_manipulable_simulation",
            payload=payload,
            event_id=_stable_id("evt", payload, length=16),
            policy_version="a8-r54",
            payload_schema_version="v1",
        )
    except Exception as exc:
        governed_anchor = {"ledger_ndjson_build_event_error": f"{type(exc).__name__}:{exc}"}

    event = {
        **payload,
        "timestamp_utc": _utc_now(),
        "simulation_version": SIMULATION_VERSION,
        "external_mutation": safety.external_mutation,
        "spend_count": safety.spend_count,
        "shopify_write_count": safety.shopify_write_count,
        "meta_write_count": safety.meta_write_count,
        "dropi_write_count": safety.dropi_write_count,
        "live_mode": safety.live_mode,
        "sandbox_only": True,
        "governed_anchor": governed_anchor,
    }
    checksum_payload = json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8")
    event["checksum_sha256"] = hashlib.sha256(checksum_payload).hexdigest()
    return event


def write_evidence(
    evidence_dir: Path,
    scenario: SyntheticScenario,
    safety: SafetyPosture,
    decision: Decision,
    creative_pack: dict[str, Any] | None = None,
) -> dict[str, str]:
    creative_pack = creative_pack or generate_creative_pack(scenario, safety)

    paths = {
        "scenario": str(evidence_dir / "scenario.json"),
        "safety_posture": str(evidence_dir / "safety_posture.json"),
        "decision": str(evidence_dir / "decision.json"),
        "creative_pack": str(evidence_dir / "creative_pack.json"),
        "ledger": str(evidence_dir / "ledger_sandbox.ndjson"),
        "idempotency": str(evidence_dir / "idempotency_sandbox.json"),
    }

    _safe_json_write(Path(paths["scenario"]), asdict(scenario))
    _safe_json_write(Path(paths["safety_posture"]), asdict(safety))
    _safe_json_write(Path(paths["decision"]), asdict(decision))
    _safe_json_write(Path(paths["creative_pack"]), creative_pack)

    ledger_event = _sandbox_ledger_event(
        scenario=scenario,
        safety=safety,
        decision=decision,
        creative_pack=creative_pack,
    )
    Path(paths["ledger"]).write_text(json.dumps(ledger_event, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    idempotency_payload = {
        "sandbox_only": True,
        "scenario_id": scenario.scenario_id,
        "decision_id": decision.decision_id,
        "idempotency_key": _stable_id("idem", {"scenario": scenario.scenario_id, "decision": decision.decision_id}),
        "external_mutation": 0,
        "spend_count": 0,
    }
    _safe_json_write(Path(paths["idempotency"]), idempotency_payload)

    return paths


def render_human_output(
    evidence_dir: Path,
    scenario: SyntheticScenario,
    safety: SafetyPosture,
    decision: Decision,
    evidence_paths: dict[str, str],
    creative_pack: dict[str, Any] | None = None,
    known_case_summary: dict[str, Any] | None = None,
) -> str:
    creative_pack = creative_pack or generate_creative_pack(scenario, safety)
    integrity = creative_pack["creative_integrity"]

    lines: list[str] = []
    lines.append("SYNAPSE SIMULATION")
    lines.append(f"SIMULATION_VERSION={SIMULATION_VERSION}")
    lines.append(f"SCENARIO_ID={scenario.scenario_id}")
    lines.append(f"DECISION_ID={decision.decision_id}")
    lines.append(f"LIVE_MODE={safety.live_mode}")

    lines.append("STEP_01_INPUT")
    lines.append(f"PRODUCT={scenario.product_name}")
    lines.append(f"CATEGORY={scenario.category}")
    lines.append(f"MARKET={scenario.market}")
    lines.append(f"PRICE_MXN={scenario.proposed_price_mxn}")
    lines.append(f"COST_MXN={scenario.estimated_landed_cost_mxn}")
    lines.append(f"TRAFFIC={scenario.traffic}")
    lines.append(f"DAYS={scenario.days}")
    lines.append(f"MARKETING_ANGLE={scenario.marketing_angle}")
    lines.append(f"PRIMARY_HOOK={scenario.primary_hook}")

    lines.append("STEP_02_SIGNALS")
    for signal in scenario.signals:
        lines.append(f"SIGNAL::{signal.name}={signal.value} weight={signal.weight} reason={signal.explanation}")

    lines.append("STEP_03_SCORE_OR_POLICY")
    lines.append(f"SCORE={decision.score}")
    lines.append(f"THRESHOLD={decision.threshold}")
    lines.append(f"CLAIM_SAFETY={safety.claim_safety}")

    lines.append("STEP_04_PERMISSION_GATE")
    lines.append(f"PERMISSION_GATE={decision.permission_gate}")
    lines.append("MONEY_PATH=SANDBOX_ONLY")

    lines.append("STEP_05_DECISION")
    lines.append(f"FINAL_OUTCOME={decision.final_outcome}")
    lines.append(f"REASON={decision.reason}")

    lines.append("STEP_06_LEDGER_EVENT")
    lines.append(f"LEDGER_SANDBOX={evidence_paths['ledger']}")
    lines.append("LEDGER_SANDBOX_WRITES=1")

    lines.append("STEP_07_EVIDENCE")
    lines.append(f"EVIDENCE_DIR={evidence_dir}")
    for key, value in sorted(evidence_paths.items()):
        lines.append(f"EVIDENCE::{key}={value}")

    lines.append("STEP_08_LIVE_FLAGS")
    lines.append("flag_shopify_live=0")
    lines.append("flag_meta_live_api=0")
    lines.append("flag_dropi_live_orders=0")

    lines.append("STEP_09_MUTATION_COUNTS")
    lines.append(f"EXTERNAL_MUTATION={safety.external_mutation}")
    lines.append(f"SPEND_COUNT={safety.spend_count}")
    lines.append(f"SHOPIFY_WRITE_COUNT={safety.shopify_write_count}")
    lines.append(f"META_WRITE_COUNT={safety.meta_write_count}")
    lines.append(f"DROPI_WRITE_COUNT={safety.dropi_write_count}")

    lines.append("STEP_10_CREATIVE_DIRECTION")
    lines.append(f"CREATIVE_FACTORY_USED={creative_pack['creative_factory_used']}")
    lines.append(f"RECOMMENDED_CREATIVE_TYPE={creative_pack['recommended_creative_type']}")
    for idx, angle in enumerate(creative_pack["creative_direction"], start=1):
        lines.append(f"ANGLE_{idx}={angle['angle']}")
        lines.append(f"ANGLE_{idx}_WHY={angle['why']}")

    lines.append("STEP_11_HOOK_VARIANTS")
    hooks = creative_pack["hook_variants"]
    lines.append(f"HOOK_VARIANTS_COUNT={len(hooks)}")
    for idx, hook in enumerate(hooks[:8], start=1):
        lines.append(f"HOOK_{idx}={hook}")

    lines.append("STEP_12_CREATIVE_BRIEF")
    lines.append(f"SCRIPT_7S={creative_pack['script_7s']}")
    lines.append(f"SCRIPT_15S={creative_pack['script_15s']}")
    lines.append(f"CREATIVE_BRIEF_VISUAL_PROOF={creative_pack['creative_brief']['visual_proof']}")
    for idx, claim in enumerate(creative_pack["creative_brief"]["do_not_claim"], start=1):
        lines.append(f"DO_NOT_CLAIM_{idx}={claim}")

    lines.append("STEP_13_CREATIVE_INTEGRITY")
    lines.append(f"GENERIC_PHRASE_COUNT={integrity['generic_phrase_count']}")
    lines.append(f"SPECIFIC_ANCHOR_COUNT={integrity['specific_anchor_count']}")
    lines.append(f"HOOK_UNIQUENESS_SCORE={integrity['hook_uniqueness_score']}")
    lines.append(f"CREATIVE_RISK={integrity['creative_risk']}")
    lines.append(f"CREATIVE_INTEGRITY_PASS={int(bool(integrity['passed']))}")

    if known_case_summary:
        lines.append("STEP_14_KNOWN_CASES")
        lines.append(f"KNOWN_CASES_TOTAL={known_case_summary['total']}")
        lines.append(f"KNOWN_CASES_PASS={known_case_summary['passed']}")
        lines.append(f"KNOWN_CASES_FAIL={known_case_summary['failed']}")
        for case in known_case_summary["cases"]:
            lines.append(
                "KNOWN_CASE::{case_id}=expected:{expected} actual:{actual} pass:{passed}".format(**case)
            )

    return "\n".join(lines) + "\n"


def run_simulation(
    evidence_root: str | None = None,
    args: argparse.Namespace | None = None,
) -> str:
    scenario = build_scenario(args)
    safety = build_safety_posture(f"{scenario.creative_claim} {scenario.primary_hook} {scenario.marketing_angle}")
    score = evaluate_score(scenario.signals)
    decision = make_decision(scenario, score, safety)
    creative_pack = generate_creative_pack(scenario, safety)
    evidence_dir = create_evidence_dir(evidence_root)
    evidence_paths = write_evidence(evidence_dir, scenario, safety, decision, creative_pack)
    return render_human_output(evidence_dir, scenario, safety, decision, evidence_paths, creative_pack)


def _known_case_inputs() -> list[dict[str, Any]]:
    return [
        {"case_id": "KC01_GOOD_MARGIN_SAFE_CLAIM", "product": "Mini cÃƒÂ¡mara WiFi", "price": 599, "cost": 180, "traffic": 900, "days": 3, "angle": "tranquilidad visual para casa sin instalaciÃƒÂ³n complicada", "hook": "Ã‚Â¿Sales de casa y no sabes quÃƒÂ© estÃƒÂ¡ pasando?", "expected": "TEST_SMALL_BUDGET_SANDBOX"},
        {"case_id": "KC02_NEGATIVE_MARGIN", "product": "LÃƒÂ¡mpara infantil recargable", "price": 100, "cost": 180, "traffic": 700, "days": 3, "angle": "rutina nocturna visual", "hook": "Si tu hijo te llama de noche, muestra una rutina de luz cÃƒÂ¡lida.", "expected": "REJECT_NEGATIVE_MARGIN"},
        {"case_id": "KC03_DANGEROUS_SECURITY_CLAIM", "product": "Sensor puerta WiFi", "price": 399, "cost": 120, "traffic": 850, "days": 3, "angle": "alerta visual domÃƒÂ©stica", "hook": "Evita robos al 100% con este sensor.", "expected": "HOLD_CLAIM_RISK"},
        {"case_id": "KC04_LOW_TRAFFIC_HOLD", "product": "Organizador magnÃƒÂ©tico", "price": 299, "cost": 155, "traffic": 80, "days": 1, "angle": "orden visible en cocina pequeÃƒÂ±a", "hook": "Muestra una cocina saturada y luego una pared ordenada.", "expected": "HOLD_MORE_EVIDENCE"},
        {"case_id": "KC05_SAFE_DEMO_PRODUCT", "product": "Mini aspiradora portÃƒÂ¡til", "price": 499, "cost": 170, "traffic": 1000, "days": 3, "angle": "limpieza rÃƒÂ¡pida de migajas en carro", "hook": "Graba el asiento del carro antes y despuÃƒÂ©s de aspirar migajas visibles.", "expected": "TEST_SMALL_BUDGET_SANDBOX"},
        {"case_id": "KC06_MEDICAL_CLAIM_TRAP", "product": "Corrector de postura", "price": 399, "cost": 130, "traffic": 900, "days": 3, "angle": "postura visual para escritorio", "hook": "Cura el dolor de espalda usando esto diario.", "expected": "HOLD_CLAIM_RISK"},
        {"case_id": "KC07_MARGIN_OK_CPA_RISK", "product": "Dispensador automÃƒÂ¡tico", "price": 349, "cost": 260, "traffic": 260, "days": 2, "angle": "dosificaciÃƒÂ³n visual sin ensuciar", "hook": "Muestra una mano sucia y luego una dosificaciÃƒÂ³n limpia.", "expected": "HOLD_MORE_EVIDENCE"},
        {"case_id": "KC08_CLEAR_VISUAL_WIN", "product": "Removedor de pelusa reutilizable", "price": 249, "cost": 55, "traffic": 1200, "days": 3, "angle": "antes/despuÃƒÂ©s real en ropa negra sin exagerar", "hook": "Graba una manga negra llena de pelusa y una pasada real del removedor.", "expected": "TEST_SMALL_BUDGET_SANDBOX"},
    ]


def _namespace_for_case(case: dict[str, Any]) -> argparse.Namespace:
    return argparse.Namespace(
        evidence_root=None,
        known_cases=False,
        product_name=case["product"],
        category="known_case",
        market="MX",
        price=case["price"],
        cost=case["cost"],
        traffic=case["traffic"],
        days=case["days"],
        marketing_angle=case["angle"],
        primary_hook=case["hook"],
        target_audience="comprador mexicano de e-commerce",
        use_case=case["angle"],
    )


def run_known_cases(evidence_root: str | None = None) -> str:
    cases_out: list[dict[str, Any]] = []
    passed = 0

    for case in _known_case_inputs():
        args = _namespace_for_case(case)
        scenario = build_scenario(args)
        safety = build_safety_posture(f"{scenario.creative_claim} {scenario.primary_hook} {scenario.marketing_angle}")
        score = evaluate_score(scenario.signals)
        decision = make_decision(scenario, score, safety)
        ok = decision.final_outcome == case["expected"]
        passed += int(ok)
        cases_out.append(
            {
                "case_id": case["case_id"],
                "expected": case["expected"],
                "actual": decision.final_outcome,
                "passed": int(ok),
            }
        )

    args = _namespace_for_case(_known_case_inputs()[0])
    scenario = replace(build_scenario(args), scenario_id="A8-R54-KNOWN-CASES", source="known_cases_contract")
    safety = build_safety_posture("known cases safe anchor")
    decision = Decision(
        decision_id=_stable_id("dec", {"known_cases": cases_out}, length=14),
        score=_round(passed / len(cases_out)),
        threshold=0.75,
        permission_gate="ALLOW_SANDBOX_ONLY" if passed >= 6 else "HOLD",
        final_outcome="KNOWN_CASES_PASS" if passed >= 6 else "KNOWN_CASES_FAIL",
        reason=f"{passed}/{len(cases_out)} known cases matched expected outcomes.",
    )
    creative_pack = generate_creative_pack(scenario, safety)
    evidence_dir = create_evidence_dir(evidence_root)
    evidence_paths = write_evidence(evidence_dir, scenario, safety, decision, creative_pack)
    _safe_json_write(evidence_dir / "known_cases.json", {"cases": cases_out, "passed": passed, "total": len(cases_out)})

    return render_human_output(
        evidence_dir,
        scenario,
        safety,
        decision,
        evidence_paths,
        creative_pack,
        known_case_summary={"cases": cases_out, "passed": passed, "failed": len(cases_out) - passed, "total": len(cases_out)},
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_presets:
        sys.stdout.write(render_preset_list())
        return 0

    if args.known_cases:
        sys.stdout.write(run_known_cases(args.evidence_root))
        return 0

    sys.stdout.write(run_simulation(args.evidence_root, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
