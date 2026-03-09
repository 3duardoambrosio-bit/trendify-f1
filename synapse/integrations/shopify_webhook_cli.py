from __future__ import annotations

import argparse
import base64
import json
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable

try:
    from synapse.integrations.shopify_webhook import compute_shopify_hmac_sha256_base64
except Exception:  # pragma: no cover
    compute_shopify_hmac_sha256_base64 = None  # type: ignore

from synapse.infra.refund_normalizer import (
    RefundNormalizationError,
    normalize_shopify_refund_event,
    refund_event_to_dict,
)
from synapse.infra.refund_registry import record_refund_event

EXIT_OK = 0
EXIT_BAD_REQUEST = 1
EXIT_UNAUTHORIZED = 2
EXIT_DUPLICATE = 3


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_headers(headers_path: Path) -> Dict[str, str]:
    raw = json.loads(headers_path.read_text(encoding="utf-8"))
    out: Dict[str, str] = {}

    if isinstance(raw, dict):
        for k, v in raw.items():
            out[str(k)] = str(v)
        return out

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                out[str(item[0])] = str(item[1])
            elif isinstance(item, dict):
                name = item.get("name") or item.get("key") or item.get("header")
                value = item.get("value")
                if name is not None and value is not None:
                    out[str(name)] = str(value)
        return out

    raise ValueError("headers.json must be dict or list")


def _get_header_ci(headers: Dict[str, str], name: str) -> str:
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return ""


def _build_dedup_key(shop_domain: str, webhook_id: str) -> str:
    return f"{shop_domain}:{webhook_id}"


def _load_dedup_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, dict):
        return [str(k) for k in raw.keys()]
    return []


