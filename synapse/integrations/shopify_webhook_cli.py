from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, MutableSet, Optional

from synapse.integrations.shopify_webhook_adapter import handle_shopify_webhook_http


def _read_bytes(p: Path) -> bytes:
    return p.read_bytes()


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _dump_json(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_headers(obj: Any) -> Dict[str, str]:
    if isinstance(obj, dict):
        return {str(k): str(v) for k, v in obj.items()}

    # allow list of {"name": "...", "value": "..."} or [ [k,v], ... ]
    if isinstance(obj, list):
        out: Dict[str, str] = {}
        for it in obj:
            if isinstance(it, dict) and "name" in it and "value" in it:
                out[str(it["name"])] = str(it["value"])
            elif isinstance(it, (list, tuple)) and len(it) == 2:
                out[str(it[0])] = str(it[1])
            else:
                raise ValueError(f"invalid headers item: {it!r}")
        return out

    raise ValueError("headers.json must be dict or list")


def _load_dedup(path: Optional[Path]) -> Optional[MutableSet[str]]:
    if path is None:
        return None
    if not path.exists():
        return set()
    obj = _load_json(path)
    if obj is None:
        return set()
    if not isinstance(obj, list):
        raise ValueError("dedup file must be JSON list of strings")
    return set(str(x) for x in obj)


def _save_dedup(path: Optional[Path], dedup: Optional[MutableSet[str]]) -> None:
    if path is None or dedup is None:
        return
    _dump_json(path, sorted(dedup))


def _safe_result_dict(result_obj: Any) -> Dict[str, Any]:
    """
    Convert result dataclass to JSON-safe dict.
    raw_body (bytes) => raw_body_b64 (str), and remove raw_body.
    """
    d: Dict[str, Any] = asdict(result_obj)

    ev = d.get("event")
    if isinstance(ev, dict) and "raw_body" in ev:
        rb = ev.get("raw_body")
        if isinstance(rb, (bytes, bytearray, memoryview)):
            ev["raw_body_b64"] = base64.b64encode(bytes(rb)).decode("ascii")
        ev.pop("raw_body", None)

    return d


def _response_artifact(resp: Any) -> Dict[str, Any]:
    # resp is ShopifyWebhookHTTPResponse dataclass
    try:
        body_json: Any = json.loads(resp.body.decode("utf-8"))
    except Exception:
        body_json = {"_parse_error": "invalid_json_response"}

    return {
        "status_code": int(resp.status_code),
        "headers": dict(resp.headers),
        "body_json": body_json,
        "body_b64": base64.b64encode(resp.body).decode("ascii"),
        "result": _safe_result_dict(resp.result),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="shopify_webhook_cli", add_help=True)
    ap.add_argument("--headers", required=True, help="Path to headers.json")
    ap.add_argument("--body", required=True, help="Path to raw body bytes (body.bin)")
    ap.add_argument("--secret", default=None, help="Shared secret (string)")
    ap.add_argument("--secret-file", default=None, help="Path to secret.txt")
    ap.add_argument("--dedup-file", default=None, help="Path to dedup.json (persisted list)")
    ap.add_argument("--out-dir", default="out", help="Output directory")
    ap.add_argument("--quiet", action="store_true", help="Do not write stdout (still writes files)")
    args = ap.parse_args(argv)

    headers_path = Path(args.headers)
    body_path = Path(args.body)
    out_dir = Path(args.out_dir)
    dedup_path = Path(args.dedup_file) if args.dedup_file else None

    if args.secret and args.secret_file:
        raise ValueError("use --secret OR --secret-file, not both")

    secret = args.secret if args.secret is not None else (_read_text(Path(args.secret_file)) if args.secret_file else None)
    if not secret:
        raise ValueError("missing secret: pass --secret or --secret-file")

    headers_obj = _load_json(headers_path)
    headers = _normalize_headers(headers_obj)
    body = _read_bytes(body_path)

    dedup = _load_dedup(dedup_path)

    out_dir.mkdir(parents=True, exist_ok=True)
    resp = handle_shopify_webhook_http(secret=secret, headers=headers, body=body, dedup_set=dedup)

    _save_dedup(dedup_path, dedup)

    _dump_json(out_dir / "response.json", _response_artifact(resp))
    (out_dir / "status_code.txt").write_text(str(int(resp.status_code)) + "\n", encoding="utf-8")

    if not args.quiet:
        sys.stdout.write("OK=1\n")
        sys.stdout.write(f"status_code={int(resp.status_code)}\n")
        sys.stdout.flush()

    # exit code contract:
    # 0 accepted, 3 rejected (includes duplicates)
    return 0 if int(resp.status_code) == 200 else 3


if __name__ == "__main__":
    raise SystemExit(main())