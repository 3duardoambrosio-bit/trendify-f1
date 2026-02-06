"""synapse/meta/meta_control_tower_snapshot.py
SYNAPSE — Control Tower Snapshot (CANON)
- Atomic write (tmp + replace)
- Freshness stamp + content fingerprint (fp12)
- Consume outputs in data/run/
marker: CT_SNAPSHOT_CANON_2026-01-20_V1_ATOMIC_FRESHNESS

CLI:
  python -m synapse.meta.meta_control_tower_snapshot --repo . --out data/run/control_tower_snapshot.json
  python -m synapse.meta.meta_control_tower_snapshot . data/run/control_tower_snapshot.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
import logging
logger = logging.getLogger(__name__)

SCHEMA_VERSION = "ct_snapshot_v1"
MARKER = "CT_SNAPSHOT_CANON_2026-01-20_V1_ATOMIC_FRESHNESS"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json_safe(p: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not p.exists():
        return None, "missing"
    try:
        raw = p.read_text(encoding="utf-8")
        if not raw.strip():
            return None, "empty"
        return json.loads(raw), None
    except Exception as e:
        return None, f"invalid_json: {e}"


def get_prop(obj: Any, path: str) -> Any:
    if obj is None:
        return None
    cur = obj
    for k in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
    return cur


def first_non_empty(*vals: Any) -> Any:
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    return None


def git_info(repo: Path) -> Dict[str, Any]:
    def run(args: List[str]) -> str:
        try:
            r = subprocess.run(args, cwd=str(repo), capture_output=True, text=True, timeout=2)
            if r.returncode != 0:
                return "unknown"
            return (r.stdout or "").strip()
        except Exception:
            return "unknown"

    commit = run(["git", "rev-parse", "HEAD"])[:12]
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    dirty = run(["git", "status", "--porcelain"])
    return {
        "commit12": commit if commit else "unknown",
        "branch": branch if branch else "unknown",
        "dirty": bool(dirty.strip()),
    }


def content_fp12(payload: Dict[str, Any]) -> str:
    stable = dict(payload)
    stable.pop("ts", None)
    stable.pop("freshness", None)
    canon = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def atomic_write_json(out_path: Path, data: Dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=out_path.name + ".", suffix=".tmp", dir=str(out_path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_name, str(out_path))
    finally:
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except Exception as e:
            logger.debug("suppressed exception", exc_info=True)

def build_snapshot(repo_root: Path, include_raw: bool = True, trend_n: int = 10) -> Dict[str, Any]:
    run_dir = repo_root / "data" / "run"

    paths = {
        "preflight": run_dir / "meta_publish_preflight.json",
        "run": run_dir / "meta_publish_run.json",
        "report": run_dir / "meta_publish_report.json",
        "autopilot": run_dir / "meta_autopilot.json",
        "policy": run_dir / "meta_policy_check.json",
        "index": run_dir / "meta_publish_runs_index.json",
        "index_nd": run_dir / "meta_publish_runs_index.ndjson",
    }

    preflight, pre_err = read_json_safe(paths["preflight"])
    run_obj, run_err = read_json_safe(paths["run"])
    rep_obj, rep_err = read_json_safe(paths["report"])
    auto_obj, auto_err = read_json_safe(paths["autopilot"])
    pol_obj, pol_err = read_json_safe(paths["policy"])
    idx_obj, idx_err = read_json_safe(paths["index"])

    # KPIs (alineado con test_contract)
    mode = first_non_empty(
        get_prop(run_obj, "mode"),
        get_prop(rep_obj, "mode"),
        "—",
    )

    policy_status = first_non_empty(
        get_prop(pol_obj, "status"),
        get_prop(pol_obj, "result"),
        get_prop(pol_obj, "summary.status"),
        "—",
    )

    autopilot_health = first_non_empty(
        get_prop(auto_obj, "health.status"),
        get_prop(auto_obj, "status"),
        get_prop(auto_obj, "health"),
        "—",
    )

    runs_count = first_non_empty(
        get_prop(idx_obj, "count"),
        get_prop(idx_obj, "total_count"),
        (len(get_prop(idx_obj, "runs")) if isinstance(get_prop(idx_obj, "runs"), list) else None),
        0,
    )

    rows = first_non_empty(
        get_prop(rep_obj, "exec.rows"),
        get_prop(run_obj, "counts.results"),
        get_prop(run_obj, "counts.rows"),
        "—",
    )

    errors = first_non_empty(
        get_prop(rep_obj, "exec.errors"),
        get_prop(run_obj, "counts.errors"),
        0,
    )

    files_count = first_non_empty(
        get_prop(run_obj, "files.count"),
        get_prop(run_obj, "files_count"),
        "—",
    )

    missing_count = first_non_empty(
        get_prop(run_obj, "files.missing"),
        (len(get_prop(run_obj, "files.missing")) if isinstance(get_prop(run_obj, "files.missing"), list) else None),
        get_prop(run_obj, "files_missing"),
        0,
    )

    fp12 = first_non_empty(
        get_prop(run_obj, "run_fingerprint_12"),
        get_prop(preflight, "run_fingerprint_12"),
        "—",
    )

    sha12 = first_non_empty(
        get_prop(run_obj, "files.overall_sha12"),
        get_prop(preflight, "files.overall_sha12"),
        get_prop(run_obj, "overall_sha12"),
        "—",
    )

    trends: Dict[str, Any] = {"runs_last": []}
    runs_list = get_prop(idx_obj, "runs")
    if isinstance(runs_list, list) and runs_list:
        tail = runs_list[-trend_n:]
        for r in tail:
            if not isinstance(r, dict):
                continue
            trends["runs_last"].append({
                "ts": first_non_empty(r.get("ts"), r.get("timestamp"), r.get("time"), ""),
                "mode": r.get("mode", ""),
                "status": r.get("status", r.get("result", "")),
                "path": r.get("path", r.get("filename", "")),
            })

    provenance = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.platform(),
        "host": socket.gethostname(),
        "git": git_info(repo_root),
    }

    raw_errors = {
        "preflight": pre_err,
        "run": run_err,
        "report": rep_err,
        "autopilot": auto_err,
        "policy": pol_err,
        "index": idx_err,
    }

    snapshot: Dict[str, Any] = {
        "marker": MARKER,
        "ts": utc_now_iso(),
        "repo_root": str(repo_root),
        "contract": {
            "schema_version": SCHEMA_VERSION,
            "expects": [str(paths[k].relative_to(repo_root)) for k in ["preflight", "run", "report", "autopilot", "policy", "index"]],
            "notes": "CANON snapshot. Atomic write + freshness + fp.",
        },
        "freshness": {
            "generated_at": utc_now_iso(),
            "max_age_seconds_default": 300,
        },
        "kpis": {
            "mode": mode,
            "policy_status": policy_status,
            "autopilot_health": autopilot_health,
            "runs_count": runs_count,
            "rows": rows,
            "errors": errors,
            "files_count": files_count,
            "missing_count": missing_count,
            "fp12": fp12,
            "sha12": sha12,
        },
        "paths": {k: str(v) for k, v in paths.items()},
        "determinism": {
            "overall_sha12": sha12,
            "run_fingerprint_12": fp12,
            "raw_errors": raw_errors,
        },
        "trends": trends,
        "raw": {},
    }

    if include_raw:
        snapshot["raw"] = {
            "preflight": preflight,
            "run": run_obj,
            "report": rep_obj,
            "autopilot": auto_obj,
            "policy": pol_obj,
            "index": idx_obj,
            "__load_errors": raw_errors,
            "__provenance": provenance,
        }

    snapshot["freshness"]["content_fp12"] = content_fp12(snapshot)
    return snapshot


def parse_args(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", "--root", dest="repo", default=".", help="Repo root (default: .)")
    ap.add_argument("--out", dest="out", default="data/run/control_tower_snapshot.json")
    ap.add_argument("--no-raw", dest="no_raw", action="store_true", help="Do not embed raw JSON payloads")
    ap.add_argument("--trend-n", dest="trend_n", type=int, default=10)
    ap.add_argument("pos_repo", nargs="?", default=None)
    ap.add_argument("pos_out", nargs="?", default=None)
    return ap.parse_args(argv)


def main(argv: List[str]) -> int:
    ns = parse_args(argv)

    repo = Path(ns.repo).resolve()
    if ns.pos_repo and ns.pos_repo.strip():
        repo = Path(ns.pos_repo).resolve()

    out = Path(ns.out)
    if ns.pos_out and ns.pos_out.strip():
        out = Path(ns.pos_out)

    if not out.is_absolute():
        out = (repo / out).resolve()

    snap = build_snapshot(repo_root=repo, include_raw=(not ns.no_raw), trend_n=ns.trend_n)
    atomic_write_json(out, snap)

    k = snap.get("kpis", {})
    print(json.dumps({
        "status": "OK",
        "marker": MARKER,
        "out": str(out),
        "mode": k.get("mode"),
        "runs": k.get("runs_count"),
        "rows": k.get("rows"),
        "errors": k.get("errors"),
        "fp12": k.get("fp12"),
        "sha12": k.get("sha12"),
        "content_fp12": get_prop(snap, "freshness.content_fp12"),
        "ts": snap.get("ts"),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
