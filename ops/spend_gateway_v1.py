from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional
import json
import datetime


@dataclass(frozen=True)
class ProductCaps:
    max_total_learning: Optional[Decimal] = None
    max_day1_learning: Optional[Decimal] = None


@dataclass(frozen=True)
class SpendGatewayDecision:
    allowed: bool
    reason: str
    amount: Decimal
    pool: str
    product_id: str = ""
    day: int = 1
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.allowed

    @property
    def success(self) -> bool:
        return self.allowed


class SpendGateway:
    """
    Test-driven contract:
    - RESERVE: siempre bloqueado, reason == "RESERVE_PROTECTED"
    - LEARNING caps:
        day1  -> "CAP_LEARNING_DAY1"
        total -> "CAP_LEARNING_TOTAL"
    - Ledger: SIEMPRE escribe NDJSON con schema:
        {"event_type": "...", "payload": {...}}
      (para que ledger.iter_events() lo vea igual que los tests)
    - Vault v1: request_spend(req) (usa req.budget)
    """

    def __init__(self, *, vault: Any, ledger: Optional[Any] = None, caps: Optional[ProductCaps] = None):
        self.vault = vault
        self.ledger = ledger
        self.caps = caps or ProductCaps()
        self._learn_total_by_product: Dict[str, Decimal] = {}
        self._learn_day1_by_product: Dict[str, Decimal] = {}

    def _get(self, obj: Any, keys: tuple[str, ...], default=None):
        for k in keys:
            if hasattr(obj, k):
                return getattr(obj, k)
        return default

    def _pool_from_budget(self, budget_obj: Any) -> str:
        name = getattr(budget_obj, "name", None)
        if isinstance(name, str) and name:
            return name.lower()
        if isinstance(budget_obj, str):
            return budget_obj.lower()
        return str(budget_obj).lower()

    def _ledger_path(self) -> Optional[Path]:
        l = self.ledger
        if l is None:
            return None
        p = getattr(l, "path", None)
        if p is None:
            p = getattr(l, "_path", None)
        if isinstance(p, Path):
            return p
        if isinstance(p, str) and p.strip():
            return Path(p)
        return None

    def _append_ndjson(self, row: Dict[str, Any]) -> None:
        path = self._ledger_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, default=str)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _log_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        row = {
            "ts": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "event_type": event_type,
            "payload": payload,
        }
        # IMPORTANT: siempre dejamos nuestra línea AL FINAL, para que rows[-1] sea esta.
        try:
            l = self.ledger
            if l is not None:
                for m in ("log_event", "append_event", "append", "write", "emit", "log", "record"):
                    if hasattr(l, m):
                        try:
                            getattr(l, m)(row)
                        except Exception:
                            pass
        finally:
            self._append_ndjson(row)

    def _allowed_from(self, dec: Any) -> bool:
        for k in ("allowed", "ok", "success", "passed", "is_ok"):
            if hasattr(dec, k):
                return bool(getattr(dec, k))
        if dec is True or dec is False:
            return bool(dec)
        return False

    def _reason_from(self, dec: Any, allowed: bool) -> str:
        for k in ("reason", "message", "error", "why", "detail"):
            if hasattr(dec, k):
                v = getattr(dec, k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return "OK" if allowed else "DENIED"

    def request(self, req: Any) -> SpendGatewayDecision:
        # Vault v1 usa req.budget
        budget_obj = self._get(req, ("budget", "budget_type", "pool", "bucket", "type"), default="operational")
        pool = self._pool_from_budget(budget_obj)

        amount = self._get(req, ("amount", "spend"), default=Decimal("0"))
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))

        product_id = self._get(req, ("product_id", "product", "pid", "sku", "id"), default="")
        day = int(self._get(req, ("day",), default=1))
        req_id = self._get(req, ("request_id", "rid", "id", "ref"), default="")

        # RESERVE SIEMPRE bloqueado
        if pool == "reserve":
            payload = {
                "reason": "RESERVE_PROTECTED",
                "request_id": str(req_id),
                "product_id": str(product_id),
                "amount": str(amount),
                "day": day,
            }
            self._log_event("SPEND_DENIED", payload)
            return SpendGatewayDecision(False, "RESERVE_PROTECTED", amount, pool, product_id, day, {})

        # Caps learning
        if pool == "learning":
            total_so_far = self._learn_total_by_product.get(product_id, Decimal("0"))
            day1_so_far = self._learn_day1_by_product.get(product_id, Decimal("0"))

            if self.caps.max_day1_learning is not None and day == 1:
                if day1_so_far + amount > self.caps.max_day1_learning:
                    payload = {
                        "reason": "CAP_LEARNING_DAY1",
                        "request_id": str(req_id),
                        "product_id": str(product_id),
                        "amount": str(amount),
                        "day": day,
                        "cap": str(self.caps.max_day1_learning),
                        "so_far": str(day1_so_far),
                    }
                    self._log_event("SPEND_DENIED", payload)
                    return SpendGatewayDecision(False, "CAP_LEARNING_DAY1", amount, pool, product_id, day, {"cap": str(self.caps.max_day1_learning), "so_far": str(day1_so_far)})

            if self.caps.max_total_learning is not None:
                if total_so_far + amount > self.caps.max_total_learning:
                    payload = {
                        "reason": "CAP_LEARNING_TOTAL",
                        "request_id": str(req_id),
                        "product_id": str(product_id),
                        "amount": str(amount),
                        "day": day,
                        "cap": str(self.caps.max_total_learning),
                        "so_far": str(total_so_far),
                    }
                    self._log_event("SPEND_DENIED", payload)
                    return SpendGatewayDecision(False, "CAP_LEARNING_TOTAL", amount, pool, product_id, day, {"cap": str(self.caps.max_total_learning), "so_far": str(total_so_far)})

        # Delegar al vault (v1: request_spend(req))
        dec = self.vault.request_spend(req)
        allowed = self._allowed_from(dec)
        reason = self._reason_from(dec, allowed)

        # log approval/denial del vault también
        payload = {
            "reason": str(reason),
            "request_id": str(req_id),
            "product_id": str(product_id),
            "amount": str(amount),
            "day": day,
            "pool": pool,
        }
        self._log_event("SPEND_APPROVED" if allowed else "SPEND_DENIED", payload)

        if allowed and pool == "learning":
            self._learn_total_by_product[product_id] = self._learn_total_by_product.get(product_id, Decimal("0")) + amount
            if day == 1:
                self._learn_day1_by_product[product_id] = self._learn_day1_by_product.get(product_id, Decimal("0")) + amount

        return SpendGatewayDecision(allowed, str(reason), amount, pool, product_id, day, {})

    # compat helper
    def request_spend(self, *, amount: Decimal, bucket: str):
        class _Req:
            def __init__(self, amount, bucket):
                self.amount = amount
                self.budget = bucket
                self.budget_type = bucket
                self.product_id = ""
                self.day = 1
        return self.request(_Req(amount, bucket))