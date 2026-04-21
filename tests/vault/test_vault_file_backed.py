"""
S13 Tests: VaultFileBacked — persistence, budget enforcement, fail-closed, shield integration.

Acceptance criteria:
  1. Fresh vault creates with correct pool totals
  2. Spend depletes pool AND persists to disk
  3. Reload from disk preserves spent state (no double-spend)
  4. Budget exhaustion blocks further spending
  5. Corrupted state file → FAIL-CLOSED (all spends blocked)
  6. CapitalShieldV2 + real vault = budget enforcement
  7. SpendResult.is_ok() works for CapitalShieldV2
  8. Reserve pool is ALWAYS protected
  9. Atomic write survives (temp + rename pattern)
  10. safe_client._check_capital_shield uses real vault (no StubVault)
"""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from vault.vault_v1 import SpendResult, VaultV1, BudgetPool
from vault.vault_file_backed import VaultFileBacked, VaultFileBackedConfig


# ── Helpers ──────────────────────────────────────────────────

def _tmp_config(tmp_path: Path, **overrides) -> VaultFileBackedConfig:
    defaults = {
        "state_file": str(tmp_path / "vault_state.json"),
        "learning_total": Decimal("100"),
        "operational_total": Decimal("200"),
        "reserve_total": Decimal("50"),
        "max_learning_per_product_total": Decimal("30"),
        "max_learning_per_product_day1": Decimal("10"),
    }
    defaults.update(overrides)
    return VaultFileBackedConfig(**defaults)


# ── 1. Fresh vault creates with correct pools ────────────────

