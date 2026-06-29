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
    missing_terms = (
        "no proof",
        "no certificate",
        "no clinical proof",
        "no before-after",
        "no motor test",
        "photos only",
        "images only",
        "static product photos",
        "supplier photos only",
        "supplier images only",
        "generic room photos",
    )
    weak_terms = ("weak", "incomplete", "partial", "generic", "unclear", "mixed reviews")

    if any(term in joined for term in missing_terms):
        return "missing"
    if any(term in joined for term in weak_terms):
        return "weak"
    return "present"


def _semantic_match(rule: ExecutableRule, context: Mapping[str, Any]) -> bool:
    """Deterministic semantic guard above R102 field-presence predicates.

    A8-R104.1 change:
    - No permissive match-all fallback.
    - Rule families only match when context values justify them.
    - Blind products with proof can reach an accepted angle.
    """

    when = rule.when.lower()
    rule_id = rule.id
    claim_risk = str(context.get("claim_risk", "")).lower()
    channel = str(context.get("channel", "")).lower()
    margin_profile = str(context.get("margin_profile", "")).lower()
    buyer_state = str(context.get("buyer_state", "")).lower()
    candidate_output = str(context.get("candidate_output", "")).lower()
    category = str(context.get("category", "")).lower()
    proof_strength = _proof_strength(context)
    has_product_facts = _context_has_product_specificity(context)

    facts = context.get("product_facts")
    fact_terms = ()
    if isinstance(facts, Sequence) and not isinstance(facts, (str, bytes)):
        fact_terms = _lower_values([str(item) for item in facts])

    saturated_or_generic = (
        "common saturated" in " ".join(fact_terms)
        or "saturated" in category
        or "perfect room decoration" in candidate_output
        or "perfect for everyone" in candidate_output
        or "noun swap" in candidate_output
    )

    risky_claim = claim_risk in {"high", "medical", "safety"}
    tight_margin = "tight" in margin_profile
    meta_with_weak_proof = channel == "meta" and proof_strength in {"weak", "missing"}

    if rule_id == "AGR-D001":
        return not has_product_facts or saturated_or_generic
    if rule_id == "AGR-D003":
        return saturated_or_generic
    if rule_id == "HOK-D008":
        return not has_product_facts or saturated_or_generic
    if rule_id == "CLR-D003":
        return risky_claim
    if rule_id == "OFF-D002":
        return tight_margin
    if rule_id == "PRF-D006":
        return proof_strength == "missing"
    if rule_id == "CHN-D002":
        return meta_with_weak_proof
    if rule_id == "CTA-D002":
        return buyer_state in {"cold", "latent"} or proof_strength in {"weak", "missing"}
    if rule_id == "ANG-D001":
        return has_product_facts and proof_strength == "present" and not risky_claim and not saturated_or_generic
    if rule_id == "ANG-D005":
        return has_product_facts and proof_strength == "present" and not risky_claim and tight_margin

    if "proof missing" in when or "proof is incomplete" in when or "proof weak" in when:
        return proof_strength in {"missing", "weak"}
    if "proof exists" in when or "demo proof exists" in when or "visual proof" in when:
        return has_product_facts and proof_strength == "present" and not risky_claim
    if "claim risk high" in when or "risk high" in when or "risky claim" in when:
        return risky_claim
    if "margin is tight" in when or "cac/margin tight" in when or "margin tight" in when:
        return tight_margin
    if "meta" in when or "channel is meta" in when:
        return meta_with_weak_proof
    if "category-only" in when or "category only" in when:
        return not has_product_facts
    if "buyer cold" in when or "buyer is cold" in when:
        return buyer_state == "cold"

    return False


