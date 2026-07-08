"""
VaultFileBacked — S13: File-persisted vault for production use.

Wraps VaultV1 with JSON persistence (fsync on every write).
Provides dual interface:
  - request_spend(amount, budget_type) for CapitalShieldV2 compatibility
  - request_spend_full(pool, product_id, amount, day) for direct callers

FAIL-CLOSED: if state file is corrupted, vault blocks ALL spending.

__MARKER__ embedded in module constant below.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Optional

import deal

from vault.vault_v1 import BudgetPool, SpendResult, VaultV1

__MARKER__ = "SESSION_S13_vault_file_backed_2026-03-03"

log = logging.getLogger(__name__)


def _d(x: Any) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


@dataclass(frozen=True)
class VaultFileBackedConfig:
    """Configuration for file-backed vault."""
    state_file: str = ""  # Will default to env var or data/vault/vault_state.json
    learning_total: Decimal = Decimal("150")     # ~$150 MXN learning
    operational_total: Decimal = Decimal("275")   # ~$275 MXN operational
    reserve_total: Decimal = Decimal("75")        # ~$75 MXN reserve (INTOCABLE)
    max_learning_per_product_total: Decimal = Decimal("30")
    max_learning_per_product_day1: Decimal = Decimal("10")

    @property
    def resolved_state_file(self) -> str:
        if self.state_file:
            return self.state_file
        return os.getenv("SYNAPSE_VAULT_STATE_FILE", "data/vault/vault_state.json")


class VaultFileBacked:
    """
    Production vault with file persistence.

    State is saved to JSON after every spend. On load, if the file
    is corrupted or missing, the vault starts fresh OR blocks
    depending on configuration.

    Interface contract for CapitalShieldV2:
        request_spend(amount: Decimal, budget_type: str) -> SpendResult
        SpendResult.is_ok() -> bool

    FAIL-CLOSED on corruption: if state file cannot be parsed,
    all spending is blocked until manual intervention.
    """

    def __init__(
        self,
        config: Optional[VaultFileBackedConfig] = None,
        *,
        fail_closed_on_corrupt: bool = True,
    ) -> None:
        self._config = config or VaultFileBackedConfig()
        self._state_file = Path(self._config.resolved_state_file)
        self._fail_closed = fail_closed_on_corrupt
        self._corrupted = False
        self._vault: Optional[VaultV1] = None

        self._vault = self._load_or_create()

    @property
    def corrupted(self) -> bool:
        return self._corrupted

    @property
    def vault(self) -> VaultV1:
        if self._vault is None:
            raise RuntimeError("vault_not_initialized")
        return self._vault

    # ------------------------------------------------------------------
    # CapitalShieldV2-compatible interface
    # ------------------------------------------------------------------
    @deal.pre(lambda self, amount, budget_type: isinstance(amount, (Decimal, int, str)))
    @deal.pre(lambda self, amount, budget_type: isinstance(budget_type, str))
    @deal.post(lambda result: isinstance(result, SpendResult))
    def request_spend(self, amount: Decimal, budget_type: str) -> SpendResult:
        """
        Interface for CapitalShieldV2.

        Pool-level budget check ONLY. No per-product caps — those are
        the responsibility of the caller (CapitalShieldV2 tracks products).
        """
        amount = _d(amount)

        if self._corrupted:
            log.warning("VAULT_CORRUPTED: blocking spend amount=%s type=%s", amount, budget_type)
            return SpendResult(
                allowed=False,
                reason="VAULT_STATE_CORRUPTED",
                pool=budget_type,
                amount=amount,
                product_id="_shield",
            )

        if amount <= 0:
            return SpendResult(False, "AMOUNT_NON_POSITIVE", budget_type, amount, "_shield")

        if budget_type == "reserve":
            return SpendResult(False, "RESERVE_PROTECTED", budget_type, amount, "_shield")

        pools = self.vault.pools()
        if budget_type not in pools:
            return SpendResult(False, "UNKNOWN_POOL", budget_type, amount, "_shield")

        pool = pools[budget_type]
        if amount > pool.available:
            return SpendResult(False, "INSUFFICIENT_POOL_FUNDS", budget_type, amount, "_shield")

        # Debit pool directly (no per-product tracking)
        pool.spent += amount
        self._save()
        return SpendResult(True, "APPROVED", budget_type, amount, "_shield")

    # ------------------------------------------------------------------
    # Full interface for direct callers (ops_tick, etc.)
    # ------------------------------------------------------------------
    @deal.pre(lambda self, pool, product_id, amount, day=1: isinstance(pool, str))
    @deal.pre(lambda self, pool, product_id, amount, day=1: isinstance(product_id, str))
    @deal.post(lambda result: isinstance(result, SpendResult))
    def request_spend_full(
        self,
        pool: str,
        product_id: str,
        amount: Decimal,
        day: int = 1,
    ) -> SpendResult:
        """Full interface preserving VaultV1 semantics."""
        if self._corrupted:
            log.warning("VAULT_CORRUPTED: blocking spend pool=%s product=%s amount=%s", pool, product_id, amount)
            return SpendResult(
                allowed=False,
                reason="VAULT_STATE_CORRUPTED",
                pool=pool,
                amount=_d(amount),
                product_id=product_id,
            )

        result = self.vault.request_spend(
            pool=pool,
            product_id=product_id,
            amount=_d(amount),
            day=day,
        )
        self._save()
        return result

    # ------------------------------------------------------------------
    # Query methods (no mutation)
    # ------------------------------------------------------------------
    def available(self, pool: str) -> Decimal:
        """Available budget in a pool."""
        pools = self.vault.pools()
        if pool not in pools:
            return Decimal("0")
        return pools[pool].available

    def snapshot(self) -> Dict[str, Any]:
        """Current state as a dict (for cockpit/status)."""
        v = self.vault
        return {
            "corrupted": self._corrupted,
            "state_file": str(self._state_file),
            "pools": {
                name: {
                    "total": str(p.total),
                    "spent": str(p.spent),
                    "available": str(p.available),
                }
                for name, p in v.pools().items()
            },
            "learning_by_product": {
                k: str(v) for k, v in v._learning_spent_by_product.items()
            },
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load_or_create(self) -> VaultV1:
        """Load state from file, or create fresh vault."""
        if not self._state_file.exists():
            log.info("vault state file not found, creating fresh: %s", self._state_file)
            return self._create_fresh()

        try:
            raw = self._state_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            return self._from_dict(data)
        except (json.JSONDecodeError, KeyError, InvalidOperation, TypeError, ValueError) as e:
            log.critical(
                "VAULT_STATE_CORRUPTED at %s: %s — %s",
                self._state_file, type(e).__name__, e,
            )
            if self._fail_closed:
                self._corrupted = True
                # Return a vault that won't be used (all spends blocked by corrupted flag)
                return self._create_fresh()
            else:
                log.warning("fail_closed=False: creating fresh vault despite corruption")
                return self._create_fresh()

    def _create_fresh(self) -> VaultV1:
        """Create a new vault with config defaults."""
        cfg = self._config
        vault = VaultV1(
            learning=BudgetPool(name="learning", total=cfg.learning_total),
            operational=BudgetPool(name="operational", total=cfg.operational_total),
            reserve=BudgetPool(name="reserve", total=cfg.reserve_total),
            max_learning_per_product_total=cfg.max_learning_per_product_total,
            max_learning_per_product_day1=cfg.max_learning_per_product_day1,
        )
        self._save_vault(vault)
        return vault

    def _save(self) -> None:
        """Persist current vault state."""
        if self._vault is not None:
            self._save_vault(self._vault)

    def _save_vault(self, vault: VaultV1) -> None:
        """Atomic write: write to temp file, fsync, rename."""
        data = self._to_dict(vault)
        content = json.dumps(data, indent=2, ensure_ascii=True)

        self._state_file.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write pattern: temp file + fsync + rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._state_file.parent),
            prefix=".vault_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(self._state_file))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _to_dict(vault: VaultV1) -> Dict[str, Any]:
        """Serialize vault state to dict."""
        return {
            "version": 1,
            "pools": {
                name: {"total": str(p.total), "spent": str(p.spent)}
                for name, p in vault.pools().items()
            },
            "learning_by_product": {
                k: str(v) for k, v in vault._learning_spent_by_product.items()
            },
            "caps": {
                "max_learning_per_product_total": str(vault.max_learning_per_product_total),
                "max_learning_per_product_day1": str(vault.max_learning_per_product_day1),
            },
        }

    @staticmethod
    def _from_dict(data: Dict[str, Any]) -> VaultV1:
        """Deserialize vault state from dict."""
        if data.get("version") != 1:
            raise ValueError(f"unsupported_vault_version:{data.get('version')}")

        pools_raw = data["pools"]

        def _pool(name: str) -> BudgetPool:
            p = pools_raw[name]
            return BudgetPool(name=name, total=Decimal(p["total"]), spent=Decimal(p["spent"]))

        caps = data.get("caps", {})
        vault = VaultV1(
            learning=_pool("learning"),
            operational=_pool("operational"),
            reserve=_pool("reserve"),
            max_learning_per_product_total=Decimal(caps.get("max_learning_per_product_total", "30")),
            max_learning_per_product_day1=Decimal(caps.get("max_learning_per_product_day1", "10")),
        )

        # Restore per-product tracking
        for k, v in data.get("learning_by_product", {}).items():
            vault._learning_spent_by_product[k] = Decimal(v)

        return vault