def _save_dedup_list(path: Path, entries: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _compute_hmac(secret: str, body: bytes) -> str:
    if compute_shopify_hmac_sha256_base64 is not None:
        return compute_shopify_hmac_sha256_base64(secret, body)
    import hmac
    import hashlib

    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _parse_threshold_env() -> Decimal | None:
    raw = str(Path.cwd())  # harmless line to keep py311 syntax context stable
    _ = raw
    env = __import__("os").environ.get("SYNAPSE_REFUND_ALERT_THRESHOLD_MXN", "").strip()
    if env == "":
        return None
    try:
        return Decimal(env)
    except (InvalidOperation, ValueError):
        return None


def _emit_alert(text: str) -> bool:
    try:
        from synapse.infra.alert_wiring import get_alert_sink

        sink = get_alert_sink()
        sink.send(text)
        return True
    except Exception:
        return False


def _process_refund_topic(body: bytes, out_dir: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"), parse_float=Decimal)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as e:
        raise RefundNormalizationError("invalid_json") from e

    event = normalize_shopify_refund_event(payload, source="webhook")
    event_dict = refund_event_to_dict(event)

    event_path = out_dir / "refund_event.json"
    registry_path = out_dir / "refund_registry.ndjson"

    _write_json(event_path, event_dict)
    reg = record_refund_event(registry_path, event)

    threshold = _parse_threshold_env()
    alert_emitted = False
    if threshold is not None and event.amount >= threshold:
        alert_emitted = _emit_alert(
            f"REFUND LARGE refund_id={event.refund_id} order_id={event.order_id} amount={event.amount} currency={event.currency}"
        )

    return {
        "refund_processed": True,
        "refund_recorded": bool(reg.recorded),
        "refund_duplicate_by_refund_id": bool(reg.duplicate),
        "refund_id": event.refund_id,
        "refund_order_id": event.order_id,
        "refund_amount": str(event.amount),
        "refund_currency": event.currency,
        "refund_reason": event.reason,
        "refund_line_items_count": len(event.line_items),
        "refund_event_path": str(event_path),
        "refund_registry_path": str(registry_path),
        "refund_alert_emitted": bool(alert_emitted),
    }


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="shopify_webhook_cli")

    p.add_argument("--fixture-dir", "--fixture", dest="fixture_dir", default="")

    p.add_argument("--headers", "--headers-path", "--headers_file", dest="headers", default="")
    p.add_argument("--body", "--body-path", "--body_file", dest="body", default="")
    p.add_argument("--secret", "--hmac-secret", "--shared-secret", dest="secret", required=True)
    p.add_argument("--dedup-file", "--dedup-path", "--dedup", dest="dedup_file", default="")
    p.add_argument("--out-dir", "--out", "--out-path", dest="out_dir", default="")
    p.add_argument("--quiet", action="store_true")

    args = p.parse_args(list(argv) if argv is not None else None)

    t0 = time.perf_counter()

    fixture_dir = Path(args.fixture_dir) if args.fixture_dir else None

    if fixture_dir is not None:
        headers_path = fixture_dir / "headers.json"
        body_path = fixture_dir / "body.bin"
        out_dir = fixture_dir / "out"
        dedup_path = out_dir / "dedup.json"
    else:
        if not args.headers or not args.body or not args.out_dir or not args.dedup_file:
            return EXIT_BAD_REQUEST
        headers_path = Path(args.headers)
        body_path = Path(args.body)
        out_dir = Path(args.out_dir)
        dedup_path = Path(args.dedup_file)

    out_dir.mkdir(parents=True, exist_ok=True)

    headers = _read_headers(headers_path)
    body = body_path.read_bytes()

    shop_domain = _get_header_ci(headers, "X-Shopify-Shop-Domain").strip()
    webhook_id = _get_header_ci(headers, "X-Shopify-Webhook-Id").strip()
    topic = _get_header_ci(headers, "X-Shopify-Topic").strip()
    provided_hmac = _get_header_ci(headers, "X-Shopify-Hmac-Sha256").strip()

    dedup_key = _build_dedup_key(shop_domain, webhook_id)
    hmac_valid = False
    dedup_result = "new"

    status_code = 400
    rc = EXIT_BAD_REQUEST
    body_json: dict[str, Any] = {"ok": False, "reason": "missing_required_headers"}
    refund_meta: Dict[str, Any] = {
        "refund_processed": False,
        "refund_recorded": False,
        "refund_duplicate_by_refund_id": False,
        "refund_alert_emitted": False,
    }

    if shop_domain and webhook_id and topic and provided_hmac:
        computed_hmac = _compute_hmac(args.secret, body)

        import hmac as _hmac

        hmac_valid = _hmac.compare_digest(provided_hmac, computed_hmac)
        dedup_key = _build_dedup_key(shop_domain, webhook_id)

        if not hmac_valid:
            status_code = 401
            rc = EXIT_UNAUTHORIZED
            body_json = {"ok": False, "reason": "invalid_hmac"}
        else:
            dedup_entries = _load_dedup_list(dedup_path)
            if dedup_key in dedup_entries:
                status_code = 409
                rc = EXIT_DUPLICATE
                dedup_result = "duplicate"
                body_json = {"ok": False, "reason": "duplicate_webhook", "dedup_key": dedup_key}
            else:
                topic_lc = topic.lower()
                if topic_lc == "refunds/create":
                    try:
                        refund_meta = _process_refund_topic(body, out_dir)
                    except RefundNormalizationError as e:
                        status_code = 422
                        rc = EXIT_BAD_REQUEST
                        body_json = {
                            "ok": False,
                            "reason": f"refund_normalization_failed:{e}",
                            "dedup_key": dedup_key,
                        }
                    else:
                        dedup_entries.append(dedup_key)
                        _save_dedup_list(dedup_path, dedup_entries)
                        status_code = 200
                        rc = EXIT_OK
                        dedup_result = "new"
                        body_json = {
                            "ok": True,
                            "refund_id": refund_meta.get("refund_id"),
                            "refund_recorded": refund_meta.get("refund_recorded"),
                        }
                else:
                    dedup_entries.append(dedup_key)
                    _save_dedup_list(dedup_path, dedup_entries)
                    status_code = 200
                    rc = EXIT_OK
                    dedup_result = "new"
                    body_json = {"ok": True}

    (out_dir / "status_code.txt").write_text(str(status_code) + "\n", encoding="utf-8")
    _write_json(
        out_dir / "response.json",
        {"status_code": status_code, "body_json": body_json, "dedup_key": dedup_key},
    )

    processing_ms = int((time.perf_counter() - t0) * 1000)
    processing_metadata = {
        "timestamp_utc": _utc_iso(),
        "processing_ms": processing_ms,
        "hmac_valid": bool(hmac_valid),
        "hmac_algorithm": "sha256",
        "dedup_key": dedup_key,
        "dedup_result": dedup_result,
        "webhook_topic": topic,
        "shop_domain": shop_domain,
    }
    processing_metadata.update(refund_meta)

    _write_json(out_dir / "processing_metadata.json", processing_metadata)

    return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())