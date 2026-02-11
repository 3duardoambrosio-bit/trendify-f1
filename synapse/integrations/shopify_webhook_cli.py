from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any, Dict, Iterable

try:
    from synapse.integrations.shopify_webhook import compute_shopify_hmac_sha256_base64
except Exception:  # pragma: no cover
    compute_shopify_hmac_sha256_base64 = None  # type: ignore

EXIT_OK = 0
EXIT_BAD_REQUEST = 1
EXIT_UNAUTHORIZED = 2
EXIT_DUPLICATE = 3


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
    except Exception:
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

    status_code = 400
    rc = EXIT_BAD_REQUEST
    body_json: dict[str, Any] = {"ok": False, "reason": "missing_required_headers"}

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
                body_json = {"ok": False, "reason": "duplicate_webhook", "dedup_key": dedup_key}
            else:
                dedup_entries.append(dedup_key)
                _save_dedup_list(dedup_path, dedup_entries)
                status_code = 200
                rc = EXIT_OK
                body_json = {"ok": True}

    (out_dir / "status_code.txt").write_text(str(status_code) + "\n", encoding="utf-8")
    _write_json(out_dir / "response.json", {"status_code": status_code, "body_json": body_json, "dedup_key": dedup_key})

    return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())