Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Release Gate (default: seed + canonical)
$ProductId    = "seed"
$CanonicalCsv = "data\catalog\candidates_real.csv"
$OutRoot      = "exports"

Write-Host "============================================================"
Write-Host "WAVEKIT RELEASE GATE (NO API/TOKENS) "
Write-Host "============================================================"
Write-Host ("Repo: {0}" -f (Get-Location))
Write-Host ("ProductId: {0}" -f $ProductId)
Write-Host ("CanonicalCsv: {0}" -f $CanonicalCsv)
Write-Host ("OutRoot: {0}" -f $OutRoot)
Write-Host ""

# 1) Quality gates
Write-Host "==> pytest"
pytest -q

Write-Host ""
Write-Host "==> doctor"
python -m synapse.infra.doctor

Write-Host ""
Write-Host "==> wave --apply"
python -m synapse.cli wave --product-id $ProductId --apply --out-root $OutRoot --canonical-csv $CanonicalCsv

# 2) Harden + validate + produce exports\wave_kit_<product>.zip
Write-Host ""
Write-Host "==> harden_wavekit"
python scripts\harden_wavekit.py (Join-Path $OutRoot $ProductId)

# 3) Release folder by git sha
Write-Host ""
Write-Host "==> seal release dir"
$sha = (git rev-parse --short=12 HEAD).Trim()
$rel = "exports\releases\$ProductId\$sha"
New-Item -ItemType Directory -Force $rel | Out-Null

Copy-Item ("exports\wave_kit_{0}.zip" -f $ProductId), ("exports\wave_kit_{0}.sha256" -f $ProductId) $rel -Force

Write-Host ("OK RELEASE_DIR={0}" -f $rel)
Write-Host ("OK FILE={0}" -f (Join-Path $rel ("wave_kit_{0}.zip" -f $ProductId)))
Write-Host ("OK SHA ={0}" -f (Join-Path $rel ("wave_kit_{0}.sha256" -f $ProductId)))