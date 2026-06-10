from __future__ import annotations

import inspect
import json

from synapse.financial.evaluation import Decision
from synapse.integration.a8_r70_smoke import (
    SMOKE_SCHEMA_VERSION,
    SmokeDecision,
    run_a8_r70_smoke_integration,
)
from synapse.safety.spend_guard import GuardDecision, GuardReasonCode
from tools.nogo_ast_resolver import scan_source_for_forbidden_strings


def test_a8_r70_smoke_integration_runs_discovery_financial_brief_decision_end_to_end():
    result = run_a8_r70_smoke_integration()

    assert result.schema_version == SMOKE_SCHEMA_VERSION
    assert result.candidate.source_type == "synthetic"
    assert result.financial_input.product_id == result.candidate.candidate_id
    assert result.financial_input.name == result.candidate.product_name
    assert result.financial_result.product_id == result.candidate.candidate_id
    assert result.financial_result.decision in {
        Decision.PASS,
        Decision.WATCH,
        Decision.FAIL,
        Decision.KILL,
    }

    assert result.guard_trail.evaluation.decision is GuardDecision.ALLOW
    assert result.guard_trail.evaluation.reason_codes == (
        GuardReasonCode.SANDBOX_ACTION_ALLOWED.value,
    )

    assert result.guard_trail.spend_probe.decision is GuardDecision.BLOCK
    assert result.guard_trail.spend_probe.reason_codes == (
        GuardReasonCode.BLOCKED_SPEND_REQUIRES_AUTHORIZATION.value,
    )

    assert result.guard_trail.mutation_probe.decision is GuardDecision.BLOCK
    assert (
        GuardReasonCode.BLOCKED_LIVE_CHANNEL_REQUIRES_AUTHORIZATION.value
        in result.guard_trail.mutation_probe.reason_codes
    )
    assert (
        GuardReasonCode.BLOCKED_EXTERNAL_MUTATION_REQUIRES_AUTHORIZATION.value
        in result.guard_trail.mutation_probe.reason_codes
    )

    assert result.decision_record.schema_version == SMOKE_SCHEMA_VERSION
    assert result.decision_record.candidate_id == result.candidate.candidate_id
    assert result.decision_record.spend_guard_allowed is True
    assert result.decision_record.mutation_guard_blocked is True
    assert result.decision_record.final_decision in {
        SmokeDecision.READY_FOR_SANDBOX_BRIEF,
        SmokeDecision.WATCH_SANDBOX_BRIEF_ONLY,
        SmokeDecision.BLOCKED_BY_FINANCIALS,
        SmokeDecision.BLOCKED_BY_SPEND_GUARD,
    }

    if result.decision_record.brief_built:
        assert result.marketing_brief is not None
        assert result.marketing_brief["product_id"] == result.candidate.candidate_id
        assert result.marketing_brief["permission"]["status"] in {
            "allowed",
            "review_required",
        }
        assert result.marketing_brief["anti_npc_checks"]["passed"] is True
    else:
        assert result.marketing_brief is None
        assert result.decision_record.final_decision in {
            SmokeDecision.BLOCKED_BY_FINANCIALS,
            SmokeDecision.BLOCKED_BY_SPEND_GUARD,
        }

    payload = result.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert result.candidate.candidate_id in encoded
    assert payload["decision_record"]["brief_built"] is result.decision_record.brief_built
    assert payload["guard_trail"]["evaluation"]["decision"] == "ALLOW"
    assert payload["guard_trail"]["spend_probe"]["decision"] == "BLOCK"
    assert payload["guard_trail"]["mutation_probe"]["decision"] == "BLOCK"


def test_a8_r70_smoke_integration_is_deterministic():
    first = run_a8_r70_smoke_integration().to_dict()
    second = run_a8_r70_smoke_integration().to_dict()

    assert first == second


def test_a8_r70_smoke_integration_routes_spend_and_mutation_through_guard_source_contract():
    import synapse.integration.a8_r70_smoke as smoke

    source = inspect.getsource(smoke)

    assert "evaluate_spend_guard" in source
    assert "GuardIntent.SPEND" in source
    assert "GuardIntent.MUTATE" in source
    assert 'channel="shopify_admin"' in source
    assert '"shop" + "ify" + "_admin"' not in source

    channel_findings = scan_source_for_forbidden_strings(source, ("shopify_admin",))
    assert any(f.value == "shopify_admin" for f in channel_findings)

    forbidden = (
        "requests.",
        "httpx.",
        "urllib.request",
        "aiohttp",
        "selenium",
        "playwright",
        "BeautifulSoup",
        "network_port_api.",
        "os.system",
        "subprocess",
    )

    findings = scan_source_for_forbidden_strings(source, forbidden)
    assert findings == []


# A8_R70I1R_SCAN_SAFE_RUNTIME_SURFACE_ASSERTION

from pathlib import Path as _A8R70SmokePath


def _a8_r70i1r_runtime_blocklist() -> tuple[str, ...]:
    return (
        "requests.",
        "httpx.",
        "urllib.request",
        "subprocess",
        "socket",
        "boto3",
        "dropi",
        "facebook_business",
        "openai",
        "LIVE_WRITE",
        "LIVE_SPEND",
    )


def test_a8_r70_smoke_module_blocks_runtime_surfaces_scan_safe() -> None:
    source = _A8R70SmokePath("synapse/integration/a8_r70_smoke.py").read_text(
        encoding="utf-8"
    )

    findings = scan_source_for_forbidden_strings(
        source, _a8_r70i1r_runtime_blocklist()
    )
    assert findings == []
