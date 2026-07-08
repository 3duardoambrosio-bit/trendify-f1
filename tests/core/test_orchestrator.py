from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from config.feature_flags import FeatureFlags
from infra.vault import VaultSnapshot
from synapse.core.models import OrchestratorDecision
from synapse.core.orchestrator import build_ledger_summary, decide, read_ops_tick


def _vault(
    total="300",
    learning="150",
    operational="100",
    reserve="50",
    spent_learning="0",
    spent_operational="0",
):
    return VaultSnapshot(
        total_budget=Decimal(total),
        learning_budget=Decimal(learning),
        operational_budget=Decimal(operational),
        reserve_budget=Decimal(reserve),
        spent_learning=Decimal(spent_learning),
        spent_operational=Decimal(spent_operational),
    )


def _product(pid="P1", score=0.9, margin=55.0):
    return SimpleNamespace(
        product_id=pid,
        match_score=score,
        margin_percent=margin,
    )


def _campaign(pid="P1", vid="V1", cid="C1", roas="1.0", spend="0", days=0, status="active"):
    return SimpleNamespace(
        product_id=pid,
        variant_id=vid,
        campaign_id=cid,
        roas=Decimal(roas) if roas is not None else None,
        spend_today=Decimal(spend),
        days_active=days,
        status=status,
    )


def _variant(pid="P1", vid="V1", roas="1.0", status="active"):
    from synapse.core.models import CreativeVariant, utc_now
    return CreativeVariant(
        variant_id=vid,
        product_id=pid,
        created_at=utc_now(),
        angle="benefit",
        hook="hook",
        format="image_single",
        asset_path="assets/a.png",
        status=status,
        roas=Decimal(roas) if roas is not None else None,
    )


