$ErrorActionPreference="Stop"
$env:PYTHONPATH="."

New-Item -ItemType Directory -Force "data\backups\audit" | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$out = "data\backups\audit\audit_$ts.txt"

Add-Content -Path $out -Value "=== SYNAPSE AUDIT PACKET ==="
Add-Content -Path $out -Value ("timestamp=" + (Get-Date).ToString("o"))
Add-Content -Path $out -Value ("branch=" + (git rev-parse --abbrev-ref HEAD))
Add-Content -Path $out -Value ("commit=" + (git rev-parse HEAD))
Add-Content -Path $out -Value ""

Add-Content -Path $out -Value "=== GIT LOG (last 20) ==="
git --no-pager log --oneline -n 20 | Add-Content -Path $out
Add-Content -Path $out -Value ""

Add-Content -Path $out -Value "=== PYTEST ==="
pytest -q 2>&1 | Add-Content -Path $out
Add-Content -Path $out -Value ""

Add-Content -Path $out -Value "=== SMOKE P0 ==="
python scripts\run_smoke_p0.py 2>&1 | Add-Content -Path $out
Add-Content -Path $out -Value ""

Add-Content -Path $out -Value "=== LEDGER STATS ==="
python scripts\ledger_stats.py 2>&1 | Add-Content -Path $out

Write-Host "Audit packet => $out"