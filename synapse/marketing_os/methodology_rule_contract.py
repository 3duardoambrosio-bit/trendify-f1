"""Executable contract for A8-R101 marketing methodology rules.

This module intentionally does not load files, call external systems, run ads,
spend money, create orders, or implement the marketing
decision engine. It converts an in-memory R101 spec dict into deterministic
contract objects and machine-evaluable predicate specs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

EXPECTED_SCHEMA_VERSION = "synapse.marketing_methodology.depth.v1"
EXPECTED_ISLAND = "A8-R101"
EXPECTED_TYPE = "content_depth_spec_no_code_conversion_no_loader_no_engine"

EXPECTED_RULE_COUNT = 82
EXPECTED_FRAMEWORK_COUNT = 15

EXPECTED_MIN_RULE_COUNTS: dict[str, int] = {
    "AudiencePersona": 5,
    "BuyerStateAwareness": 5,
    "ProductFactExtraction": 5,
    "ValuePropositionPositioning": 5,
    "AngleSelection": 8,
    "OfferConstruction": 6,
    "HookConstruction": 8,
    "ObjectionHandling": 6,
    "ProofRequirement": 6,
    "ClaimRisk": 6,
    "ChannelConstraint": 5,
    "CTA": 5,
    "AntiGenericRejection": 4,
    "DecisionTrace": 4,
    "OperatorReview": 4,
}

ALLOWED_SOURCE_ANCHORS: frozenset[str] = frozenset(
    {
        "STP",
        "JTBD",
        "AWARENESS",
        "DIRECT_RESPONSE",
        "PERSUASION",
        "CLAIMS",
        "CHANNEL",
        "SYNAPSE",
    }
)

TOKEN_FIELD_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("proof", "evidence", "demo", "media", "asset", "visual"), "proof_available"),
    (("claim", "guarantee", "medical", "absolute", "risk", "safe"), "claim_risk"),
    (("channel", "meta", "format", "landing", "copy"), "channel"),
    (("margin", "cac", "price", "discount", "aov", "economic"), "margin_profile"),
    (("buyer", "problem", "aware", "unaware", "solution", "cold", "urgent"), "buyer_state"),
    (("product", "fact", "attribute", "mechanism", "category", "sku"), "product_facts"),
    (("objection", "trust", "quality", "fit", "shipping"), "buyer_state"),
)

REJECT_TERMS: frozenset[str] = frozenset({"reject", "block", "fallback", "operator"})


class MethodologyRuleContractError(ValueError):
    """Raised when an R101 spec cannot be represented as an executable contract."""


@dataclass(frozen=True)
class PredicateSpec:
    """Machine-evaluable predicate compiled from a rule's R101 `when` text."""

    predicate_id: str
    source_when: str
    required_presence_fields: tuple[str, ...]
    match_terms: tuple[str, ...]
    rejection_or_fallback_terms: tuple[str, ...]


@dataclass(frozen=True)
class PredicateEvaluation:
    matched: bool
    predicate_id: str
    missing_fields: tuple[str, ...]
    matched_terms: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ExecutableRule:
    id: str
    name: str
    source_anchor: str
    source_logic: str
    when: str
    then: str
    priority: int
    required_inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    anti_generic_gate: str
    rejection_signal: str
    trace_fields: tuple[str, ...]
    deterministic: bool
    predicate: PredicateSpec


@dataclass(frozen=True)
class ExecutableFramework:
    name: str
    purpose: str
    conversion_target: str
    min_rule_count: int
    rules: tuple[ExecutableRule, ...]
    tie_break_order: tuple[str, ...]
    overlap_policy: str
    fallback_policy: str
    route_example_types: tuple[str, ...]
    trace_requirements: tuple[str, ...]


@dataclass(frozen=True)
class ExecutableMethodologyContract:
    schema_version: str
    island: str
    source_type: str
    frameworks: tuple[ExecutableFramework, ...]
    global_anti_generic_gates: tuple[Mapping[str, Any], ...]
    adversarial_scenarios: tuple[Mapping[str, Any], ...]
    no_code_conversion_source: bool
    no_loader_source: bool
    no_engine_source: bool

    @property
    def rule_count(self) -> int:
        return sum(len(framework.rules) for framework in self.frameworks)

    @property
    def framework_count(self) -> int:
        return len(self.frameworks)


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MethodologyRuleContractError(f"{name} must be a mapping")
    return value


