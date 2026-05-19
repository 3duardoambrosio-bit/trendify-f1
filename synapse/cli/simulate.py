"""Visible single-scenario simulation runner for SYNAPSE.

A8-R53 contract:
- local-only
- deterministic
- human-readable
- sandbox evidence only
- no Shopify/Meta/Dropi mutation
- no spend
- no launch
- no live API mutation
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCENARIO_ID = "A8-R53-VISIBLE-SINGLE-SCENARIO-001"
SIMULATION_VERSION = "a8_r53_visible_single_scenario_v1"


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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_short(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_scenario() -> SyntheticScenario:
    return SyntheticScenario(
        scenario_id=SCENARIO_ID,
        product_name="Synthetic Posture Desk Lamp",
        category="home-office-gadget",
        market="MX",
        supplier_mode="sandbox_manual_research_only",
        proposed_price_mxn=699,
        estimated_landed_cost_mxn=331,
        creative_claim="Ayuda a iluminar tu escritorio sin prometer resultados médicos ni financieros.",
        signals=(
            SyntheticSignal(
                name="margin_room",
                value=0.5265,
                weight=0.30,
                explanation="Synthetic gross room after estimated landed cost; not real supplier truth.",
            ),
            SyntheticSignal(
                name="claim_safety",
                value=0.9200,
                weight=0.25,
                explanation="Creative claim avoids health, finance, body-result, and guaranteed outcome claims.",
            ),
            SyntheticSignal(
                name="operational_complexity",
                value=0.7400,
                weight=0.20,
                explanation="Simple SKU shape for local simulation; no fulfillment automation is invoked.",
            ),
            SyntheticSignal(
                name="evidence_quality",
                value=0.6100,
                weight=0.15,
                explanation="Scenario is synthetic and useful for system validation, not market proof.",
            ),
            SyntheticSignal(
                name="mutation_risk_inverse",
                value=1.0000,
                weight=0.10,
                explanation="All live mutation paths remain blocked in this simulation.",
            ),
        ),
    )


def evaluate_score(signals: Iterable[SyntheticSignal]) -> float:
    weighted_sum = 0.0
    total_weight = 0.0

    for signal in signals:
        weighted_sum += signal.value * signal.weight
        total_weight += signal.weight

    if total_weight <= 0:
        raise ValueError("Signal total weight must be positive.")

    return round(weighted_sum / total_weight, 4)


def build_safety_posture() -> SafetyPosture:
    return SafetyPosture(
        claim_safety="PASS_SYNTHETIC_LOW_RISK",
        money_path="BLOCKED_LOCAL_ONLY",
        external_mutation=0,
        shopify_write_count=0,
        meta_write_count=0,
        dropi_write_count=0,
        spend_count=0,
        live_mode=0,
    )


def make_decision(scenario: SyntheticScenario, score: float, safety: SafetyPosture) -> Decision:
    payload = _stable_json(
        {
            "scenario_id": scenario.scenario_id,
            "score": score,
            "safety": asdict(safety),
            "simulation_version": SIMULATION_VERSION,
        }
    )
    decision_id = f"dec_{_sha256_short(payload)}"
    threshold = 0.72

    if safety.external_mutation != 0 or safety.spend_count != 0 or safety.live_mode != 0:
        return Decision(
            decision_id=decision_id,
            score=score,
            threshold=threshold,
            permission_gate="PRE_SPEND_GATE_BLOCKED",
            final_outcome="BLOCKED_UNSAFE_LIVE_PATH",
            reason="Simulation detected live, spend, or mutation risk.",
        )

    if score >= threshold:
        return Decision(
            decision_id=decision_id,
            score=score,
            threshold=threshold,
            permission_gate="LOCAL_ONLY_READINESS_GATE_PASS",
            final_outcome="APPROVE_FOR_LOCAL_REVIEW_ONLY",
            reason="Synthetic scenario clears local-only review threshold; still not approved for launch.",
        )

    return Decision(
        decision_id=decision_id,
        score=score,
        threshold=threshold,
        permission_gate="LOCAL_ONLY_READINESS_GATE_HOLD",
        final_outcome="HOLD_FOR_MORE_EVIDENCE",
        reason="Synthetic scenario does not clear local-only review threshold.",
    )


def create_evidence_dir(base_dir: str | None = None) -> Path:
    root = Path(base_dir) if base_dir else Path(tempfile.gettempdir())
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    evidence_dir = root / f"synapse_a8_r53_visible_simulation_{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=False)
    return evidence_dir


def write_evidence(
    evidence_dir: Path,
    scenario: SyntheticScenario,
    safety: SafetyPosture,
    decision: Decision,
) -> dict[str, str]:
    scenario_path = evidence_dir / "scenario.json"
    safety_path = evidence_dir / "safety_posture.json"
    decision_path = evidence_dir / "decision.json"
    ledger_path = evidence_dir / "ledger_sandbox.ndjson"
    idempotency_path = evidence_dir / "idempotency_sandbox.json"

    scenario_payload = asdict(scenario)
    safety_payload = asdict(safety)
    decision_payload = asdict(decision)

    scenario_path.write_text(
        json.dumps(scenario_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    safety_path.write_text(
        json.dumps(safety_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    decision_path.write_text(
        json.dumps(decision_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ledger_event = {
        "event_type": "VISIBLE_SINGLE_SCENARIO_SIMULATION",
        "simulation_version": SIMULATION_VERSION,
        "created_at": _utc_now_iso(),
        "scenario_id": scenario.scenario_id,
        "decision_id": decision.decision_id,
        "permission_gate": decision.permission_gate,
        "final_outcome": decision.final_outcome,
        "external_mutation": safety.external_mutation,
        "spend_count": safety.spend_count,
        "shopify_write_count": safety.shopify_write_count,
        "meta_write_count": safety.meta_write_count,
        "dropi_write_count": safety.dropi_write_count,
        "live_mode": safety.live_mode,
    }
    ledger_path.write_text(json.dumps(ledger_event, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    idempotency_payload = {
        "scenario_id": scenario.scenario_id,
        "decision_id": decision.decision_id,
        "fingerprint": _sha256_short(_stable_json(ledger_event)),
        "sandbox_only": True,
    }
    idempotency_path.write_text(
        json.dumps(idempotency_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "scenario_path": str(scenario_path),
        "safety_path": str(safety_path),
        "decision_path": str(decision_path),
        "ledger_path": str(ledger_path),
        "idempotency_path": str(idempotency_path),
    }


def render_human_output(
    evidence_dir: Path,
    scenario: SyntheticScenario,
    safety: SafetyPosture,
    decision: Decision,
    evidence_paths: dict[str, str],
) -> str:
    signal_lines = []
    for idx, signal in enumerate(scenario.signals, start=1):
        signal_lines.append(
            f"  SIGNAL_{idx:02d}={signal.name} value={signal.value:.4f} "
            f"weight={signal.weight:.2f} note={signal.explanation}"
        )

    lines = [
        "SYNAPSE SIMULATION",
        f"SIMULATION_VERSION={SIMULATION_VERSION}",
        f"SCENARIO_ID={scenario.scenario_id}",
        f"DECISION_ID={decision.decision_id}",
        "LIVE_MODE=0",
        "",
        "STEP_01_INPUT",
        f"  product_name={scenario.product_name}",
        f"  category={scenario.category}",
        f"  market={scenario.market}",
        f"  supplier_mode={scenario.supplier_mode}",
        f"  proposed_price_mxn={scenario.proposed_price_mxn}",
        f"  estimated_landed_cost_mxn={scenario.estimated_landed_cost_mxn}",
        f"  creative_claim={scenario.creative_claim}",
        "",
        "STEP_02_SIGNALS",
        *signal_lines,
        "",
        "STEP_03_SCORE_OR_POLICY",
        f"  score={decision.score:.4f}",
        f"  threshold={decision.threshold:.4f}",
        "  policy=evidence_first_local_only_no_live_mutation",
        "",
        "STEP_04_PERMISSION_GATE",
        f"  permission_gate={decision.permission_gate}",
        "  pre_spend_gate=BLOCKED_FOR_LIVE_SPEND",
        "  launch_gate=BLOCKED_FOR_LIVE_LAUNCH",
        "",
        "STEP_05_DECISION",
        f"  final_outcome={decision.final_outcome}",
        f"  reason={decision.reason}",
        "",
        "STEP_06_LEDGER_EVENT",
        f"  ledger_sandbox={evidence_paths['ledger_path']}",
        "  ledger_sandbox_line_count=1",
        "",
        "STEP_07_EVIDENCE",
        f"  evidence_dir={evidence_dir}",
        f"  scenario_json={evidence_paths['scenario_path']}",
        f"  safety_posture_json={evidence_paths['safety_path']}",
        f"  decision_json={evidence_paths['decision_path']}",
        f"  idempotency_sandbox={evidence_paths['idempotency_path']}",
        "",
        "STEP_08_LIVE_FLAGS",
        f"  flag_shopify_live={safety.live_mode}",
        f"  flag_meta_live_api={safety.live_mode}",
        f"  flag_dropi_live_orders={safety.live_mode}",
        "",
        "STEP_09_MUTATION_COUNTS",
        f"  EXTERNAL_MUTATION={safety.external_mutation}",
        f"  SPEND_COUNT={safety.spend_count}",
        f"  SHOPIFY_WRITE_COUNT={safety.shopify_write_count}",
        f"  META_WRITE_COUNT={safety.meta_write_count}",
        f"  DROPI_WRITE_COUNT={safety.dropi_write_count}",
        "",
        f"FINAL_OUTCOME={decision.final_outcome}",
        f"EVIDENCE_DIR={evidence_dir}",
    ]
    return "\n".join(lines) + "\n"


def run_simulation(evidence_root: str | None = None) -> str:
    scenario = build_scenario()
    safety = build_safety_posture()
    score = evaluate_score(scenario.signals)
    decision = make_decision(scenario=scenario, score=score, safety=safety)
    evidence_dir = create_evidence_dir(evidence_root)
    evidence_paths = write_evidence(
        evidence_dir=evidence_dir,
        scenario=scenario,
        safety=safety,
        decision=decision,
    )
    return render_human_output(
        evidence_dir=evidence_dir,
        scenario=scenario,
        safety=safety,
        decision=decision,
        evidence_paths=evidence_paths,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m synapse.cli simulate",
        description="Run the A8-R53 visible single-scenario local-only SYNAPSE simulation.",
    )
    parser.add_argument(
        "--evidence-root",
        default=None,
        help="Optional directory where sandbox evidence will be created. Defaults to system temp.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = run_simulation(evidence_root=args.evidence_root)
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())