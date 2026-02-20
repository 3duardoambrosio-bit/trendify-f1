from __future__ import annotations

from synapse.infra.cli_logging import cli_print


import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
logger = logging.getLogger(__name__)


DEFAULT_REL = Path("data/ledger/events.ndjson")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_ts_utc(ts: Optional[str]) -> str:
    s = (ts or "").strip()
    if not s:
        return _utc_now_z()
    # normalize +00:00 -> Z
    if s.endswith("+00:00"):
        s = s[:-6] + "Z"
    # if no timezone marker, force Z (UTC)
    if s.endswith("Z"):
        return s
    # crude check for timezone offset at end like -06:00 or +01:00
    tail = s[-6:]
    if (len(tail) == 6) and (tail[0] in ("+", "-")) and (tail[3] == ":"):
        return s
    return s + "Z"


def _read_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, FileNotFoundError):
        return []


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line.rstrip("\n") + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_json_loads(s: str) -> Tuple[Optional[Any], Optional[str]]:
    try:
        return json.loads(s), None
    except (json.JSONDecodeError, TypeError) as e:
        return None, str(e)


def _make_event(payload: Dict[str, Any], ts: Optional[str] = None) -> Dict[str, Any]:
    ts_utc = _normalize_ts_utc(ts)
    # Keep both: ts_utc (contract) + ts (legacy compatibility)
    return {
        "ts_utc": ts_utc,
        "ts": ts_utc,
        "payload": payload,
    }


def _ensure_payload(obj: Any) -> Optional[Dict[str, Any]]:
    """
    Normaliza a evento con contrato:
      { "ts_utc": "...Z", "payload": {...} }
    Mantiene también "ts" por compatibilidad.
    """
    if not isinstance(obj, dict):
        return None

    # If already event-like
    if "payload" in obj and isinstance(obj["payload"], dict):
        ts_in = obj.get("ts_utc") or obj.get("ts") or obj.get("timestamp")
        return _make_event(obj["payload"], ts=str(ts_in) if ts_in else None)

    # Wrap common keys
    for k in ("data", "record", "event", "body"):
        if k in obj and isinstance(obj[k], dict):
            ts_in = obj.get("ts_utc") or obj.get("ts") or obj.get("timestamp")
            return _make_event(obj[k], ts=str(ts_in) if ts_in else None)

    # payload directo
    return _make_event(obj)


