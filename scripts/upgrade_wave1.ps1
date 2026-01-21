# scripts/upgrade_wave1.ps1
# SYNAPSE ? Wave 1 Upgrade Pack (CANON SNAPSHOT + ATOMIC + FRESHNESS + ENCODING GUARD + CT OPS v8)
# marker: UPGRADE_WAVE1_2026-01-20_V1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section([string]$t) {
  Write-Host ""
  Write-Host "============================================================" -ForegroundColor DarkGray
  Write-Host $t -ForegroundColor Cyan
  Write-Host "============================================================" -ForegroundColor DarkGray
}

function Ensure-Dir([string]$p) {
  $d = Split-Path $p -Parent
  if ($d -and -not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
}

function Write-TextUtf8NoBom([string]$path, [string]$text) {
  Ensure-Dir $path
  $full = (Resolve-Path (Split-Path $path -Parent)).Path
  $leaf = Split-Path $path -Leaf
  $abs = Join-Path $full $leaf
  [System.IO.File]::WriteAllText($abs, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Patch-Gitignore([string]$repoRoot) {
  $gi = Join-Path $repoRoot ".gitignore"
  if (-not (Test-Path $gi)) { New-Item -ItemType File -Force -Path $gi | Out-Null }
  $c = Get-Content $gi -Raw -ErrorAction SilentlyContinue
  if ($null -eq $c) { $c = "" }

  $adds = @(
    "secrets/",
    "data/run/*.log",
    "data/run/*.pid",
    "data/run/pytest_*.log",
    "data/run/control_tower_snapshot_*.json"
  )

  foreach ($a in $adds) {
    if ($c -notmatch "(?m)^\Q$a\E$") {
      Add-Content -Path $gi -Encoding UTF8 -Value $a
    }
  }
}

Write-Section "WAVE 1 ? APPLY UPGRADES"

$repoRoot = (Resolve-Path ".").Path
Write-Host ("Repo: {0}" -f $repoRoot) -ForegroundColor Green

# ----------------------------
# 1) pytest.ini: clean, single import-mode, no BOM
# ----------------------------
Write-Section "PATCH: pytest.ini (NO BOM + single import-mode)"
$pytestIniPath = Join-Path $repoRoot "pytest.ini"
$pytestIni = @"
[pytest]
addopts = -q --import-mode=prepend --ignore=docs/tests
"@
Write-TextUtf8NoBom $pytestIniPath $pytestIni
Write-Host "OK: pytest.ini rewritten (UTF-8 no BOM, import-mode=prepend)" -ForegroundColor Green

# ----------------------------
# 2) Encoding guard script (blocks BOM + invalid UTF-8)
# ----------------------------
Write-Section "WRITE: scripts/check_encoding.py"
$checkEncodingPath = Join-Path $repoRoot "scripts\check_encoding.py"
$checkEncoding = @"
\"\"\"scripts/check_encoding.py
SYNAPSE ? Encoding Guard
- Blocks UTF-8 BOM (EF BB BF)
- Validates UTF-8 decodability
marker: ENCODING_GUARD_2026-01-20_V1
\"\"\"

import sys
from pathlib import Path

BOM = b\"\\xef\\xbb\\xbf\"

DEFAULT_PATTERNS = [
    \"pytest.ini\",
    \"pyproject.toml\",
    \"**/*.py\",
    \"**/*.ps1\",
    \"**/*.json\",
    \"**/*.md\",
    \"**/*.html\",
]

IGNORE_DIRS = {
    \".git\",
    \".venv\",
    \"venv\",
    \"__pycache__\",
    \".pytest_cache\",
    \"node_modules\",
    \"data\",
}

def is_ignored(path: Path) -> bool:
    parts = set(path.parts)
    return any(d in parts for d in IGNORE_DIRS)

def check_file(p: Path):
    try:
        raw = p.read_bytes()
    except Exception as e:
        return False, f\"read_error: {p} -> {e}\"

    if raw.startswith(BOM):
        return False, f\"bom_detected: {p}\"

    try:
        raw.decode(\"utf-8\")
    except UnicodeDecodeError as e:
        return False, f\"invalid_utf8: {p} -> {e}\"

    return True, \"\"

def main():
    repo = Path(__file__).resolve().parent.parent
    patterns = DEFAULT_PATTERNS

    errors = []
    checked = 0

    for pat in patterns:
        for p in repo.glob(pat):
            if not p.is_file():
                continue
            if is_ignored(p):
                continue
            ok, msg = check_file(p)
            checked += 1
            if not ok:
                errors.append(msg)

    if errors:
        print(\"ENCODING GUARD: FAIL\", file=sys.stderr)
        for e in errors:
            print(f\"  - {e}\", file=sys.stderr)
        print(f\"Checked: {checked} files\", file=sys.stderr)
        return 1

    print(f\"ENCODING GUARD: OK (checked {checked} files)\")
    return 0

if __name__ == \"__main__\":
    raise SystemExit(main())
"@
Write-TextUtf8NoBom $checkEncodingPath $checkEncoding
Write-Host "OK: scripts/check_encoding.py" -ForegroundColor Green

# ----------------------------
# 3) Canon + Atomic Snapshot Builder (single truth)
# ----------------------------
Write-Section "WRITE: synapse/meta/meta_control_tower_snapshot.py (CANON + ATOMIC + FRESHNESS)"
$snapshotBuilderPath = Join-Path $repoRoot "synapse\meta\meta_control_tower_snapshot.py"
$snapshotBuilder = @"
\"\"\"synapse/meta/meta_control_tower_snapshot.py
SYNAPSE ? Control Tower Snapshot (CANON)
- Atomic write (tmp + replace)
- Freshness stamp + content fingerprint
- Reads existing outputs in data/run
marker: CT_SNAPSHOT_CANON_2026-01-20_V1_ATOMIC_FRESHNESS

CLI:
  python -m synapse.meta.meta_control_tower_snapshot --repo . --out data/run/control_tower_snapshot.json
  python -m synapse.meta.meta_control_tower_snapshot --root . --out data/run/control_tower_snapshot.json
  python -m synapse.meta.meta_control_tower_snapshot . data/run/control_tower_snapshot.json
\"\"\"

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

SCHEMA_VERSION = \"ct_snapshot_v1\"
MARKER = \"CT_SNAPSHOT_CANON_2026-01-20_V1_ATOMIC_FRESHNESS\"

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def read_json_safe(p: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not p.exists():
        return None, \"missing\"
    try:
        raw = p.read_text(encoding=\"utf-8\")
        if not raw.strip():
            return None, \"empty\"
        return json.loads(raw), None
    except Exception as e:
        return None, f\"invalid_json: {e}\"

def get_prop(obj: Any, path: str) -> Any:
    if obj is None:
        return None
    cur = obj
    for k in path.split(\".\"):
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
                return \"unknown\"
            return (r.stdout or \"\").strip()
        except Exception:
            return \"unknown\"

    commit = run([\"git\", \"rev-parse\", \"HEAD\"])[:12]
    branch = run([\"git\", \"rev-parse\", \"--abbrev-ref\", \"HEAD\"])
    dirty = run([\"git\", \"status\", \"--porcelain\"])
    return {
        \"commit12\": commit if commit else \"unknown\",
        \"branch\": branch if branch else \"unknown\",
        \"dirty\": bool(dirty.strip()),
    }

def content_fp12(payload: Dict[str, Any]) -> str:
    # Fingerprint only stable parts (exclude ts/freshness)
    stable = dict(payload)
    stable.pop(\"ts\", None)
    stable.pop(\"freshness\", None)
    canon = json.dumps(stable, sort_keys=True, separators=(\",\", \":\"), ensure_ascii=False)
    return hashlib.sha256(canon.encode(\"utf-8\")).hexdigest()[:12]

def atomic_write_json(out_path: Path, data: Dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=out_path.name + \".\", suffix=\".tmp\", dir=str(out_path.parent))
    try:
        with os.fdopen(tmp_fd, \"w\", encoding=\"utf-8\", newline=\"\\n\") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write(\"\\n\")
        os.replace(tmp_name, str(out_path))
    finally:
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except Exception:
            pass

def build_snapshot(repo_root: Path, out_path: Path, include_raw: bool = True, trend_n: int = 10) -> Dict[str, Any]:
    run_dir = repo_root / \"data\" / \"run\"

    paths = {
        \"preflight\": run_dir / \"meta_publish_preflight.json\",
        \"run\":      run_dir / \"meta_publish_run.json\",
        \"report\":   run_dir / \"meta_publish_report.json\",
        \"autopilot\":run_dir / \"meta_autopilot.json\",
        \"policy\":   run_dir / \"meta_policy_check.json\",
        \"index\":    run_dir / \"meta_publish_runs_index.json\",
        \"index_nd\": run_dir / \"meta_publish_runs_index.ndjson\",
    }

    preflight, pre_err = read_json_safe(paths[\"preflight\"])
    run_obj,  run_err  = read_json_safe(paths[\"run\"])
    rep_obj,  rep_err  = read_json_safe(paths[\"report\"])
    auto_obj, auto_err = read_json_safe(paths[\"autopilot\"])
    pol_obj,  pol_err  = read_json_safe(paths[\"policy\"])
    idx_obj,  idx_err  = read_json_safe(paths[\"index\"])

    # KPIs (match your current keys)
    mode = first_non_empty(
        get_prop(run_obj, \"mode\"),
        get_prop(rep_obj, \"mode\"),
        get_prop(run_obj, \"run_mode\"),
        get_prop(rep_obj, \"run_mode\"),
        \"?\",
    )

    policy_status = first_non_empty(
        get_prop(pol_obj, \"status\"),
        get_prop(pol_obj, \"result\"),
        get_prop(pol_obj, \"summary.status\"),
        \"?\",
    )

    autopilot_health = first_non_empty(
        get_prop(auto_obj, \"health.status\"),
        get_prop(auto_obj, \"status\"),
        get_prop(auto_obj, \"health\"),
        get_prop(auto_obj, \"context.health\"),
        \"?\",
    )

    runs_count = first_non_empty(
        get_prop(idx_obj, \"count\"),
        get_prop(idx_obj, \"total_count\"),
        (len(get_prop(idx_obj, \"runs\")) if isinstance(get_prop(idx_obj, \"runs\"), list) else None),
        0,
    )

    rows = first_non_empty(
        get_prop(rep_obj, \"exec.rows\"),
        get_prop(rep_obj, \"exec.rows_total\"),
        get_prop(run_obj, \"counts.results\"),
        get_prop(run_obj, \"counts.rows\"),
        \"?\",
    )

    errors = first_non_empty(
        get_prop(rep_obj, \"exec.errors\"),
        get_prop(run_obj, \"counts.errors\"),
        get_prop(rep_obj, \"errors\"),
        get_prop(rep_obj, \"errors_count\"),
        0,
    )

    files_count = first_non_empty(
        get_prop(run_obj, \"files.count\"),
        get_prop(run_obj, \"files_count\"),
        \"?\",
    )

    missing_count = first_non_empty(
        get_prop(run_obj, \"files.missing\"),
        (len(get_prop(run_obj, \"files.missing\")) if isinstance(get_prop(run_obj, \"files.missing\"), list) else None),
        get_prop(run_obj, \"files_missing\"),
        0,
    )

    fp12 = first_non_empty(
        get_prop(run_obj, \"run_fingerprint_12\"),
        get_prop(preflight, \"run_fingerprint_12\"),
        \"?\",
    )

    sha12 = first_non_empty(
        get_prop(run_obj, \"files.overall_sha12\"),
        get_prop(run_obj, \"overall_sha12\"),
        get_prop(preflight, \"files.overall_sha12\"),
        \"?\",
    )

    # Trends (last N runs from index, if available)
    trends: Dict[str, Any] = {\"runs_last\": []}
    runs_list = get_prop(idx_obj, \"runs\")
    if isinstance(runs_list, list) and runs_list:
        tail = runs_list[-trend_n:]
        for r in tail:
            if not isinstance(r, dict):
                continue
            trends[\"runs_last\"].append({
                \"ts\": first_non_empty(r.get(\"ts\"), r.get(\"timestamp\"), r.get(\"time\"), \"\"),
                \"mode\": r.get(\"mode\", \"\"),
                \"status\": r.get(\"status\", r.get(\"result\", \"\")),
                \"path\": r.get(\"path\", r.get(\"filename\", \"\")),
            })

    # Determinism / provenance
    gi = git_info(repo_root)
    provenance = {
        \"python\": f\"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\",
        \"platform\": platform.platform(),
        \"host\": socket.gethostname(),
        \"git\": gi,
    }

    raw_errors = {
        \"preflight\": pre_err,
        \"run\": run_err,
        \"report\": rep_err,
        \"autopilot\": auto_err,
        \"policy\": pol_err,
        \"index\": idx_err,
    }

    snapshot: Dict[str, Any] = {
        \"marker\": MARKER,
        \"ts\": utc_now_iso(),
        \"repo_root\": str(repo_root),
        \"contract\": {
            \"schema_version\": SCHEMA_VERSION,
            \"expects\": [str(paths[k].relative_to(repo_root)) for k in [\"preflight\",\"run\",\"report\",\"autopilot\",\"policy\",\"index\"]],
            \"notes\": \"CANON snapshot. Atomic write + freshness + fp.\",
        },
        \"freshness\": {
            \"generated_at\": utc_now_iso(),
            \"max_age_seconds_default\": 300,
        },
        \"kpis\": {
            \"mode\": mode,
            \"policy_status\": policy_status,
            \"autopilot_health\": autopilot_health,
            \"runs_count\": runs_count,
            \"rows\": rows,
            \"errors\": errors,
            \"files_count\": files_count,
            \"missing_count\": missing_count,
            \"fp12\": fp12,
            \"sha12\": sha12,
        },
        \"paths\": {k: str(v) for k, v in paths.items()},
        \"determinism\": {
            \"overall_sha12\": sha12,
            \"run_fingerprint_12\": fp12,
            \"raw_errors\": raw_errors,
        },
        \"trends\": trends,
        \"raw\": {},
    }

    if include_raw:
        snapshot[\"raw\"] = {
            \"preflight\": preflight,
            \"run\": run_obj,
            \"report\": rep_obj,
            \"autopilot\": auto_obj,
            \"policy\": pol_obj,
            \"index\": idx_obj,
            \"__load_errors\": raw_errors,
            \"__provenance\": provenance,
        }

    # Add stable content fp after structure is ready
    snapshot[\"freshness\"][\"content_fp12\"] = content_fp12(snapshot)

    return snapshot

def parse_args(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument(\"--repo\", \"--root\", dest=\"repo\", default=\".\", help=\"Repo root (default: .)\")
    ap.add_argument(\"--out\", dest=\"out\", default=\"data/run/control_tower_snapshot.json\")
    ap.add_argument(\"--no-raw\", dest=\"no_raw\", action=\"store_true\", help=\"Do not embed raw JSON payloads\")
    ap.add_argument(\"--trend-n\", dest=\"trend_n\", type=int, default=10)
    ap.add_argument(\"pos_repo\", nargs=\"?\", default=None)
    ap.add_argument(\"pos_out\", nargs=\"?\", default=None)
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

    snap = build_snapshot(repo_root=repo, out_path=out, include_raw=(not ns.no_raw), trend_n=ns.trend_n)
    atomic_write_json(out, snap)

    # small stdout summary (for ct_ops)
    k = snap.get(\"kpis\", {})
    print(json.dumps({
        \"status\": \"OK\",
        \"marker\": MARKER,
        \"out\": str(out),
        \"mode\": k.get(\"mode\"),
        \"runs\": k.get(\"runs_count\"),
        \"rows\": k.get(\"rows\"),
        \"errors\": k.get(\"errors\"),
        \"fp12\": k.get(\"fp12\"),
        \"sha12\": k.get(\"sha12\"),
        \"content_fp12\": get_prop(snap, \"freshness.content_fp12\"),
        \"ts\": snap.get(\"ts\"),
    }, indent=2, ensure_ascii=False))
    return 0

if __name__ == \"__main__\":
    raise SystemExit(main(sys.argv[1:]))
"@
Write-TextUtf8NoBom $snapshotBuilderPath $snapshotBuilder
Write-Host "OK: synapse/meta/meta_control_tower_snapshot.py written (CANON)" -ForegroundColor Green

# ----------------------------
# 4) CT Ops v8 ? no autodiscovery, calls canon module, runs encoding guard
# ----------------------------
Write-Section "WRITE: scripts/ct_ops.ps1 (v8 CANON)"
$ctOpsPath = Join-Path $repoRoot "scripts\ct_ops.ps1"
$ctOps = @"
# scripts/ct_ops.ps1
<#
SYNAPSE ? Control Tower Ops (SIM)
marker: CT_OPS_PS1_2026-01-20_V8_CANON_SNAPSHOT

Uso:
  powershell -ExecutionPolicy Bypass -File .\\scripts\\ct_ops.ps1 -Sim -Serve -Open
#>

param(
  [switch]\$Sim,
  [switch]\$Serve,
  [switch]\$Open,
  [switch]\$NoSnapshot,
  [int]\$Port = 8787,
  [string]\$Root = \".\"
)

Set-StrictMode -Version Latest
\$ErrorActionPreference = \"Stop\"

function Write-Section([string]\$t) {
  Write-Host \"\"
  Write-Host \"============================================================\" -ForegroundColor DarkGray
  Write-Host \$t -ForegroundColor Cyan
  Write-Host \"============================================================\" -ForegroundColor DarkGray
}

function Resolve-RepoRoot([string]\$r) {
  \$p = Resolve-Path \$r
  return \$p.Path
}

function Test-PortOpen([int]\$p) {
  try {
    \$conn = Test-NetConnection -ComputerName \"127.0.0.1\" -Port \$p -WarningAction SilentlyContinue
    return [bool]\$conn.TcpTestSucceeded
  } catch { return \$false }
}

function Start-Server([string]\$repoRoot, [int]\$p) {
  if (Test-PortOpen \$p) {
    Write-Host \"Server ya esta arriba en puerto \$p (nice).\" -ForegroundColor Green
    return
  }

  \$logDir = Join-Path \$repoRoot \"data\\run\"
  if (-not (Test-Path \$logDir)) { New-Item -ItemType Directory -Force -Path \$logDir | Out-Null }

  \$logOut = Join-Path \$logDir \"control_tower_server.out.log\"
  \$logErr = Join-Path \$logDir \"control_tower_server.err.log\"

  Write-Host \"Levantando server en puerto \$p (sin secuestrar tu consola)...\" -ForegroundColor Yellow
  \$pyArgs = \"-m http.server \$p --directory `\"\$repoRoot`\"\"
  Start-Process -FilePath \"python\" -ArgumentList \$pyArgs -WorkingDirectory \$repoRoot -WindowStyle Minimized `
    -RedirectStandardOutput \$logOut -RedirectStandardError \$logErr | Out-Null

  Start-Sleep -Milliseconds 400
  if (Test-PortOpen \$p) {
    Write-Host \"Server arriba: http://localhost:\$p\" -ForegroundColor Green
  } else {
    Write-Host \"Ojo: no pude confirmar el server. Revisa logs:\" -ForegroundColor Red
    Write-Host \"  OUT: \$logOut\" -ForegroundColor Red
    Write-Host \"  ERR: \$logErr\" -ForegroundColor Red
  }
}

function Open-Dashboard([int]\$p) {
  \$url = \"http://localhost:\$p/dash/control_tower.html\"
  Write-Host \"Abriendo: \$url\" -ForegroundColor Cyan
  Start-Process \$url | Out-Null
}

function Read-JsonSafe([string]\$path) {
  if (-not (Test-Path \$path)) { return \$null }
  try {
    \$raw = Get-Content \$path -Raw -Encoding UTF8
    if (-not \$raw) { return \$null }
    return (\$raw | ConvertFrom-Json)
  } catch {
    return \$null
  }
}

function Get-Prop(\$obj, [string]\$path) {
  if (\$null -eq \$obj) { return \$null }
  if ([string]::IsNullOrWhiteSpace(\$path)) { return \$null }
  \$cur = \$obj
  foreach (\$k in (\$path -split \"\\.\")) {
    if (\$null -eq \$cur) { return \$null }
    \$props = @()
    try { \$props = \$cur.PSObject.Properties.Name } catch { return \$null }
    if (\$props -notcontains \$k) { return \$null }
    \$cur = \$cur.\$k
  }
  return \$cur
}

function Get-FirstNonEmpty(\$vals) {
  foreach (\$v in \$vals) {
    if (\$null -eq \$v) { continue }
    if (\$v -is [string] -and [string]::IsNullOrWhiteSpace(\$v)) { continue }
    return \$v
  }
  return \$null
}

# ----------------------------
# Main
# ----------------------------
\$repoRoot = Resolve-RepoRoot \$Root
Set-Location \$repoRoot

Write-Section \"CT OPS ? CONTEXT\"
Write-Host (\"Repo: {0}\" -f \$repoRoot) -ForegroundColor Cyan

Write-Section \"PRE-FLIGHT: ENCODING GUARD\"
& python (Join-Path \$repoRoot \"scripts\\check_encoding.py\")
if (\$LASTEXITCODE -ne 0) {
  Write-Host \"Encoding guard FAIL -> abort.\" -ForegroundColor Red
  exit 1
}

if (\$Sim) {
  Write-Section \"RUN: SIM PIPELINE\"
  & powershell -ExecutionPolicy Bypass -File (Join-Path \$repoRoot \"scripts\\run_sim_control_tower.ps1\")
}

if (-not \$NoSnapshot) {
  Write-Section \"BUILD: CONTROL TOWER SNAPSHOT (CANON ATOMIC)\"
  \$out = Join-Path \$repoRoot \"data\\run\\control_tower_snapshot.json\"
  & python -m synapse.meta.meta_control_tower_snapshot --repo \"\$repoRoot\" --out \"\$out\"
  if (\$LASTEXITCODE -ne 0) {
    Write-Host \"WARN: snapshot builder fallo (pero seguimos).\" -ForegroundColor Yellow
  }
}

Write-Section \"CONTROL TOWER ? OUTPUTS (SANITY)\"
\$base = Join-Path \$repoRoot \"data\\run\"
\$paths = @{
  preflight = (Join-Path \$base \"meta_publish_preflight.json\")
  run       = (Join-Path \$base \"meta_publish_run.json\")
  report    = (Join-Path \$base \"meta_publish_report.json\")
  autopilot = (Join-Path \$base \"meta_autopilot.json\")
  policy    = (Join-Path \$base \"meta_policy_check.json\")
  index     = (Join-Path \$base \"meta_publish_runs_index.json\")
  snapshot  = (Join-Path \$base \"control_tower_snapshot.json\")
}

foreach (\$k in \$paths.Keys) {
  \$exists = Test-Path \$paths[\$k]
  \$mark = if (\$exists) { \"OK \" } else { \"MISS\" }
  \$color = if (\$exists) { \"Green\" } else { \"Red\" }
  Write-Host (\"[{0}] {1}\" -f \$mark, \$paths[\$k]) -ForegroundColor \$color
}

Write-Section \"EXEC SUMMARY (FROM SNAPSHOT)\"
\$snap = Read-JsonSafe \$paths.snapshot
if (\$null -eq \$snap) {
  Write-Host \"Snapshot no cargable. Revisa data/run/control_tower_snapshot.json\" -ForegroundColor Yellow
} else {
  \$k = \$snap.kpis
  Write-Host (\"Mode:      {0}\" -f \$k.mode) -ForegroundColor Cyan
  Write-Host (\"Policy:    {0}\" -f \$k.policy_status) -ForegroundColor Cyan
  Write-Host (\"Autopilot: {0}\" -f \$k.autopilot_health) -ForegroundColor Cyan
  Write-Host (\"Runs:      {0}\" -f \$k.runs_count) -ForegroundColor Cyan
  Write-Host (\"Rows/Err:  {0} rows | {1} errors\" -f \$k.rows, \$k.errors) -ForegroundColor Cyan
  Write-Host (\"FP12/SHA:  {0} | {1}\" -f \$k.fp12, \$k.sha12) -ForegroundColor Cyan
  Write-Host (\"ContentFP: {0}\" -f (Get-Prop \$snap \"freshness.content_fp12\")) -ForegroundColor Cyan
}

if (\$Serve) { Start-Server \$repoRoot \$Port }
if (\$Open)  { Open-Dashboard \$Port }
"@
Write-TextUtf8NoBom $ctOpsPath $ctOps
Write-Host "OK: scripts/ct_ops.ps1 written (v8)" -ForegroundColor Green

# ----------------------------
# 5) .gitignore patch
# ----------------------------
Write-Section "PATCH: .gitignore (safe ignores)"
Patch-Gitignore $repoRoot
Write-Host "OK: .gitignore patched" -ForegroundColor Green

Write-Section "DONE ? NEXT COMMANDS"
Write-Host "1) python -m pytest -q" -ForegroundColor Green
Write-Host "2) powershell -ExecutionPolicy Bypass -File .\scripts\ct_ops.ps1 -Sim -Serve -Open" -ForegroundColor Green