def _candidate_rule_ids_for_context(
    contract: ExecutableMethodologyContract,
    context: Mapping[str, Any],
) -> tuple[str, ...]:
    """Select a small context-relevant rule set instead of running all 82 rules."""

    available = {rule.id for rule in iter_rules(contract)}
    selected: list[str] = []

    def add(*rule_ids: str) -> None:
        for rule_id in rule_ids:
            if rule_id in available and rule_id not in selected:
                selected.append(rule_id)

    claim_risk = str(context.get("claim_risk", "")).lower()
    channel = str(context.get("channel", "")).lower()
    margin_profile = str(context.get("margin_profile", "")).lower()
    buyer_state = str(context.get("buyer_state", "")).lower()
    candidate_output = str(context.get("candidate_output", "")).lower()
    category = str(context.get("category", "")).lower()
    proof_strength = _proof_strength(context)
    has_product_facts = _context_has_product_specificity(context)

    facts = context.get("product_facts")
    fact_terms = ()
    if isinstance(facts, Sequence) and not isinstance(facts, (str, bytes)):
        fact_terms = _lower_values([str(item) for item in facts])

    risky_claim = claim_risk in {"high", "medical", "safety"}
    tight_margin = "tight" in margin_profile
    saturated_or_generic = (
        "common saturated" in " ".join(fact_terms)
        or "saturated" in category
        or "perfect room decoration" in candidate_output
        or "perfect for everyone" in candidate_output
        or "noun swap" in candidate_output
    )

    if risky_claim:
        add("CLR-D003", "PRF-D006", "CHN-D002", "CTA-D002")
    if proof_strength in {"missing", "weak"}:
        add("PRF-D006", "CHN-D002", "CTA-D002")
    if tight_margin:
        add("OFF-D002", "OFF-D006", "ANG-D005")
    if saturated_or_generic or buyer_state == "cold":
        add("AGR-D001", "AGR-D003", "HOK-D008", "CTA-D002")
    if has_product_facts and proof_strength == "present" and not risky_claim and not saturated_or_generic:
        add("ANG-D001")

    if not selected:
        add("CTA-D002", "ANG-D001")

    return tuple(selected)


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


def _selection_rank_for_context(
    decision: RuleDecision,
    context: Mapping[str, Any],
) -> tuple[int, int]:
    """Rank matched rules by business context, not raw rule priority alone.

    A8-R104.1R2 change:
    - Risk/safety beats everything.
    - Tight margin economics beats generic channel constraint.
    - Generic/saturated rejection beats proof/channel fallbacks.
    - Proof/channel rules remain useful but should not dominate all cases.
    """

    claim_risk = str(context.get("claim_risk", "")).lower()
    channel = str(context.get("channel", "")).lower()
    margin_profile = str(context.get("margin_profile", "")).lower()
    buyer_state = str(context.get("buyer_state", "")).lower()
    candidate_output = str(context.get("candidate_output", "")).lower()
    category = str(context.get("category", "")).lower()
    proof_strength = _proof_strength(context)

    facts = context.get("product_facts")
    fact_terms = ()
    if isinstance(facts, Sequence) and not isinstance(facts, (str, bytes)):
        fact_terms = _lower_values([str(item) for item in facts])

    risky_claim = claim_risk in {"high", "medical", "safety"}
    tight_margin = "tight" in margin_profile
    saturated_or_generic = (
        "common saturated" in " ".join(fact_terms)
        or "saturated" in category
        or "perfect room decoration" in candidate_output
        or "perfect for everyone" in candidate_output
        or "noun swap" in candidate_output
        or buyer_state == "cold"
    )
    meta_with_weak_proof = channel == "meta" and proof_strength in {"weak", "missing"}

    rule_id = decision.rule_id

    if risky_claim and rule_id in {"CLR-D003", "CLR-D001", "CLR-D005"}:
        family_rank = 900
    elif tight_margin and rule_id in {"OFF-D002", "OFF-D006", "ANG-D005"}:
        family_rank = 800
    elif saturated_or_generic and rule_id in {"AGR-D001", "AGR-D003", "HOK-D008", "CTA-D002"}:
        family_rank = 700
    elif proof_strength == "missing" and rule_id in {"PRF-D006", "CTA-D002"}:
        family_rank = 600
    elif meta_with_weak_proof and rule_id in {"CHN-D002", "CTA-D002"}:
        family_rank = 500
    elif rule_id.startswith("ANG-"):
        family_rank = 400
    else:
        family_rank = 100

    return (family_rank, decision.priority)



