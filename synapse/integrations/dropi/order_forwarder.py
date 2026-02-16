# synapse/integrations/dropi/order_forwarder.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Tuple, Callable
import json
import time
import urllib.request
import urllib.error


class CircuitOpenError(RuntimeError):
    pass


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: bytes,
        timeout_seconds: int,
    ) -> Tuple[int, bytes]:
        ...


@dataclass(frozen=True)
class DropiOrderForwarderConfig:
    base_url: str
    api_token: str
    timeout_seconds: int = 20
    max_attempts: int = 3
    backoff_seconds: float = 0.4
    circuit_fail_threshold: int = 5
    circuit_cooldown_seconds: int = 30
    idempotency_ttl_seconds: int = 24 * 3600
    user_agent: str = "synapse-dropi-forwarder/1.0"


@dataclass(frozen=True)
class ForwardResult:
    ok: bool
    status_code: int
    response_text: str
    replayed: bool
    idempotency_key: str


class InMemoryIdempotencyStore:
    """
    Store minimalista (ttl) para tests y runtime local.
    Interface intencionalmente simple para no acoplarse a infra interna.
    """
    def __init__(self) -> None:
        self._items: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        v = self._items.get(key)
        if not v:
            return None
        exp, payload = v
        if now >= exp:
            self._items.pop(key, None)
            return None
        return payload

    def put(self, key: str, value: Dict[str, Any], ttl_seconds: int) -> None:
        exp = time.time() + max(1, int(ttl_seconds))
        self._items[key] = (exp, value)


def _json_dumps(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def build_dropi_payload_from_shopify(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Payload agnóstico (porque Dropi API real puede variar).
    Lo importante en F1: external_id + items + shipping + totals.
    """
    customer = order.get("customer") or {}
    ship = order.get("shipping_address") or {}
    items_in = order.get("line_items") or []

    items = []
    for it in items_in:
        items.append(
            {
                "sku": (it.get("sku") or it.get("variant_id") or it.get("id") or ""),
                "name": it.get("title") or "",
                "quantity": int(it.get("quantity") or 0),
                "price": float(it.get("price") or 0.0),
            }
        )

    return {
        "external_id": str(order.get("id") or order.get("order_id") or ""),
        "currency": order.get("currency") or "MXN",
        "email": customer.get("email") or order.get("email") or "",
        "customer_name": (customer.get("first_name") or "") + " " + (customer.get("last_name") or ""),
        "shipping": {
            "name": ship.get("name") or "",
            "address1": ship.get("address1") or "",
            "address2": ship.get("address2") or "",
            "city": ship.get("city") or "",
            "province": ship.get("province") or "",
            "zip": ship.get("zip") or "",
            "country": ship.get("country") or "",
            "phone": ship.get("phone") or "",
        },
        "items": items,
        "note": order.get("note") or "",
        "total_price": float(order.get("total_price") or 0.0),
    }


class UrllibTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: bytes,
        timeout_seconds: int,
    ) -> Tuple[int, bytes]:
        req = urllib.request.Request(url=url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                return int(resp.status), resp.read()
        except urllib.error.HTTPError as e:
            return int(e.code), e.read() if hasattr(e, "read") else str(e).encode("utf-8")


class DropiOrderForwarder:
    def __init__(
        self,
        cfg: DropiOrderForwarderConfig,
        *,
        transport: Optional[HttpTransport] = None,
        store: Optional[Any] = None,
        payload_builder: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self._cfg = cfg
        self._transport = transport or UrllibTransport()
        self._store = store or InMemoryIdempotencyStore()
        self._payload_builder = payload_builder or build_dropi_payload_from_shopify

        self._fail_count = 0
        self._circuit_open_until = 0.0

    def _store_get(self, key: str) -> Optional[Dict[str, Any]]:
        for name in ("get", "read", "load", "fetch"):
            if hasattr(self._store, name):
                return getattr(self._store, name)(key)
        return None

    def _store_put(self, key: str, value: Dict[str, Any]) -> None:
        for name in ("put", "set", "write", "save"):
            if hasattr(self._store, name):
                fn = getattr(self._store, name)
                try:
                    fn(key, value, self._cfg.idempotency_ttl_seconds)
                except TypeError:
                    fn(key, value)
                return

    def forward_shopify_order(self, order: Dict[str, Any], *, idempotency_key: str) -> ForwardResult:
        now = time.time()
        if now < self._circuit_open_until:
            raise CircuitOpenError(f"circuit_open_until={self._circuit_open_until:.0f}")

        cached = self._store_get(idempotency_key)
        if cached is not None:
            return ForwardResult(
                ok=bool(cached.get("ok")),
                status_code=int(cached.get("status_code", 0)),
                response_text=str(cached.get("response_text", "")),
                replayed=True,
                idempotency_key=idempotency_key,
            )

        url = self._cfg.base_url.rstrip("/") + "/orders"
        payload = self._payload_builder(order)
        body = _json_dumps(payload)

        headers = {
            "Authorization": f"Bearer {self._cfg.api_token}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": self._cfg.user_agent,
            "X-Idempotency-Key": idempotency_key,
        }

        last_status = 0
        last_text = ""
        for attempt in range(1, max(1, self._cfg.max_attempts) + 1):
            status, resp_body = self._transport.request("POST", url, headers, body, self._cfg.timeout_seconds)
            last_status = int(status)
            last_text = resp_body.decode("utf-8", errors="replace")

            if 200 <= last_status < 300:
                self._fail_count = 0
                result = ForwardResult(True, last_status, last_text, False, idempotency_key)
                self._store_put(idempotency_key, {
                    "ok": result.ok,
                    "status_code": result.status_code,
                    "response_text": result.response_text,
                })
                return result

            # retry solo en 5xx
            if last_status >= 500 and attempt < self._cfg.max_attempts:
                time.sleep(self._cfg.backoff_seconds * attempt)
                continue

            break

        # failure path => circuit tracking
        self._fail_count += 1
        if self._fail_count >= self._cfg.circuit_fail_threshold:
            self._circuit_open_until = time.time() + float(self._cfg.circuit_cooldown_seconds)

        result = ForwardResult(False, last_status, last_text, False, idempotency_key)
        self._store_put(idempotency_key, {
            "ok": result.ok,
            "status_code": result.status_code,
            "response_text": result.response_text,
        })
        return result