class TestFreshVault:
    def test_fresh_creates_file(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        assert Path(cfg.state_file).exists()

    def test_fresh_pool_totals(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        snap = v.snapshot()
        assert snap["pools"]["learning"]["total"] == "100"
        assert snap["pools"]["operational"]["total"] == "200"
        assert snap["pools"]["reserve"]["total"] == "50"

    def test_fresh_all_available(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        assert v.available("learning") == Decimal("100")
        assert v.available("operational") == Decimal("200")
        assert v.available("reserve") == Decimal("50")

    def test_fresh_not_corrupted(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        assert v.corrupted is False


# ── 2. Spend depletes pool AND persists ──────────────────────

class TestSpendAndPersist:
    def test_spend_reduces_available(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        result = v.request_spend(Decimal("25"), "learning")
        assert result.is_ok() is True
        assert v.available("learning") == Decimal("75")

    def test_spend_persists_to_disk(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        v.request_spend(Decimal("25"), "learning")

        # Read raw file
        raw = json.loads(Path(cfg.state_file).read_text())
        assert raw["pools"]["learning"]["spent"] == "25"

    def test_full_interface_spend(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        result = v.request_spend_full(
            pool="learning",
            product_id="PROD-001",
            amount=Decimal("10"),
            day=1,
        )
        assert result.is_ok() is True
        assert result.product_id == "PROD-001"

    def test_operational_spend(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        result = v.request_spend(Decimal("50"), "operational")
        assert result.is_ok() is True
        assert v.available("operational") == Decimal("150")


# ── 3. Reload preserves state (no double-spend) ─────────────

class TestReloadPersistence:
    def test_reload_preserves_spent(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v1 = VaultFileBacked(cfg)
        v1.request_spend(Decimal("40"), "learning")
        del v1

        v2 = VaultFileBacked(cfg)
        assert v2.available("learning") == Decimal("60")

    def test_reload_preserves_product_tracking(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v1 = VaultFileBacked(cfg)
        v1.request_spend_full("learning", "PROD-X", Decimal("10"), day=1)
        del v1

        # Reload: same product should still have tracking
        v2 = VaultFileBacked(cfg)
        snap = v2.snapshot()
        assert snap["learning_by_product"]["PROD-X"] == "10"

    def test_multiple_spends_then_reload(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v1 = VaultFileBacked(cfg)
        v1.request_spend(Decimal("10"), "learning")
        v1.request_spend(Decimal("20"), "learning")
        v1.request_spend(Decimal("30"), "operational")
        del v1

        v2 = VaultFileBacked(cfg)
        assert v2.available("learning") == Decimal("70")
        assert v2.available("operational") == Decimal("170")

    def test_100_reloads_same_state(self, tmp_path):
        """Paranoia test: 100 load/save cycles don't drift."""
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        v.request_spend(Decimal("33.33"), "learning")

        for _ in range(100):
            v = VaultFileBacked(cfg)

        assert v.available("learning") == Decimal("100") - Decimal("33.33")


# ── 4. Budget exhaustion blocks spending ─────────────────────

class TestBudgetExhaustion:
    def test_insufficient_funds_blocked(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        result = v.request_spend(Decimal("999"), "learning")
        assert result.is_ok() is False
        assert result.reason in ("INSUFFICIENT_POOL_FUNDS", "DAY1_CAP_REACHED", "PRODUCT_TOTAL_CAP_REACHED")

    def test_exact_exhaustion_then_blocked(self, tmp_path):
        cfg = _tmp_config(tmp_path, learning_total=Decimal("50"))
        v = VaultFileBacked(cfg)

        r1 = v.request_spend(Decimal("50"), "learning")
        assert r1.is_ok() is True

        r2 = v.request_spend(Decimal("1"), "learning")
        assert r2.is_ok() is False

    def test_day1_cap_enforced(self, tmp_path):
        cfg = _tmp_config(tmp_path, max_learning_per_product_day1=Decimal("10"))
        v = VaultFileBacked(cfg)
        result = v.request_spend_full("learning", "PROD-A", Decimal("15"), day=1)
        assert result.is_ok() is False
        assert "DAY1_CAP" in result.reason

    def test_product_total_cap_enforced(self, tmp_path):
        cfg = _tmp_config(tmp_path, max_learning_per_product_total=Decimal("30"))
        v = VaultFileBacked(cfg)
        v.request_spend_full("learning", "PROD-B", Decimal("10"), day=2)
        v.request_spend_full("learning", "PROD-B", Decimal("10"), day=2)
        v.request_spend_full("learning", "PROD-B", Decimal("10"), day=2)

        # This pushes past 30
        result = v.request_spend_full("learning", "PROD-B", Decimal("1"), day=2)
        assert result.is_ok() is False
        assert "PRODUCT_TOTAL_CAP" in result.reason


# ── 5. Corrupted file → FAIL-CLOSED ─────────────────────────

class TestFailClosed:
    def test_corrupted_json_blocks_all(self, tmp_path):
        state_file = tmp_path / "vault_state.json"
        state_file.write_text("THIS IS NOT JSON {{{{")

        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg, fail_closed_on_corrupt=True)
        assert v.corrupted is True

        result = v.request_spend(Decimal("1"), "learning")
        assert result.is_ok() is False
        assert "CORRUPTED" in result.reason

    def test_corrupted_blocks_full_interface_too(self, tmp_path):
        state_file = tmp_path / "vault_state.json"
        state_file.write_text("{}")  # Valid JSON but missing keys

        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg, fail_closed_on_corrupt=True)
        assert v.corrupted is True

        result = v.request_spend_full("learning", "P1", Decimal("1"))
        assert result.is_ok() is False

    def test_fail_open_mode_recovers(self, tmp_path):
        state_file = tmp_path / "vault_state.json"
        state_file.write_text("GARBAGE")

        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg, fail_closed_on_corrupt=False)
        assert v.corrupted is False  # fail-open recovers

        result = v.request_spend(Decimal("1"), "learning")
        assert result.is_ok() is True

    def test_wrong_version_fails_closed(self, tmp_path):
        state_file = tmp_path / "vault_state.json"
        state_file.write_text(json.dumps({"version": 99, "pools": {}}))

        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg, fail_closed_on_corrupt=True)
        assert v.corrupted is True


# ── 6. CapitalShieldV2 + real vault integration ─────────────

class TestCapitalShieldIntegration:
    def test_shield_approves_within_budget(self, tmp_path):
        from ops.capital_shield_v2 import CapitalShieldV2

        cfg = _tmp_config(tmp_path, learning_total=Decimal("100"))
        vault = VaultFileBacked(cfg)
        shield = CapitalShieldV2(vault=vault)

        decision = shield.decide_for_product(
            final_decision="approved",
            requested_amount=Decimal("50"),
        )
        assert decision.reason == "approved"
        assert decision.allocated == Decimal("50")

    def test_shield_blocks_over_budget(self, tmp_path):
        from ops.capital_shield_v2 import CapitalShieldV2

        cfg = _tmp_config(tmp_path, learning_total=Decimal("10"))
        vault = VaultFileBacked(cfg)
        shield = CapitalShieldV2(vault=vault)

        decision = shield.decide_for_product(
            final_decision="approved",
            requested_amount=Decimal("50"),
        )
        assert decision.reason == "insufficient_budget"
        assert decision.allocated == Decimal("0")

    def test_shield_blocks_not_approved_product(self, tmp_path):
        from ops.capital_shield_v2 import CapitalShieldV2

        cfg = _tmp_config(tmp_path)
        vault = VaultFileBacked(cfg)
        shield = CapitalShieldV2(vault=vault)

        decision = shield.decide_for_product(
            final_decision="rejected",
            requested_amount=Decimal("10"),
        )
        assert decision.reason == "not_approved"

    def test_shield_depletes_vault_and_persists(self, tmp_path):
        from ops.capital_shield_v2 import CapitalShieldV2

        cfg = _tmp_config(tmp_path, learning_total=Decimal("100"))
        vault = VaultFileBacked(cfg)
        shield = CapitalShieldV2(vault=vault)

        shield.decide_for_product("approved", Decimal("40"))
        shield.decide_for_product("approved", Decimal("40"))

        # Reload vault — should see 80 spent
        vault2 = VaultFileBacked(cfg)
        assert vault2.available("learning") == Decimal("20")

    def test_shield_with_corrupted_vault_blocks(self, tmp_path):
        from ops.capital_shield_v2 import CapitalShieldV2

        state_file = tmp_path / "vault_state.json"
        state_file.write_text("NOT JSON")

        cfg = _tmp_config(tmp_path)
        vault = VaultFileBacked(cfg, fail_closed_on_corrupt=True)
        shield = CapitalShieldV2(vault=vault)

        decision = shield.decide_for_product("approved", Decimal("1"))
        # Corrupted vault returns fail-closed signal → shield preserves vault_error
        assert decision.reason == "vault_error"
        assert decision.allocated == Decimal("0")


# ── 7. SpendResult.is_ok() ──────────────────────────────────

class TestSpendResultIsOk:
    def test_approved_is_ok_true(self):
        r = SpendResult(True, "APPROVED", "learning", Decimal("10"), "P1")
        assert r.is_ok() is True

    def test_rejected_is_ok_false(self):
        r = SpendResult(False, "INSUFFICIENT", "learning", Decimal("10"), "P1")
        assert r.is_ok() is False


# ── 8. Reserve pool ALWAYS protected ────────────────────────

class TestReserveProtection:
    def test_reserve_blocked_via_shield_interface(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        result = v.request_spend(Decimal("1"), "reserve")
        assert result.is_ok() is False
        assert "RESERVE" in result.reason

    def test_reserve_blocked_via_full_interface(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        result = v.request_spend_full("reserve", "P1", Decimal("1"))
        assert result.is_ok() is False


# ── 9. Atomic write ─────────────────────────────────────────

class TestAtomicWrite:
    def test_no_partial_writes(self, tmp_path):
        """State file is always valid JSON after any operation."""
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)

        for i in range(50):
            v.request_spend(Decimal("1"), "learning")
            raw = Path(cfg.state_file).read_text()
            data = json.loads(raw)  # Must not raise
            assert data["version"] == 1

    def test_snapshot_consistency(self, tmp_path):
        cfg = _tmp_config(tmp_path)
        v = VaultFileBacked(cfg)
        v.request_spend(Decimal("10"), "learning")
        v.request_spend(Decimal("20"), "operational")

        snap = v.snapshot()
        assert snap["corrupted"] is False
        assert snap["pools"]["learning"]["spent"] == "10"
        assert snap["pools"]["operational"]["spent"] == "20"


# ── 10. safe_client no longer has StubVault ──────────────────

class TestSafeClientNoStub:
    def test_no_stub_vault_in_source(self):
        """Verify StubVault is completely removed from safe_client.py."""
        import inspect
        import synapse.meta.safe_client as sc
        source = inspect.getsource(sc)
        assert "StubVault" not in source
        assert "module_unavailable_passthrough" not in source

    def test_no_passthrough_in_source(self):
        """Verify no passthrough behavior remains."""
        import inspect
        import synapse.meta.safe_client as sc
        source = inspect.getsource(sc)
        assert "passthrough" not in source.lower()
