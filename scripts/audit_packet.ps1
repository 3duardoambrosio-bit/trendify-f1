$ErrorActionPreference="Stop"
$env:PYTHONPATH="."

New-Item -ItemType Directory -Force "data\backups\audit" | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$out = "data\backups\audit\audit_$ts.txt"

function Add([string]$s) { Add-Content -Path $out -Value $s }

Add "=== SYNAPSE AUDIT PACKET ==="
Add ("timestamp=" + (Get-Date).ToString("o"))
Add ("python=" + (& python -c "import sys; print(sys.version.replace('`n',' '))"))
Add ("cwd=" + (Get-Location).Path)
Add ("branch=" + (git rev-parse --abbrev-ref HEAD))
Add ("commit=" + (git rev-parse HEAD))
Add ""

Add "=== GIT STATUS ==="
git status | Add-Content -Path $out
Add ""

Add "=== GIT LOG (last 30) ==="
git --no-pager log --oneline -n 30 | Add-Content -Path $out
Add ""

Add "=== PYTEST ==="
pytest -q 2>&1 | Add-Content -Path $out
Add ""

Add "=== SMOKE P0 ==="
python scripts\run_smoke_p0.py 2>&1 | Add-Content -Path $out
Add ""

Add "=== LEDGER STATS ==="
if (Test-Path "scripts\ledger_stats.py") {
  python scripts\ledger_stats.py 2>&1 | Add-Content -Path $out
} else {
  Add "LEDGER_STATS: MISSING scripts/ledger_stats.py"
}
Add ""

Add "=== CHECK (FAST) ==="
if (Test-Path "scripts\check.ps1") {
  powershell -ExecutionPolicy Bypass -File scripts\check.ps1 -Fast 2>&1 | Add-Content -Path $out
} else {
  Add "CHECK: MISSING scripts/check.ps1"
}

Write-Host "Audit packet => $out"