def _write_genesis(path: Path) -> None:
    """
    Ledger contract: nunca vacío + cada línea debe traer ts_utc.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    ev = _make_event({
        "event_type": "LEDGER_GENESIS",
        "marker": "SYSTEM_GENESIS",
        "source": "system",
        "note": "ledger initialized/reset",
    })
    line = json.dumps(ev, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    path.write_text(line + "\n", encoding="utf-8")


def cmd_init(path: Path, force: bool) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not force:
        lines = _read_lines(path)
        if any(ln.strip() for ln in lines):
            cli_print(f"OK: ledger exists -> {path}")
            return 0
        _write_genesis(path)
        cli_print(f"OK: ledger existed but empty -> wrote genesis -> {path}")
        return 0

    _write_genesis(path)
    cli_print(f"OK: ledger initialized -> {path}")
    return 0


def cmd_reset(path: Path) -> int:
    _write_genesis(path)
    cli_print(f"OK: ledger reset (genesis kept) -> {path}")
    return 0


def cmd_append(path: Path, json_str: Optional[str], json_file: Optional[Path]) -> int:
    if json_file is not None:
        if not json_file.exists():
            cli_print(f"ERROR: file not found: {json_file}", file=sys.stderr)
            return 2
        raw = json_file.read_text(encoding="utf-8")
    else:
        raw = (json_str or "").strip()

    if not raw:
        cli_print("ERROR: provide --json '{...}' or --file path.json", file=sys.stderr)
        return 2

    obj, err = _safe_json_loads(raw)
    if err:
        cli_print(f"ERROR: invalid JSON: {err}", file=sys.stderr)
        return 2

    ev = _ensure_payload(obj)
    if ev is None:
        cli_print("ERROR: JSON must be an object/dict.", file=sys.stderr)
        return 2

    line = json.dumps(ev, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    _append_line(path, line)
    cli_print(f"OK: appended 1 event -> {path}")
    return 0


def _seed_payload(i: int, platform: str) -> Dict[str, Any]:
    roas = 1.5 + (i * 0.05)
    hook = 18 + i
    spend = 5.0
    return {
        "event_type": "AD_RESULTS",
        "product_id": "34357",
        "platform": platform,
        "utm_content": f"Hh{i}_Adolor_Fhands_V1",
        "spend": spend,
        "impressions": 1000,
        "clicks": 20 + i,
        "conversions": 1,
        "roas": roas,
        "hook_rate_3s": hook,
        "marker": "SYNTHETIC_SEED",
        "source": "seed",
    }


def cmd_seed(path: Path, n: int, platform: str, seed: int) -> int:
    rng = random.Random(seed)

    lines = _read_lines(path)
    if not any(ln.strip() for ln in lines):
        _write_genesis(path)

    for i in range(n):
        base = _seed_payload(i, platform=platform)
        base["clicks"] = int(base["clicks"]) + rng.randint(0, 3)
        base["impressions"] = int(base["impressions"]) + rng.randint(0, 200)
        ev = _make_event(base)
        line = json.dumps(ev, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        _append_line(path, line)

    cli_print(f"OK: seeded {n} events -> {path}")
    return 0


def cmd_validate(path: Path) -> int:
    lines = _read_lines(path)
    if not lines or not any(ln.strip() for ln in lines):
        _write_genesis(path)
        cli_print(f"OK: empty ledger fixed -> wrote genesis -> {path}")
        return 0

    bad = 0
    good = 0
    for idx, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        obj, err = _safe_json_loads(line)
        if err:
            bad += 1
            cli_print(f"BAD line {idx}: invalid JSON: {err}", file=sys.stderr)
            continue
        if not isinstance(obj, dict):
            bad += 1
            cli_print(f"BAD line {idx}: not a JSON object", file=sys.stderr)
            continue
        ts = str(obj.get("ts_utc") or "").strip()
        if not ts:
            bad += 1
            cli_print(f"BAD line {idx}: missing ts_utc", file=sys.stderr)
            continue
        if not isinstance(obj.get("payload"), dict):
            bad += 1
            cli_print(f"BAD line {idx}: missing/invalid payload", file=sys.stderr)
            continue
        good += 1

    if bad:
        cli_print(f"VALIDATE: {good} good, {bad} bad -> {path}", file=sys.stderr)
        return 2
    cli_print(f"VALIDATE: {good} good, {bad} bad -> {path}")
    return 0


def cmd_stats(path: Path) -> int:
    lines = _read_lines(path)
    total = 0
    spend_sum = 0.0
    payload_ok = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        obj, err = _safe_json_loads(line)
        if err or not isinstance(obj, dict):
            continue
        if not str(obj.get("ts_utc") or "").strip():
            continue
        p = obj.get("payload")
        if not isinstance(p, dict):
            continue
        total += 1
        payload_ok += 1
        try:
            spend_sum += float(p.get("spend") or 0.0)
        except (ValueError, TypeError) as e:
            logger.debug("suppressed exception", exc_info=True)

    cli_print(json.dumps({
        "ledger": str(path),
        "lines_total": len(lines),
        "events_total": total,
        "events_payload_ok": payload_ok,
        "total_spend_sum": spend_sum,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="synapse.ledger_ndjson", description="NDJSON ledger tools (Fase 1).")
    p.add_argument("--path", default=str(DEFAULT_REL), help="Ledger path (default: data/ledger/events.ndjson)")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp_init = sub.add_parser("init", help="Create ledger file if missing (or truncate with --force).")
    sp_init.add_argument("--force", action="store_true", help="Truncate existing file (keeps genesis).")

    sub.add_parser("reset", help="Truncate ledger file (keeps genesis).")

    sp_append = sub.add_parser("append", help="Append one event line from JSON.")
    sp_append.add_argument("--json", default=None, help="Inline JSON string. Example: --json '{\"payload\":{...}}'")
    sp_append.add_argument("--file", default=None, help="Path to .json file containing object.")

    sp_seed = sub.add_parser("seed", help="Append N synthetic events (good for smoke tests).")
    sp_seed.add_argument("--n", type=int, default=10, help="How many events to append.")
    sp_seed.add_argument("--platform", default="meta", choices=["meta", "tiktok", "google"], help="Platform tag.")
    sp_seed.add_argument("--seed", type=int, default=1337, help="Deterministic seed.")

    sub.add_parser("validate", help="Validate NDJSON structure.")
    sub.add_parser("stats", help="Quick stats (count, spend sum).")

    args = p.parse_args(argv)
    path = Path(args.path).expanduser().resolve()

    if args.cmd == "init":
        return cmd_init(path, force=bool(args.force))
    if args.cmd == "reset":
        return cmd_reset(path)
    if args.cmd == "append":
        jf = Path(args.file).expanduser().resolve() if args.file else None
        return cmd_append(path, json_str=args.json, json_file=jf)
    if args.cmd == "seed":
        return cmd_seed(path, n=int(args.n), platform=str(args.platform), seed=int(args.seed))
    if args.cmd == "validate":
        return cmd_validate(path)
    if args.cmd == "stats":
        return cmd_stats(path)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())