def _write_ops_tick(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestReadOpsTick:
    def test_read_ops_tick_dict_green(self, tmp_path):
        p = tmp_path / "ops.json"
        _write_ops_tick(p, {
            "status": "OK",
            "marker": "X",
            "ts_utc": "2026-01-01T00:00:00+00:00",
            "checks": {
                "reconcile_preflight": {"blocked": False, "status": "ok"},
                "readonly_invariant_ok": True,
            },
            "steps": [],
        })
        out = read_ops_tick(str(p))
        assert out["reconcile_status"] == "green"

    def test_read_ops_tick_dict_skipped_is_yellow(self, tmp_path):
        p = tmp_path / "ops.json"
        _write_ops_tick(p, {
            "status": "OK",
            "marker": "X",
            "checks": {
                "reconcile_preflight": {"blocked": False, "status": "skipped", "reason": "env_vars_not_set"},
                "readonly_invariant_ok": True,
            },
            "steps": [],
        })
        out = read_ops_tick(str(p))
        assert out["reconcile_status"] == "yellow"

    def test_read_ops_tick_dict_blocked_is_red(self, tmp_path):
        p = tmp_path / "ops.json"
        _write_ops_tick(p, {
            "status": "FAIL",
            "marker": "X",
            "checks": {
                "reconcile_preflight": {"blocked": True, "status": "blocked"},
                "readonly_invariant_ok": True,
            },
            "steps": [],
        })
        out = read_ops_tick(str(p))
        assert out["reconcile_status"] == "red"

    def test_read_ops_tick_bool_false_legacy(self, tmp_path):
        p = tmp_path / "ops.json"
        _write_ops_tick(p, {
            "status": "FAIL",
            "marker": "X",
            "checks": {
                "reconcile_preflight": False,
            },
            "steps": [],
        })
        out = read_ops_tick(str(p))
        assert out["reconcile_status"] == "red"

    def test_read_ops_tick_bool_true_legacy(self, tmp_path):
        p = tmp_path / "ops.json"
        _write_ops_tick(p, {
            "status": "OK",
            "marker": "X",
            "checks": {
                "reconcile_preflight": True,
            },
            "steps": [],
        })
        out = read_ops_tick(str(p))
        assert out["reconcile_status"] == "green"

    def test_read_ops_tick_missing_file_fail_closed(self, tmp_path):
        out = read_ops_tick(str(tmp_path / "missing.json"))
        assert out["status"] == "MISSING"
        assert out["reconcile_status"] == "red"


class TestBuildLedgerSummary:
    def test_build_ledger_summary_basic(self):
        rows = [
            SimpleNamespace(kind="sale", amount=Decimal("200"), meta={"reconciled": True}),
            SimpleNamespace(kind="ad_spend", amount=Decimal("50"), meta={"reconciled": True}),
        ]
        out = build_ledger_summary(rows)
        assert out.total_revenue == Decimal("200")
        assert out.total_spent == Decimal("50")
        assert out.net_pnl == Decimal("150")

    def test_build_ledger_summary_negative_amounts(self):
        rows = [
            {"kind": "misc", "amount": "-10", "meta": {"reconciled": False}},
            {"kind": "misc", "amount": "20", "meta": {"reconciled": True}},
        ]
        out = build_ledger_summary(rows)
        assert out.total_spent == Decimal("10")
        assert out.total_revenue == Decimal("20")
        assert out.unreconciled_count == 1

    def test_build_ledger_summary_empty(self):
        out = build_ledger_summary([])
        assert out.total_spent == Decimal("0")
        assert out.total_revenue == Decimal("0")
        assert out.net_pnl == Decimal("0")

    def test_build_ledger_summary_refund_is_spent(self):
        rows = [{"kind": "refund", "amount": "30", "meta": {}}]
        out = build_ledger_summary(rows)
        assert out.total_spent == Decimal("30")

    def test_build_ledger_summary_frozen(self):
        out = build_ledger_summary([])
        with pytest.raises(FrozenInstanceError):
            out.total_spent = Decimal("1")


class TestDecide:
    def test_emergency_stop_when_breaker_open(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(_vault(), [], [], [], breaker_status="open", ops_tick_path=str(ops), decisions_dir=str(tmp_path / "decisions"))
        assert decisions[0].action_type == "emergency_stop"

    def test_pause_all_on_reconcile_red(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": True, "status": "blocked"}}, "steps": []})
        decisions = decide(_vault(), [], [], [], ops_tick_path=str(ops), decisions_dir=str(tmp_path / "decisions"))
        assert decisions[0].action_type == "pause_all"

    def test_hold_on_budget_floor(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        vault = _vault(learning="20", spent_learning="0")
        decisions = decide(vault, [], [], [], ops_tick_path=str(ops), decisions_dir=str(tmp_path / "decisions"))
        assert decisions[0].action_type == "hold"
        assert "budget_exhausted" in decisions[0].reason_codes

    def test_kill_campaign_on_bad_roas(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(
            _vault(),
            [],
            [],
            [_campaign(roas="0.5", spend="60", days=3)],
            ops_tick_path=str(ops),
            decisions_dir=str(tmp_path / "decisions"),
        )
        assert any(d.action_type == "kill_campaign" for d in decisions)

    def test_scale_up_on_good_roas(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(
            _vault(),
            [],
            [],
            [_campaign(roas="2.5", spend="20", days=2)],
            feature_flags=FeatureFlags(spend_real_money=True),
            ops_tick_path=str(ops),
            decisions_dir=str(tmp_path / "decisions"),
        )
        scale = [d for d in decisions if d.action_type == "scale_up"][0]
        assert scale.budget_action is not None
        assert scale.budget_action.amount > 0

    def test_launch_test_for_best_product(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(
            _vault(),
            [_product("P1", 0.3), _product("P2", 0.9)],
            [],
            [],
            feature_flags=FeatureFlags(spend_real_money=True),
            ops_tick_path=str(ops),
            decisions_dir=str(tmp_path / "decisions"),
        )
        launch = [d for d in decisions if d.action_type == "launch_test"][0]
        assert launch.target_product == "P2"

    def test_rotate_creative_when_variant_outperforms(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(
            _vault(),
            [],
            [_variant("P1", "V1", "5.0"), _variant("P1", "V2", "1.0")],
            [],
            ops_tick_path=str(ops),
            decisions_dir=str(tmp_path / "decisions"),
        )
        assert any(d.action_type == "rotate_creative" for d in decisions)

    def test_spend_real_money_disabled_blocks_allocate(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(
            _vault(),
            [_product("P2", 0.9)],
            [],
            [],
            feature_flags=FeatureFlags(spend_real_money=False),
            ops_tick_path=str(ops),
            decisions_dir=str(tmp_path / "decisions"),
        )
        launch = [d for d in decisions if d.action_type == "launch_test"][0]
        assert "spend_real_money_disabled" in launch.blocking_conditions

    def test_spend_real_money_enabled_no_block(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(
            _vault(),
            [_product("P2", 0.9)],
            [],
            [],
            feature_flags=FeatureFlags(spend_real_money=True),
            ops_tick_path=str(ops),
            decisions_dir=str(tmp_path / "decisions"),
        )
        launch = [d for d in decisions if d.action_type == "launch_test"][0]
        assert "spend_real_money_disabled" not in launch.blocking_conditions

    def test_feature_flags_none_is_allowed(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(
            _vault(),
            [_product("P2", 0.9)],
            [],
            [],
            feature_flags=None,
            ops_tick_path=str(ops),
            decisions_dir=str(tmp_path / "decisions"),
        )
        assert len(decisions) >= 1

    def test_artifact_written(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(
            _vault(),
            [_product("P2", 0.9)],
            [],
            [],
            feature_flags=FeatureFlags(spend_real_money=True),
            ops_tick_path=str(ops),
            decisions_dir=str(tmp_path / "decisions"),
        )
        assert Path(decisions[0].artifact_path).exists()

    def test_output_type(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(
            _vault(),
            [],
            [],
            [],
            ops_tick_path=str(ops),
            decisions_dir=str(tmp_path / "decisions"),
        )
        assert isinstance(decisions[0], OrchestratorDecision)

    def test_output_is_frozen(self, tmp_path):
        ops = tmp_path / "ops.json"
        _write_ops_tick(ops, {"checks": {"reconcile_preflight": {"blocked": False, "status": "ok"}}, "steps": []})
        decisions = decide(
            _vault(),
            [],
            [],
            [],
            ops_tick_path=str(ops),
            decisions_dir=str(tmp_path / "decisions"),
        )
        with pytest.raises(FrozenInstanceError):
            decisions[0].action_type = "x"