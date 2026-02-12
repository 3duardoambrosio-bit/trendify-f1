from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

__MARKER__ = "META_HISTORY_INDEX_2026-01-19_V1"

def _read_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}

def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default

def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default

def _summarize_run(obj: Dict[str, Any], path: Path) -> Dict[str, Any]:
    counts = obj.get("counts") if isinstance(obj.get("counts"), dict) else {}
    files = obj.get("files") if isinstance(obj.get("files"), dict) else {}
    ledger = obj.get("ledger") if isinstance(obj.get("ledger"), dict) else {}

    return {
        "file": str(path),
        "ts": _safe_str(obj.get("ts")),
        "marker": _safe_str(obj.get("marker")),
        "mode": _safe_str(obj.get("mode")),
        "status": _safe_str(obj.get("status")),
        "run_fingerprint_12": _safe_str(obj.get("run_fingerprint_12")),
        "plan_hash": _safe_str(obj.get("plan_hash")),
        "files": {
            "count": _safe_int(files.get("count", 0), 0),
            "missing": _safe_int(files.get("missing", 0), 0),
            "overall_sha12": _safe_str(files.get("overall_sha12", "")),
        },
        "counts": {
            "steps": _safe_int(counts.get("steps", 0), 0),
            "results": _safe_int(counts.get("results", 0), 0),
            "errors": _safe_int(counts.get("errors", 0), 0),
            "issues": _safe_int(counts.get("issues", 0), 0),
            "warns": _safe_int(counts.get("warns", 0), 0),
        },
        "ledger": {
            "enabled": bool(ledger.get("enabled", False)),
            "scope": _safe_str(ledger.get("scope", "")),
            "dir": _safe_str(ledger.get("dir", "")),
        },
    }

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.meta_history_index", description="Index meta_publish_runs/*.json into a single index file.")
    ap.add_argument("--runs-dir", default="data/run/meta_publish_runs", help="Runs directory")
    ap.add_argument("--out-json", default="data/run/meta_publish_runs_index.json")
    ap.add_argument("--out-ndjson", default="data/run/meta_publish_runs_index.ndjson")
    ap.add_argument("--limit", default="2000", help="Max runs to index (default 2000)")
    args = ap.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    out_json = Path(args.out_json)
    out_ndjson = Path(args.out_ndjson)
    limit = int(args.limit)

    runs: List[Dict[str, Any]] = []
    if runs_dir.exists():
        files = sorted(runs_dir.glob("*.json"))
        for p in files[-limit:]:
            obj = _read_json(p)
            if not obj:
                continue
            # only include execute runs (best signal)
            marker = _safe_str(obj.get("marker", ""))
            if "META_PUBLISH_EXECUTE" not in marker and "META_PUBLISH_EXECUTE_DEMO" not in marker:
                # still include if shape looks like execute
                if not isinstance(obj.get("results"), list):
                    continue
            runs.append(_summarize_run(obj, p.resolve()))

    # sort desc by ts (fallback filename)
    runs.sort(key=lambda r: (r.get("ts",""), r.get("file","")), reverse=True)

    payload = {
        "marker": __MARKER__,
        "runs_dir": str(runs_dir.resolve()),
        "count": len(runs),
        "latest_ts": runs[0]["ts"] if runs else "",
        "runs": runs,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    # NDJSON (cada línea = 1 run)
    out_ndjson.parent.mkdir(parents=True, exist_ok=True)
    with out_ndjson.open("w", encoding="utf-8") as f:
        for r in runs:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    cli_print(json.dumps({
        "marker": __MARKER__,
        "status": "OK",
        "count": len(runs),
        "out_json": str(out_json.resolve()),
        "out_ndjson": str(out_ndjson.resolve()),
    }, ensure_ascii=False, indent=2, sort_keys=True))

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
