"""A8-R103 loader and adversarial fixture validator.

Scope:
- Load the closed A8-R101 methodology JSON from disk.
- Build the closed A8-R102 executable contract from that loaded spec.
- Load adversarial fixture data from disk.
- Execute contract predicates against fixture contexts.

Non-scope:
- No marketing decision engine.
- No replacement of category-angle behavior.
- No external network, ad platform, spend, or commerce-side action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from synapse.marketing_os.methodology_rule_contract import (
    ExecutableMethodologyContract,
    MethodologyRuleContractError,
    build_contract,
    evaluate_predicate,
    iter_rules,
)

EXPECTED_FIXTURE_SCHEMA_VERSION = "synapse.marketing_methodology.adversarial_fixtures.v1"
EXPECTED_SOURCE_SCHEMA_VERSION = "synapse.marketing_methodology.depth.v1"
EXPECTED_SCENARIO_COUNT = 8


class MethodologyRuleLoaderError(ValueError):
    """Raised when a methodology spec or adversarial fixture bundle is invalid."""


@dataclass(frozen=True)
class LoadedMethodologyContract:
    source_path: Path
    spec: Mapping[str, Any]
    contract: ExecutableMethodologyContract


@dataclass(frozen=True)
class FixtureValidationResult:
    scenario_id: str
    scenario_name: str
    target_rule_id: str
    predicate_matched: bool
    expected_predicate_matched: bool
    missing_fields: tuple[str, ...]
    expected_missing_fields: tuple[str, ...]
    must_trigger: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class FixtureValidationReport:
    schema_version: str
    scenario_count: int
    results: tuple[FixtureValidationResult, ...]

    @property
    def passed(self) -> bool:
        return all(item.predicate_matched == item.expected_predicate_matched for item in self.results)


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MethodologyRuleLoaderError(f"{name} must be a mapping")
    return value


def _require_sequence(value: Any, name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise MethodologyRuleLoaderError(f"{name} must be a sequence")
    return value


def _require_nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MethodologyRuleLoaderError(f"{name} must be a non-empty string")
    return value.strip()


def _tuple_of_strings(value: Any, name: str) -> tuple[str, ...]:
    seq = _require_sequence(value, name)
    out: list[str] = []
    for item in seq:
        out.append(_require_nonempty_str(item, name))
    return tuple(out)


def load_json_document(path: str | Path) -> Mapping[str, Any]:
    """Load a JSON object from disk using UTF-8 and fail closed."""

    resolved = Path(path)
    if not resolved.exists():
        raise MethodologyRuleLoaderError(f"JSON document does not exist: {resolved}")
    if not resolved.is_file():
        raise MethodologyRuleLoaderError(f"JSON document is not a file: {resolved}")
    if resolved.suffix.lower() != ".json":
        raise MethodologyRuleLoaderError(f"JSON document must use .json suffix: {resolved}")

    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MethodologyRuleLoaderError(f"Invalid JSON: {resolved}") from exc

    return _require_mapping(payload, "json_document")


def load_methodology_contract(spec_path: str | Path) -> LoadedMethodologyContract:
    """Load the R101 JSON and build the R102 executable contract."""

    payload = load_json_document(spec_path)
    if payload.get("schema_version") != EXPECTED_SOURCE_SCHEMA_VERSION:
        raise MethodologyRuleLoaderError("Unexpected R101 schema_version")

    try:
        contract = build_contract(payload)
    except MethodologyRuleContractError as exc:
        raise MethodologyRuleLoaderError("R101 spec could not build executable contract") from exc

    return LoadedMethodologyContract(
        source_path=Path(spec_path),
        spec=payload,
        contract=contract,
    )


def _scenario_ids_from_contract(contract: ExecutableMethodologyContract) -> set[str]:
    out: set[str] = set()
    for scenario in contract.adversarial_scenarios:
        out.add(_require_nonempty_str(scenario.get("id"), "contract.adversarial_scenario.id"))
    return out


def _rule_map(contract: ExecutableMethodologyContract) -> dict[str, Any]:
    return {rule.id: rule for rule in iter_rules(contract)}


def validate_adversarial_fixtures(
    fixture_bundle: Mapping[str, Any],
    contract: ExecutableMethodologyContract,
) -> FixtureValidationReport:
    """Validate and execute adversarial fixtures against contract predicates.

    This does not choose marketing decisions. It only confirms that fixture
    contexts can execute the target rule predicates and that expected match/miss
    outcomes are enforced.
    """

    if fixture_bundle.get("schema_version") != EXPECTED_FIXTURE_SCHEMA_VERSION:
        raise MethodologyRuleLoaderError("Unexpected fixture schema_version")
    if fixture_bundle.get("source_schema_version") != EXPECTED_SOURCE_SCHEMA_VERSION:
        raise MethodologyRuleLoaderError("Unexpected fixture source_schema_version")
    if fixture_bundle.get("does_not_implement_engine") is not True:
        raise MethodologyRuleLoaderError("Fixture bundle must declare no engine")
    if fixture_bundle.get("does_not_touch_live_or_spend") is not True:
        raise MethodologyRuleLoaderError("Fixture bundle must declare no live/spend")

    scenarios = tuple(_require_mapping(item, "fixture.scenario") for item in _require_sequence(fixture_bundle.get("scenarios"), "fixture.scenarios"))
    if len(scenarios) != EXPECTED_SCENARIO_COUNT:
        raise MethodologyRuleLoaderError(f"Expected {EXPECTED_SCENARIO_COUNT} fixture scenarios")

    expected_ids = _scenario_ids_from_contract(contract)
    fixture_ids = {_require_nonempty_str(item.get("id"), "fixture.scenario.id") for item in scenarios}
    if fixture_ids != expected_ids:
        raise MethodologyRuleLoaderError(f"Fixture scenario ids do not match contract scenarios: {fixture_ids ^ expected_ids}")

    rules = _rule_map(contract)
    results: list[FixtureValidationResult] = []

    for scenario in scenarios:
        scenario_id = _require_nonempty_str(scenario.get("id"), "scenario.id")
        scenario_name = _require_nonempty_str(scenario.get("name"), f"{scenario_id}.name")
        target_rule_id = _require_nonempty_str(scenario.get("target_rule_id"), f"{scenario_id}.target_rule_id")
        if target_rule_id not in rules:
            raise MethodologyRuleLoaderError(f"{scenario_id} target rule not found: {target_rule_id}")

        context = _require_mapping(scenario.get("context"), f"{scenario_id}.context")
        expected_predicate_matched = scenario.get("expected_predicate_matched")
        if not isinstance(expected_predicate_matched, bool):
            raise MethodologyRuleLoaderError(f"{scenario_id}.expected_predicate_matched must be bool")

        expected_missing = _tuple_of_strings(scenario.get("expected_missing_fields"), f"{scenario_id}.expected_missing_fields")
        must_trigger = _tuple_of_strings(scenario.get("must_trigger"), f"{scenario_id}.must_trigger")

        evaluation = evaluate_predicate(rules[target_rule_id].predicate, context)
        missing_fields = tuple(sorted(evaluation.missing_fields))

        if evaluation.matched != expected_predicate_matched:
            raise MethodologyRuleLoaderError(
                f"{scenario_id} predicate match mismatch: expected={expected_predicate_matched} actual={evaluation.matched}"
            )
        if missing_fields != tuple(sorted(expected_missing)):
            raise MethodologyRuleLoaderError(
                f"{scenario_id} missing fields mismatch: expected={tuple(sorted(expected_missing))} actual={missing_fields}"
            )

        results.append(
            FixtureValidationResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                target_rule_id=target_rule_id,
                predicate_matched=evaluation.matched,
                expected_predicate_matched=expected_predicate_matched,
                missing_fields=missing_fields,
                expected_missing_fields=tuple(sorted(expected_missing)),
                must_trigger=must_trigger,
                reason=evaluation.reason,
            )
        )

    return FixtureValidationReport(
        schema_version=EXPECTED_FIXTURE_SCHEMA_VERSION,
        scenario_count=len(results),
        results=tuple(results),
    )


def load_and_validate_adversarial_fixtures(
    fixture_path: str | Path,
    contract: ExecutableMethodologyContract,
) -> FixtureValidationReport:
    """Load fixture JSON from disk and validate it against an executable contract."""

    fixture_bundle = load_json_document(fixture_path)
    return validate_adversarial_fixtures(fixture_bundle, contract)