def decide_marketing_methodology(
    contract: ExecutableMethodologyContract,
    decision_input: MethodologyDecisionInput,
    candidate_rule_ids: Sequence[str] | None = None,
) -> MarketingMethodologyDecision:
    """Run local deterministic methodology decisions over context-relevant rules."""

    context = decision_input.as_context()
    selected_rules = (
        tuple(candidate_rule_ids)
        if candidate_rule_ids is not None
        else _candidate_rule_ids_for_context(contract, context)
    )
    if not selected_rules:
        raise MethodologyDecisionEngineError("At least one candidate rule id is required")

    decisions = tuple(evaluate_rule_decision(contract, rule_id, decision_input) for rule_id in selected_rules)
    matched = tuple(item for item in decisions if item.semantic_matched)

    if matched:
        selected = sorted(
            matched,
            key=lambda item: _selection_rank_for_context(item, context),
            reverse=True,
        )[0]
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


def _compact_list(values: Sequence[str], limit: int = 2) -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if not cleaned:
        return "specific product evidence"
    return ", ".join(cleaned[:limit])


def _primary_fact(decision_input: MethodologyDecisionInput) -> str:
    for fact in decision_input.product_facts:
        clean = str(fact).strip()
        if clean:
            return clean
    return decision_input.category.strip() or "product proof"


def _primary_proof(decision_input: MethodologyDecisionInput) -> str:
    for proof in decision_input.proof_available:
        clean = str(proof).strip()
        if clean:
            return clean
    return "visible proof"


def _category_problem(category: str) -> str:
    cat = category.strip().lower()
    if "pet hair" in cat:
        return "pet hair left on sofa fabric or clothing"
    if "bottle" in cat:
        return "travel leaks, bag mess, or bulky bottles"
    if "oil" in cat or "sprayer" in cat:
        return "a low-margin kitchen accessory that cannot carry a discount-led offer"
    if "led" in cat or "strip" in cat:
        return "a generic room-lighting product with many lookalike alternatives"
    if "serum" in cat:
        return "beauty claims that imply skin results without proof"
    if "posture" in cat:
        return "body or pain-related claims that need stronger support"
    if "car phone" in cat or "holder" in cat:
        return "safety or reliability claims in a car-use context"
    if "blender" in cat:
        return "performance claims that imply power or durability beyond evidence"
    return f"the specific buyer problem for {category.strip() or 'this product'}"


def _buyer_state_guidance(decision_input: MethodologyDecisionInput) -> str:
    state = decision_input.buyer_state.strip().lower()
    category = decision_input.category.strip() or "product"
    fact = _primary_fact(decision_input)
    problem = _category_problem(category)

    if state in {"cold", "latent"}:
        return (
            f"For a cold buyer, make {problem} visible before naming {category}; "
            f"use {fact} as proof, not as a hard sell."
        )
    if state in {"skeptical", "doubtful"}:
        return (
            f"For a skeptical buyer, lead with {fact} and show the proof sequence before any CTA; "
            f"the message must use visible proof and reduce trust friction around {problem}."
        )
    if state in {"warm", "pain-aware", "problem-aware"}:
        return (
            f"For a warm buyer already aware of {problem}, connect {category} directly to {fact} "
            f"and move from active pain point to proof to comparison before a margin-safe next step."
        )
    if state in {"solution-aware", "ready"}:
        return (
            f"For a ready buyer, compare {category}'s concrete proof ({fact}) against the main alternative, "
            f"then ask for the next step."
        )
    return (
        f"Match the buyer's state to {problem}; make {fact} the reason the message is credible."
    )


