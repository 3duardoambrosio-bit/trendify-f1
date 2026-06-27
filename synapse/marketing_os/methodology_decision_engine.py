"""A8-R104 local marketing methodology decision engine.

The engine consumes the R101/R102/R103 chain:
- R101: methodology data.
- R102: executable rule contract.
- R103: loader and adversarial fixtures.

It makes local decisions only. It does not call external services, create
commerce actions, authorize spend, or certify market performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from synapse.marketing_os.methodology_rule_contract import (
    ExecutableMethodologyContract,
    ExecutableRule,
    evaluate_predicate,
    iter_rules,
)
from synapse.marketing_os.methodology_rule_loader import (
    FixtureValidationReport,
    LoadedMethodologyContract,
    MethodologyRuleLoaderError,
    load_and_validate_adversarial_fixtures,
    load_methodology_contract,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC_PATH = ROOT / "docs" / "phase1" / "A8_R101_MARKETING_METHOD_DEPTH_SPEC.json"
DEFAULT_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "marketing_methodology" / "a8_r103_adversarial_fixtures.json"

EXPECTED_ENGINE_SCHEMA_VERSION = "synapse.marketing_methodology.decision_engine.v1"

BLOCKED_TRIGGER_TERMS = frozenset(
    {
        "claim_rejected",
        "generic_rejected",
        "reject_discount_offer",
        "lower_claim_or_reject",
        "operator_review_required",
        "channel_constraint",
        "cta_softened_or_rejected",
    }
)


class MethodologyDecisionEngineError(ValueError):
    """Raised when the local methodology engine cannot make a safe decision."""


@dataclass(frozen=True)
class MethodologyDecisionInput:
    product_facts: tuple[str, ...]
    buyer_state: str
    proof_available: tuple[str, ...]
    claim_risk: str
    channel: str
    margin_profile: str
    candidate_output: str = ""
    category: str = "unknown"

    def as_context(self) -> dict[str, Any]:
        return {
            "product_facts": list(self.product_facts),
            "buyer_state": self.buyer_state,
            "proof_available": list(self.proof_available),
            "claim_risk": self.claim_risk,
            "channel": self.channel,
            "margin_profile": self.margin_profile,
            "candidate_output": self.candidate_output,
            "category": self.category,
        }


@dataclass(frozen=True)
class RuleDecision:
    rule_id: str
    framework: str
    source_anchor: str
    priority: int
    predicate_matched: bool
    semantic_matched: bool
    missing_fields: tuple[str, ...]
    triggers: tuple[str, ...]
    decision_text: str


@dataclass(frozen=True)
class MarketingMethodologyDecision:
    schema_version: str
    selected_rule_id: str
    selected_framework: str
    status: str
    triggers: tuple[str, ...]
    operator_review_required: bool
    safe_output: str
    rule_decisions: tuple[RuleDecision, ...]

    @property
    def blocked(self) -> bool:
        return self.status == "blocked"


@dataclass(frozen=True)
class EngineRunReport:
    loaded: LoadedMethodologyContract
    fixture_report: FixtureValidationReport
    decision: MarketingMethodologyDecision


def _tuple_str(value: Sequence[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(item) for item in value)


def _lower_values(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(str(item).lower() for item in values)


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _list_contains_any(values: Sequence[str], terms: Sequence[str]) -> bool:
    joined = " ".join(_lower_values(values))
    return any(term in joined for term in terms)


def _context_has_product_specificity(context: Mapping[str, Any]) -> bool:
    facts = context.get("product_facts")
    if not isinstance(facts, Sequence) or isinstance(facts, (str, bytes)):
        return False
    return len([item for item in facts if str(item).strip()]) > 0


def _proof_strength(context: Mapping[str, Any]) -> str:
    proof = context.get("proof_available")
    if not isinstance(proof, Sequence) or isinstance(proof, (str, bytes)):
        return "missing"
    proof_values = _lower_values([str(item) for item in proof if str(item).strip()])
    if not proof_values:
        return "missing"
    joined = " ".join(proof_values)
    if any(term in joined for term in ("weak", "incomplete", "partial", "generic", "unclear")):
        return "weak"
    return "present"


def _semantic_match(rule: ExecutableRule, context: Mapping[str, Any]) -> bool:
    """Deterministic semantic guard above R102 field-presence predicates."""

    when = rule.when.lower()
    rule_id = rule.id
    claim_risk = str(context.get("claim_risk", "")).lower()
    channel = str(context.get("channel", "")).lower()
    margin_profile = str(context.get("margin_profile", "")).lower()
    buyer_state = str(context.get("buyer_state", "")).lower()
    candidate_output = str(context.get("candidate_output", "")).lower()
    proof_strength = _proof_strength(context)
    has_product_facts = _context_has_product_specificity(context)

    if rule_id == "AGR-D001":
        return not has_product_facts
    if rule_id == "AGR-D003":
        return "noun swap" in candidate_output or "perfect for everyone" in candidate_output
    if rule_id == "HOK-D008":
        return not has_product_facts or "noun swap" in candidate_output
    if rule_id == "CLR-D003":
        return claim_risk in {"high", "medical", "safety"}
    if rule_id == "OFF-D002":
        return "tight" in margin_profile
    if rule_id == "PRF-D006":
        return proof_strength == "missing"
    if rule_id == "CHN-D002":
        return channel == "meta" and proof_strength in {"weak", "missing"}
    if rule_id == "CTA-D002":
        return buyer_state in {"cold", "latent"} or proof_strength in {"weak", "missing"}
    if rule_id == "ANG-D001":
        return has_product_facts and proof_strength == "present"
    if rule_id == "ANG-D005":
        return "tight" in margin_profile or "cac" in margin_profile

    if "proof missing" in when or "proof is incomplete" in when or "proof weak" in when:
        return proof_strength in {"missing", "weak"}
    if "proof exists" in when or "demo proof exists" in when or "visual proof" in when:
        return proof_strength == "present"
    if "claim risk high" in when or "risk high" in when or "risky claim" in when:
        return claim_risk in {"high", "medium", "unclear"}
    if "margin is tight" in when or "cac/margin tight" in when or "margin tight" in when:
        return "tight" in margin_profile
    if "meta" in when or "channel is meta" in when:
        return channel == "meta"
    if "category-only" in when or "category only" in when:
        return not has_product_facts
    if "buyer cold" in when or "buyer is cold" in when:
        return buyer_state == "cold"

    return has_product_facts or proof_strength == "present"


def _triggers_for_rule(rule: ExecutableRule, semantic_matched: bool) -> tuple[str, ...]:
    if not semantic_matched:
        return ()

    by_rule = {
        "AGR-D001": ("fallback", "generic_rejected", "operator_review_required"),
        "AGR-D002": ("generic_rejected", "operator_review_required"),
        "AGR-D003": ("generic_rejected",),
        "AGR-D004": ("generic_rejected",),
        "HOK-D008": ("generic_rejected",),
        "CLR-D001": ("claim_rejected", "operator_review_required"),
        "CLR-D003": ("claim_rejected", "safe_rewrite", "operator_review_required"),
        "CLR-D005": ("safe_rewrite",),
        "OFF-D002": ("reject_discount_offer", "operator_review_required"),
        "OFF-D006": ("reject_discount_offer", "operator_review_required"),
        "PRF-D006": ("proof_gap", "lower_claim_or_reject", "operator_review_required"),
        "CHN-D002": ("channel_constraint", "operator_review_required"),
        "CTA-D002": ("cta_softened_or_rejected",),
        "ANG-D001": ("angle_selected", "demo_angle", "tie_break_applied"),
        "ANG-D005": ("tie_break_applied", "economic_fit"),
    }
    if rule.id in by_rule:
        return by_rule[rule.id]

    then = rule.then.lower()
    triggers: list[str] = []
    if "reject" in then:
        triggers.append("generic_rejected")
    if "operator review" in then:
        triggers.append("operator_review_required")
    if "safe_rewrite" in then or "safe rewrite" in then:
        triggers.append("safe_rewrite")
    if "tie_break" in then or "tie-break" in then:
        triggers.append("tie_break_applied")
    if not triggers:
        triggers.append("rule_applied")
    return tuple(dict.fromkeys(triggers))


def _framework_for_rule(contract: ExecutableMethodologyContract, rule_id: str) -> str:
    for framework in contract.frameworks:
        if any(rule.id == rule_id for rule in framework.rules):
            return framework.name
    raise MethodologyDecisionEngineError(f"Rule not found in contract: {rule_id}")


def evaluate_rule_decision(
    contract: ExecutableMethodologyContract,
    rule_id: str,
    decision_input: MethodologyDecisionInput,
) -> RuleDecision:
    rules = {rule.id: rule for rule in iter_rules(contract)}
    if rule_id not in rules:
        raise MethodologyDecisionEngineError(f"Unknown rule id: {rule_id}")

    rule = rules[rule_id]
    predicate_eval = evaluate_predicate(rule.predicate, decision_input.as_context())
    semantic = _semantic_match(rule, decision_input.as_context())
    triggers = _triggers_for_rule(rule, semantic)

    return RuleDecision(
        rule_id=rule.id,
        framework=_framework_for_rule(contract, rule.id),
        source_anchor=rule.source_anchor,
        priority=rule.priority,
        predicate_matched=predicate_eval.matched,
        semantic_matched=semantic,
        missing_fields=tuple(sorted(predicate_eval.missing_fields)),
        triggers=triggers,
        decision_text=rule.then,
    )


def decide_marketing_methodology(
    contract: ExecutableMethodologyContract,
    decision_input: MethodologyDecisionInput,
    candidate_rule_ids: Sequence[str] | None = None,
) -> MarketingMethodologyDecision:
    """Run local deterministic methodology decisions over candidate rules."""

    selected_rules = tuple(candidate_rule_ids) if candidate_rule_ids is not None else tuple(rule.id for rule in iter_rules(contract))
    if not selected_rules:
        raise MethodologyDecisionEngineError("At least one candidate rule id is required")

    decisions = tuple(evaluate_rule_decision(contract, rule_id, decision_input) for rule_id in selected_rules)
    matched = tuple(item for item in decisions if item.semantic_matched)

    if matched:
        selected = sorted(matched, key=lambda item: item.priority, reverse=True)[0]
    else:
        selected = decisions[0]

    triggers = tuple(dict.fromkeys(trigger for item in matched for trigger in item.triggers))
    blocked = any(trigger in BLOCKED_TRIGGER_TERMS for trigger in triggers)
    review = blocked or "operator_review_required" in triggers or not matched

    status = "blocked" if blocked else "accepted" if matched else "fallback"
    output = _safe_output_for_decision(selected, decision_input, status, triggers)

    return MarketingMethodologyDecision(
        schema_version=EXPECTED_ENGINE_SCHEMA_VERSION,
        selected_rule_id=selected.rule_id,
        selected_framework=selected.framework,
        status=status,
        triggers=triggers,
        operator_review_required=review,
        safe_output=output,
        rule_decisions=decisions,
    )


def _safe_output_for_decision(
    selected: RuleDecision,
    decision_input: MethodologyDecisionInput,
    status: str,
    triggers: Sequence[str],
) -> str:
    facts = ", ".join(decision_input.product_facts[:2]) if decision_input.product_facts else "specific product proof"
    category = decision_input.category.strip() or "product"

    if status == "blocked":
        return f"Blocked by {selected.rule_id}; operator review required before using {category} messaging."
    if "demo_angle" in triggers:
        return f"Show the {category} use case with concrete proof: {facts}."
    if "cta_softened_or_rejected" in triggers:
        return f"Use a softer evaluation CTA for {category}; proof is not strong enough for aggressive wording."
    return f"Use methodology rule {selected.rule_id} for {category}, grounded in: {facts}."


def decision_input_from_fixture_context(context: Mapping[str, Any]) -> MethodologyDecisionInput:
    facts = context.get("product_facts", ())
    proof = context.get("proof_available", ())
    if isinstance(facts, (str, bytes)):
        facts = (str(facts),)
    if isinstance(proof, (str, bytes)):
        proof = (str(proof),)

    return MethodologyDecisionInput(
        product_facts=_tuple_str(facts),
        buyer_state=str(context.get("buyer_state", "unknown")),
        proof_available=_tuple_str(proof),
        claim_risk=str(context.get("claim_risk", "unclear")),
        channel=str(context.get("channel", "unknown")),
        margin_profile=str(context.get("margin_profile", "unknown")),
        candidate_output=str(context.get("candidate_output", "")),
        category=str(context.get("category", "product")),
    )


def enforce_adversarial_must_triggers(
    fixture_bundle: Mapping[str, Any],
    contract: ExecutableMethodologyContract,
) -> tuple[MarketingMethodologyDecision, ...]:
    """Execute fixture must_trigger expectations against local engine decisions."""

    scenarios = fixture_bundle.get("scenarios")
    if not isinstance(scenarios, Sequence) or isinstance(scenarios, (str, bytes)):
        raise MethodologyDecisionEngineError("Fixture scenarios must be a sequence")

    decisions: list[MarketingMethodologyDecision] = []
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            raise MethodologyDecisionEngineError("Fixture scenario must be mapping")
        rule_id = str(scenario.get("target_rule_id", "")).strip()
        must_trigger = tuple(str(item) for item in scenario.get("must_trigger", ()))
        context = scenario.get("context")
        if not rule_id or not isinstance(context, Mapping):
            raise MethodologyDecisionEngineError("Fixture scenario missing rule/context")

        decision = decide_marketing_methodology(
            contract,
            decision_input_from_fixture_context(context),
            candidate_rule_ids=(rule_id,),
        )

        missing = tuple(trigger for trigger in must_trigger if trigger not in decision.triggers)
        if missing:
            raise MethodologyDecisionEngineError(
                f"{scenario.get('id')} missing required triggers: {missing}; got={decision.triggers}"
            )

        decisions.append(decision)

    return tuple(decisions)


def load_default_engine_inputs(
    spec_path: Path = DEFAULT_SPEC_PATH,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
) -> tuple[LoadedMethodologyContract, FixtureValidationReport, Mapping[str, Any]]:
    loaded = load_methodology_contract(spec_path)
    fixture_report = load_and_validate_adversarial_fixtures(fixture_path, loaded.contract)

    import json

    fixture_bundle = json.loads(fixture_path.read_text(encoding="utf-8"))
    return loaded, fixture_report, fixture_bundle


def run_engine_against_adversarial_fixtures(
    spec_path: Path = DEFAULT_SPEC_PATH,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
) -> EngineRunReport:
    loaded, fixture_report, fixture_bundle = load_default_engine_inputs(spec_path, fixture_path)
    decisions = enforce_adversarial_must_triggers(fixture_bundle, loaded.contract)
    first_decision = decisions[0]
    return EngineRunReport(
        loaded=loaded,
        fixture_report=fixture_report,
        decision=first_decision,
    )


def category_angle_from_methodology(category: str) -> tuple[str, str, str]:
    """Compatibility wrapper used by legacy category-angle callers."""

    loaded = load_methodology_contract(DEFAULT_SPEC_PATH)
    decision = decide_marketing_methodology(
        loaded.contract,
        MethodologyDecisionInput(
            product_facts=(category,),
            buyer_state="problem-aware",
            proof_available=("category evidence required",),
            claim_risk="low",
            channel="Meta",
            margin_profile="acceptable",
            category=category,
        ),
        candidate_rule_ids=("ANG-D001",),
    )
    proof_line = f"Proof-first offer for {category}; operator review before external use."
    hook_line = f"Show the {category} use case with concrete proof."
    return (decision.safe_output, proof_line, hook_line)