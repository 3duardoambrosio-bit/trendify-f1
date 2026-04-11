# V3GAP:D-04_spend_pacing_alert

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional
import logging

from infra.idempotency import (
    DEFAULT_DB_PATH as DEFAULT_IDEMPOTENCY_DB_PATH,
    STATUS_COMPLETED,
    STATUS_CONFLICT,
    STATUS_DUPLICATE,
    STATUS_IN_FLIGHT,
    execute_once,
)
from ops.safety_middleware import (
    build_layer0_descriptor,
    check_safety_before_spend,
)
from synapse.infra.time_utc import build_clock_stamp
from synapse.ledger_ndjson import append_event
from synapse.safety.killswitch import KillSwitch
from synapse.safety.circuit import CircuitBreaker

logger = logging.getLogger(__name__)

_LAYER0_THRESHOLD_KEYS = (
    "spend_envelope_daily_per_campaign",
    "heartbeat_degraded_after",
    "heartbeat_minimal_risk_after",
    "kill_switch_scope_default",
    "kill_switch_global_authority",
)


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "amount": str(self.amount),
            "pool": self.pool,
            "product_id": self.product_id,
            "day": self.day,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "SpendGatewayDecision":
        return cls(
            allowed=bool(value.get("allowed", False)),
            reason=str(value.get("reason", "DENIED")),
            amount=Decimal(str(value.get("amount", "0"))),
            pool=str(value.get("pool", "operational")),
            product_id=str(value.get("product_id", "")),
            day=int(value.get("day", 1)),
            meta=dict(value.get("meta", {})),
        )