def _channel_guidance(decision_input: MethodologyDecisionInput) -> str:
    channel = decision_input.channel.strip() or "selected channel"
    ch = channel.lower()
    category = decision_input.category.strip() or "product"
    fact = _primary_fact(decision_input)
    proof = _primary_proof(decision_input)

    if ch == "meta":
        if "pet hair" in category.lower():
            return (
                f"Meta note: first frame shows the messy fabric, second frame shows {fact}, "
                f"third frame shows {proof}; keep copy short and proof-led."
            )
        if "bottle" in category.lower():
            return (
                f"Meta note: first frame shows the travel/bag problem, second frame shows {fact}, "
                f"third frame uses {proof}; avoid a discount-first ad."
            )
        return (
            f"Meta note: open with the visual problem for {category}, then show {fact} before the CTA."
        )
    if ch in {"tiktok", "short_video"}:
        return (
            f"Short-video note: start with the product action for {category}, then caption the proof: {proof}."
        )
    if ch in {"search", "google"}:
        return (
            f"Search note: use buyer-comparison wording around {category}, {fact}, and {proof}."
        )
    return (
        f"Channel note: adapt {category}'s proof scene ({fact}) to {channel} before writing the CTA."
    )


def _objection_guidance(decision_input: MethodologyDecisionInput) -> str:
    state = decision_input.buyer_state.strip().lower()
    category = decision_input.category.strip() or "product"
    facts = " ".join(decision_input.product_facts).lower()
    proof = " ".join(decision_input.proof_available).lower()

    if "before-after" in facts or "before-after" in proof:
        return (
            f"Objection handled: buyer may doubt {category} works, so make the before-after proof the hero."
        )
    if "leak" in facts or "silicone" in facts or "bottle" in category.lower():
        return (
            "Objection handled: buyer may worry about leaks, bulk, or travel mess, "
            "so show the anti-leak/foldable detail before the CTA."
        )
    if state in {"cold", "latent"}:
        return (
            f"Objection handled: buyer is not actively shopping for {category}, so show the problem first."
        )
    return (
        f"Objection handled: buyer needs proof before promise, so tie {category} only to the evidence shown."
    )


def _offer_margin_guidance(decision_input: MethodologyDecisionInput) -> str:
    margin = decision_input.margin_profile.strip().lower()
    category = decision_input.category.strip() or "product"
    fact = _primary_fact(decision_input)
    proof = _primary_proof(decision_input)

    if "tight" in margin or "low" in margin:
        return (
            f"Offer/margin: avoid discounting {category}; build the offer around proof of {fact}, "
            f"a bundle/value frame, and a soft comparison CTA."
        )
    if "healthy" in margin or "strong" in margin:
        return (
            f"Offer/margin: use {fact} as the value reason, keep margin protected with a proof-led bundle or threshold offer, "
            f"and avoid promising more than {proof} supports."
        )
    return (
        f"Offer/margin: do not lead with price; frame {category} around {fact}, then test a margin-safe CTA."
    )


def _cta_guidance(decision_input: MethodologyDecisionInput) -> str:
    category = decision_input.category.strip() or "product"
    fact = _primary_fact(decision_input)
    margin = decision_input.margin_profile.strip().lower()

    if "tight" in margin or "low" in margin:
        return (
            f"CTA: ask the operator to test a proof-first angle for {category}; CTA should compare value from {fact}, not discount."
        )
    return (
        f"CTA: invite the buyer to watch the proof, then compare whether {category}'s {fact} solves the shown problem."
    )