def _require_sequence(value: Any, name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise MethodologyRuleContractError(f"{name} must be a sequence")
    return value


def _require_nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MethodologyRuleContractError(f"{name} must be a non-empty string")
    return value.strip()


def _as_tuple_of_strings(value: Any, name: str) -> tuple[str, ...]:
    seq = _require_sequence(value, name)
    out: list[str] = []
    for item in seq:
        out.append(_require_nonempty_str(item, name))
    if not out:
        raise MethodologyRuleContractError(f"{name} must not be empty")
    return tuple(out)


def _tokens(text: str) -> tuple[str, ...]:
    cleaned = []
    for char in text.lower():
        if char.isalnum() or char in {"_", "-"}:
            cleaned.append(char)
        else:
            cleaned.append(" ")
    stop = {"a", "an", "and", "or", "the", "is", "are", "to", "if", "when", "then", "with", "as", "of"}
    return tuple(token for token in "".join(cleaned).split() if token and token not in stop)


def compile_predicate(rule: Mapping[str, Any]) -> PredicateSpec:
    """Compile an R101 rule dictionary into a structured predicate spec.

    The compiler is deterministic. It does not interpret marketing quality; it
    turns the declared `when` text into explicit field-presence requirements
    using stable token-field rules, while retaining traceable source text.
    """

    rule_id = _require_nonempty_str(rule.get("id"), "rule.id")
    when = _require_nonempty_str(rule.get("when"), f"{rule_id}.when")
    token_set = set(_tokens(when))

    required_fields: list[str] = []
    for terms, field in TOKEN_FIELD_RULES:
        if token_set.intersection(terms) and field not in required_fields:
            required_fields.append(field)

    required_inputs = list(_as_tuple_of_strings(rule.get("required_inputs"), f"{rule_id}.required_inputs"))
    if not required_fields:
        required_fields.append(required_inputs[0])

    normalized_required = tuple(field for field in required_fields if field in required_inputs)
    if not normalized_required:
        normalized_required = (required_inputs[0],)

    rejection_terms = tuple(sorted(token_set.intersection(REJECT_TERMS)))
    match_terms = tuple(sorted(token for token in token_set if len(token) >= 4))

    return PredicateSpec(
        predicate_id=f"predicate:{rule_id}",
        source_when=when,
        required_presence_fields=normalized_required,
        match_terms=match_terms,
        rejection_or_fallback_terms=rejection_terms,
    )


def evaluate_predicate(predicate: PredicateSpec, context: Mapping[str, Any]) -> PredicateEvaluation:
    """Evaluate a PredicateSpec against an in-memory context.

    This is intentionally small and deterministic. The decision engine is not
    implemented here; this only proves that R102 predicates are machine-
    evaluable and produce traceable match/miss output.
    """

    missing: list[str] = []
    for field in predicate.required_presence_fields:
        value = context.get(field)
        if value in (None, "", [], {}, ()):
            missing.append(field)

    matched = not missing
    return PredicateEvaluation(
        matched=matched,
        predicate_id=predicate.predicate_id,
        missing_fields=tuple(missing),
        matched_terms=predicate.match_terms,
        reason="matched_required_presence" if matched else "missing_required_presence",
    )


def build_rule(rule: Mapping[str, Any]) -> ExecutableRule:
    rule_id = _require_nonempty_str(rule.get("id"), "rule.id")
    source_anchor = _require_nonempty_str(rule.get("source_anchor"), f"{rule_id}.source_anchor")
    if source_anchor not in ALLOWED_SOURCE_ANCHORS:
        raise MethodologyRuleContractError(f"{rule_id}.source_anchor invalid: {source_anchor}")

    deterministic = rule.get("deterministic")
    if deterministic is not True:
        raise MethodologyRuleContractError(f"{rule_id}.deterministic must be true")

    priority = rule.get("priority")
    if not isinstance(priority, int):
        raise MethodologyRuleContractError(f"{rule_id}.priority must be int")

    trace_fields = _as_tuple_of_strings(rule.get("trace_fields"), f"{rule_id}.trace_fields")
    for required_trace in ("rule_id", "source_anchor"):
        if required_trace not in trace_fields:
            raise MethodologyRuleContractError(f"{rule_id}.trace_fields missing {required_trace}")

    predicate = compile_predicate(rule)

    return ExecutableRule(
        id=rule_id,
        name=_require_nonempty_str(rule.get("name"), f"{rule_id}.name"),
        source_anchor=source_anchor,
        source_logic=_require_nonempty_str(rule.get("source_logic"), f"{rule_id}.source_logic"),
        when=_require_nonempty_str(rule.get("when"), f"{rule_id}.when"),
        then=_require_nonempty_str(rule.get("then"), f"{rule_id}.then"),
        priority=priority,
        required_inputs=_as_tuple_of_strings(rule.get("required_inputs"), f"{rule_id}.required_inputs"),
        outputs=_as_tuple_of_strings(rule.get("outputs"), f"{rule_id}.outputs"),
        anti_generic_gate=_require_nonempty_str(rule.get("anti_generic_gate"), f"{rule_id}.anti_generic_gate"),
        rejection_signal=_require_nonempty_str(rule.get("rejection_signal"), f"{rule_id}.rejection_signal"),
        trace_fields=trace_fields,
        deterministic=deterministic,
        predicate=predicate,
    )


def build_framework(framework: Mapping[str, Any]) -> ExecutableFramework:
    name = _require_nonempty_str(framework.get("name"), "framework.name")
    if name not in EXPECTED_MIN_RULE_COUNTS:
        raise MethodologyRuleContractError(f"Unexpected framework: {name}")

    rules = tuple(build_rule(_require_mapping(rule, f"{name}.rule")) for rule in _require_sequence(framework.get("decision_rules"), f"{name}.decision_rules"))
    minimum = EXPECTED_MIN_RULE_COUNTS[name]
    if len(rules) < minimum:
        raise MethodologyRuleContractError(f"{name} below min rule count: {len(rules)} < {minimum}")

    priorities = [rule.priority for rule in rules]
    if len(set(priorities)) != len(priorities):
        raise MethodologyRuleContractError(f"{name} has duplicate priorities")

    determinism = _require_mapping(framework.get("global_determinism"), f"{name}.global_determinism")
    route_examples = _require_sequence(framework.get("route_examples"), f"{name}.route_examples")
    route_types = tuple(sorted(_require_nonempty_str(_require_mapping(example, f"{name}.route_example").get("type"), f"{name}.route_example.type") for example in route_examples))
    if set(route_types) != {"acceptance", "fallback", "rejection"}:
        raise MethodologyRuleContractError(f"{name} route examples must include acceptance/rejection/fallback")

    return ExecutableFramework(
        name=name,
        purpose=_require_nonempty_str(framework.get("purpose"), f"{name}.purpose"),
        conversion_target=_require_nonempty_str(framework.get("conversion_target"), f"{name}.conversion_target"),
        min_rule_count=minimum,
        rules=rules,
        tie_break_order=_as_tuple_of_strings(determinism.get("tie_break_order"), f"{name}.tie_break_order"),
        overlap_policy=_require_nonempty_str(determinism.get("overlap_policy"), f"{name}.overlap_policy"),
        fallback_policy=_require_nonempty_str(determinism.get("fallback_policy"), f"{name}.fallback_policy"),
        route_example_types=route_types,
        trace_requirements=_as_tuple_of_strings(framework.get("trace_requirements"), f"{name}.trace_requirements"),
    )


def build_contract(spec: Mapping[str, Any]) -> ExecutableMethodologyContract:
    """Build an executable contract from an in-memory A8-R101 spec dictionary."""

    if spec.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise MethodologyRuleContractError("Unexpected schema_version")
    if spec.get("island") != EXPECTED_ISLAND:
        raise MethodologyRuleContractError("Unexpected island")
    if spec.get("type") != EXPECTED_TYPE:
        raise MethodologyRuleContractError("Unexpected source type")

    gates = _require_mapping(spec.get("depth_gates"), "depth_gates")
    if gates.get("no_code_conversion") is not True or gates.get("no_loader") is not True or gates.get("no_engine") is not True:
        raise MethodologyRuleContractError("R101 source gates must remain no_code/no_loader/no_engine")

    frameworks = tuple(build_framework(_require_mapping(framework, "framework")) for framework in _require_sequence(spec.get("frameworks"), "frameworks"))
    if len(frameworks) != EXPECTED_FRAMEWORK_COUNT:
        raise MethodologyRuleContractError(f"Expected {EXPECTED_FRAMEWORK_COUNT} frameworks")
    if {framework.name for framework in frameworks} != set(EXPECTED_MIN_RULE_COUNTS):
        raise MethodologyRuleContractError("Framework set mismatch")

    contract = ExecutableMethodologyContract(
        schema_version=EXPECTED_SCHEMA_VERSION,
        island=EXPECTED_ISLAND,
        source_type=EXPECTED_TYPE,
        frameworks=frameworks,
        global_anti_generic_gates=tuple(_require_mapping(gate, "global_anti_generic_gate") for gate in _require_sequence(spec.get("global_anti_generic_gates"), "global_anti_generic_gates")),
        adversarial_scenarios=tuple(_require_mapping(scenario, "adversarial_scenario") for scenario in _require_sequence(spec.get("adversarial_scenarios"), "adversarial_scenarios")),
        no_code_conversion_source=True,
        no_loader_source=True,
        no_engine_source=True,
    )

    if contract.rule_count != EXPECTED_RULE_COUNT:
        raise MethodologyRuleContractError(f"Expected {EXPECTED_RULE_COUNT} rules, got {contract.rule_count}")
    if len(contract.global_anti_generic_gates) < 8:
        raise MethodologyRuleContractError("Expected at least 8 global anti-generic gates")
    if len(contract.adversarial_scenarios) < 8:
        raise MethodologyRuleContractError("Expected at least 8 adversarial scenarios")

    return contract


def iter_rules(contract: ExecutableMethodologyContract) -> tuple[ExecutableRule, ...]:
    """Return all executable rules in deterministic framework/rule order."""

    rules: list[ExecutableRule] = []
    for framework in contract.frameworks:
        rules.extend(sorted(framework.rules, key=lambda rule: rule.priority, reverse=True))
    return tuple(rules)