class SpendGateway:
    """
    Contract:
    - RESERVE: siempre bloqueado, reason == "RESERVE_PROTECTED"
    - LEARNING caps:
        day1  -> "CAP_LEARNING_DAY1"
        total -> "CAP_LEARNING_TOTAL"
    - Ledger: un solo write path NDJSON vía synapse.ledger_ndjson.append_event
    - Idempotency: SQLite-backed execute_once() es la autoridad
    - ODD: enforced para el money-path con defaults explícitos
    """

    def __init__(
        self,
        *,
        vault: Any,
        ledger: Optional[Any] = None,
        caps: Optional[ProductCaps] = None,
        killswitch: Optional[KillSwitch] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        idempotency_manager: Optional[Any] = None,  # compat: no usado; SQLite es autoridad
        idempotency_db_path: Optional[str | Path] = None,
    ):
        self.vault = vault
        self.ledger = ledger
        self.caps = caps or ProductCaps()
        self._killswitch = killswitch
        self._circuit_breaker = circuit_breaker
        self._idempotency_legacy = idempotency_manager
        self._idempotency_db_path = Path(idempotency_db_path) if idempotency_db_path is not None else DEFAULT_IDEMPOTENCY_DB_PATH
        self._learn_total_by_product: Dict[str, Decimal] = {}
        self._learn_day1_by_product: Dict[str, Decimal] = {}

    @staticmethod
    def layer0_mapping() -> Dict[str, Any]:
        return build_layer0_descriptor(
            component="spend_gateway_v1",
            channel="meta",
            scope="per_channel",
            threshold_keys=_LAYER0_THRESHOLD_KEYS,
        )

    def _layer0_meta(self, *, operation_id: str, pool: str, product_id: str, channel: str) -> Dict[str, Any]:
        base = build_layer0_descriptor(
            component="spend_gateway_v1",
            channel=channel or "meta",
            operation_id=operation_id,
            scope="per_channel",
            threshold_keys=_LAYER0_THRESHOLD_KEYS,
        )
        base.update(
            {
                "product_id": str(product_id or ""),
                "budget_pool": str(pool or ""),
                "channel": str(channel or "meta"),
                "shield_strategy": "money_path_unified",
            }
        )
        return base

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

    def _log_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        path = self._ledger_path()
        if path is None:
            return

        stamp = build_clock_stamp()
        row = {
            "ts": stamp.ingest_time,
            "event_type": event_type,
            "kind": event_type,
            "payload": payload,
            "clock_source_id": stamp.clock_source_id,
            "clock_skew_estimate": stamp.clock_skew_estimate,
            "clock_unreliable": stamp.clock_unreliable,
            "policy_version": "v1",
            "payload_schema_version": "spend_gateway_v1",
        }
        append_event(row, path=path)

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

    @staticmethod
    def _normalize_minutes(value: Any, *, default: int) -> int:
        if value is None or value == "":
            return int(default)
        return int(value)

    def request(self, req: Any, *, idempotency_key: Optional[str] = None) -> SpendGatewayDecision:
        budget_obj = self._get(req, ("budget", "budget_type", "pool", "bucket", "type"), default="operational")
        pool = self._pool_from_budget(budget_obj)

        amount = self._get(req, ("amount", "spend"), default=Decimal("0"))
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))

        product_id = self._get(req, ("product_id", "product", "pid", "sku", "id"), default="")
        day = int(self._get(req, ("day",), default=1))
        req_id = self._get(req, ("request_id", "rid", "id", "ref"), default="")
        channel = str(self._get(req, ("channel", "platform", "network", "source"), default="meta") or "meta")
        country = str(self._get(req, ("country", "market", "geo", "country_code"), default="MX") or "MX")
        currency = str(self._get(req, ("currency",), default="MXN") or "MXN")
        data_freshness_minutes = self._normalize_minutes(self._get(req, ("data_freshness_minutes",), default=0), default=0)
        tracking_freshness_minutes = self._normalize_minutes(self._get(req, ("tracking_freshness_minutes",), default=0), default=0)
        heartbeat_age_minutes = self._normalize_minutes(self._get(req, ("heartbeat_age_minutes",), default=0), default=0)

        op_id = str(req_id) or str(idempotency_key or "")
        layer0_meta = self._layer0_meta(operation_id=op_id, pool=pool, product_id=str(product_id), channel=channel)

        idem_key = str(idempotency_key or f"spend_{pool}_{product_id}_{req_id}_{amount}_{day}")

        operation_payload = {
            "request_id": str(req_id),
            "product_id": str(product_id),
            "amount": str(amount),
            "day": day,
            "pool": pool,
            "channel": channel,
            "country": country,
            "currency": currency,
            "data_freshness_minutes": data_freshness_minutes,
            "tracking_freshness_minutes": tracking_freshness_minutes,
            "heartbeat_age_minutes": heartbeat_age_minutes,
        }

        def _perform(payload: Dict[str, Any]) -> Dict[str, Any]:
            safety_result = check_safety_before_spend(
                operation_id=op_id,
                amount=amount,
                killswitch=self._killswitch,
                circuit_breaker=self._circuit_breaker,
                enforce_odd=True,
                channel=channel,
                country=country,
                currency=currency,
                data_freshness_minutes=data_freshness_minutes,
                tracking_freshness_minutes=tracking_freshness_minutes,
                heartbeat_age_minutes=heartbeat_age_minutes,
            )
            if safety_result.is_err():
                reason = safety_result.error
                event_payload = {
                    "reason": reason,
                    "request_id": str(req_id),
                    "product_id": str(product_id),
                    "amount": str(amount),
                    "day": day,
                    "channel": channel,
                    "country": country,
                    "currency": currency,
                    "layer0": layer0_meta,
                }
                self._log_event("SPEND_BLOCKED_SAFETY", event_payload)
                return SpendGatewayDecision(False, reason, amount, pool, str(product_id), day, {"layer0": layer0_meta}).to_dict()

            if pool == "reserve":
                event_payload = {
                    "reason": "RESERVE_PROTECTED",
                    "request_id": str(req_id),
                    "product_id": str(product_id),
                    "amount": str(amount),
                    "day": day,
                    "channel": channel,
                    "country": country,
                    "currency": currency,
                    "layer0": layer0_meta,
                }
                self._log_event("SPEND_DENIED", event_payload)
                return SpendGatewayDecision(False, "RESERVE_PROTECTED", amount, pool, str(product_id), day, {"layer0": layer0_meta}).to_dict()

            if pool == "learning":
                total_so_far = self._learn_total_by_product.get(product_id, Decimal("0"))
                day1_so_far = self._learn_day1_by_product.get(product_id, Decimal("0"))

                if self.caps.max_day1_learning is not None and day == 1 and day1_so_far + amount > self.caps.max_day1_learning:
                    event_payload = {
                        "reason": "CAP_LEARNING_DAY1",
                        "request_id": str(req_id),
                        "product_id": str(product_id),
                        "amount": str(amount),
                        "day": day,
                        "cap": str(self.caps.max_day1_learning),
                        "so_far": str(day1_so_far),
                        "channel": channel,
                        "country": country,
                        "currency": currency,
                        "layer0": layer0_meta,
                    }
                    self._log_event("SPEND_DENIED", event_payload)
                    return SpendGatewayDecision(False, "CAP_LEARNING_DAY1", amount, pool, str(product_id), day, {"cap": str(self.caps.max_day1_learning), "so_far": str(day1_so_far), "layer0": layer0_meta}).to_dict()

                if self.caps.max_total_learning is not None and total_so_far + amount > self.caps.max_total_learning:
                    event_payload = {
                        "reason": "CAP_LEARNING_TOTAL",
                        "request_id": str(req_id),
                        "product_id": str(product_id),
                        "amount": str(amount),
                        "day": day,
                        "cap": str(self.caps.max_total_learning),
                        "so_far": str(total_so_far),
                        "channel": channel,
                        "country": country,
                        "currency": currency,
                        "layer0": layer0_meta,
                    }
                    self._log_event("SPEND_DENIED", event_payload)
                    return SpendGatewayDecision(False, "CAP_LEARNING_TOTAL", amount, pool, str(product_id), day, {"cap": str(self.caps.max_total_learning), "so_far": str(total_so_far), "layer0": layer0_meta}).to_dict()

            dec = self.vault.request_spend(req)
            allowed = self._allowed_from(dec)
            reason = self._reason_from(dec, allowed)

            event_payload = {
                "reason": str(reason),
                "request_id": str(req_id),
                "product_id": str(product_id),
                "amount": str(amount),
                "day": day,
                "pool": pool,
                "channel": channel,
                "country": country,
                "currency": currency,
                "layer0": layer0_meta,
            }
            self._log_event("SPEND_APPROVED" if allowed else "SPEND_DENIED", event_payload)

            if allowed and pool == "learning":
                self._learn_total_by_product[product_id] = self._learn_total_by_product.get(product_id, Decimal("0")) + amount
                if day == 1:
                    self._learn_day1_by_product[product_id] = self._learn_day1_by_product.get(product_id, Decimal("0")) + amount

            return SpendGatewayDecision(allowed, str(reason), amount, pool, str(product_id), day, {"layer0": layer0_meta}).to_dict()

        result = execute_once(idem_key, operation_payload, _perform, db_path=self._idempotency_db_path)
        status = result["status"]

        if status in {STATUS_COMPLETED, STATUS_DUPLICATE}:
            return SpendGatewayDecision.from_dict(result["response"])
        if status == STATUS_CONFLICT:
            return SpendGatewayDecision(False, "IDEMPOTENCY_CONFLICT", amount, pool, str(product_id), day, {"layer0": layer0_meta})
        if status == STATUS_IN_FLIGHT:
            return SpendGatewayDecision(False, "IDEMPOTENCY_IN_FLIGHT", amount, pool, str(product_id), day, {"layer0": layer0_meta})

        raise RuntimeError(f"unexpected idempotency status: {status}")

    def request_spend(self, *, amount: Decimal, bucket: str):
        class _Req:
            def __init__(self, amount, bucket):
                self.amount = amount
                self.budget = bucket
                self.budget_type = bucket
                self.product_id = ""
                self.day = 1
                self.channel = "meta"
                self.country = "MX"
                self.currency = "MXN"
                self.data_freshness_minutes = 0
                self.tracking_freshness_minutes = 0
                self.heartbeat_age_minutes = 0

        return self.request(_Req(amount, bucket), idempotency_key=None)