def _blocked_primary_reason(rule_id: str, decision_input: MethodologyDecisionInput) -> str:
    category = decision_input.category.strip() or "product"
    fact = _primary_fact(decision_input)
    problem = _category_problem(category)

    if rule_id.startswith("CLR-"):
        return (
            f"claim safety: for {category}, current wording risks implying {problem} is solved beyond the available proof ({fact})."
        )
    if rule_id.startswith("OFF-"):
        return (
            f"offer economics: for {category}, margin cannot support a broad discount or weak offer; proof/value framing is required."
        )
    if rule_id.startswith("AGR-") or rule_id.startswith("HOK-"):
        return (
            f"generic positioning: for {category}, the message lacks a specific product fact and a product-specific reason to care beyond {fact}. It must replace category-only wording with a visible use case."
        )
    if rule_id.startswith("PRF-"):
        return (
            f"proof gap: for {category}, evidence is not strong enough to support the proposed angle."
        )
    if rule_id.startswith("CHN-"):
        return (
            f"channel constraint: for {category}, the selected channel needs stronger proof before the message is safe."
        )
    if rule_id.startswith("CTA-"):
        return (
            f"CTA risk: for {category}, buyer state does not support an aggressive next step yet."
        )
    return f"methodology risk for {category}: operator review is required before using this message."


def _blocked_operator_action(rule_id: str, decision_input: MethodologyDecisionInput) -> str:
    category = decision_input.category.strip() or "product"
    fact = _primary_fact(decision_input)

    if rule_id.startswith("CLR-"):
        return (
            f"Operator action: remove the risky {category} claim, keep only the supported fact '{fact}', "
            f"or collect stronger proof before review."
        )
    if rule_id.startswith("OFF-"):
        return (
            f"Operator action: rebuild the {category} offer around bundle value, proof, or margin-safe framing; "
            f"do not use broad discount language."
        )
    if rule_id.startswith("AGR-") or rule_id.startswith("HOK-"):
        return (
            f"Operator action: replace category-only wording with '{fact}' plus one visible use case."
        )
    if rule_id.startswith("PRF-"):
        return f"Operator action: collect a clearer demo for {category} before acquisition messaging."
    if rule_id.startswith("CHN-"):
        return f"Operator action: adapt {category} to a proof-first channel format before testing."
    return f"Operator action: rewrite {category} with proof, buyer state, and a safer CTA."


def _safe_output_for_decision(
    selected: RuleDecision,
    decision_input: MethodologyDecisionInput,
    status: str,
    triggers: Sequence[str],
) -> str:
    facts = _compact_list(decision_input.product_facts, limit=2)
    proof = _compact_list(decision_input.proof_available, limit=2)
    category = decision_input.category.strip() or "product"
    buyer_state = decision_input.buyer_state.strip() or "unspecified buyer"
    channel = decision_input.channel.strip() or "selected channel"

    if status == "blocked":
        primary_reason = _blocked_primary_reason(selected.rule_id, decision_input)
        action = _blocked_operator_action(selected.rule_id, decision_input)
        return (
            f"Blocked: do not use the current {category} message yet. "
            f"Primary reason: {primary_reason} "
            f"Evidence checked: {facts}; proof available: {proof}. "
            f"{action} "
            f"Operator review required. "
            f"Safe next step: create a proof-safe rewrite for a {buyer_state} buyer on {channel}, then review before use."
        )

    if status == "fallback":
        return (
            f"Fallback: no expert-safe {category} angle selected yet. "
            f"Evidence checked: {facts}. "
            f"Buyer fit: {_buyer_state_guidance(decision_input)} "
            f"Offer/margin: {_offer_margin_guidance(decision_input)} "
            f"Safe next step: gather stronger proof ({proof}) and rerun the methodology before operator use."
        )

    hook = (
        f"Hook: show {category} solving {_category_problem(category)} with {facts}, "
        f"then prove it with {proof}."
    )
    buyer_fit = f"Buyer fit: {_buyer_state_guidance(decision_input)}"
    objection = _objection_guidance(decision_input)
    offer_margin = _offer_margin_guidance(decision_input)
    cta = _cta_guidance(decision_input)
    channel_note = _channel_guidance(decision_input)
    operator_asset = (
        f"Operator asset: build the first creative around '{facts}' as the proof scene, "
        f"state the offer as margin-safe value before price, keep the claim narrower than the evidence, "
        f"and use the CTA only after the proof is visible."
    )

    return " ".join((hook, buyer_fit, objection, offer_margin, cta, channel_note, operator_asset))


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