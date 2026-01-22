Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-LastExitCode([string]$step) {
  if ($LASTEXITCODE -ne 0) {
    throw ("STEP_FAILED: {0} (exit={1})" -f $step, $LASTEXITCODE)
  }
}

# Release Gate (default: seed + canonical)
$ProductId    = "seed"
$CanonicalCsv = "data\catalog\candidates_real.csv"
$OutRoot      = "exports"

Write-Host "============================================================"
Write-Host "WAVEKIT RELEASE GATE (NO API/TOKENS)"
Write-Host "============================================================"
Write-Host ("Repo: {0}" -f (Get-Location))
Write-Host ("ProductId: {0}" -f $ProductId)
Write-Host ("CanonicalCsv: {0}" -f $CanonicalCsv)
Write-Host ("OutRoot: {0}" -f $OutRoot)
Write-Host ""

Write-Host "==> pytest"
pytest -q
Assert-LastExitCode "pytest"

Write-Host ""
Write-Host "==> doctor"
python -m synapse.infra.doctor
Assert-LastExitCode "doctor"

Write-Host ""
Write-Host "==> wave --apply"
python -m synapse.cli wave --product-id $ProductId --apply --out-root $OutRoot --canonical-csv $CanonicalCsv
Assert-LastExitCode "wave_apply"

Write-Host ""
Write-Host "==> harden_wavekit (STRICT)"
$hardenOut = & python scripts\harden_wavekit.py (Join-Path $OutRoot $ProductId) 2>&1
$hardenOut | ForEach-Object { Write-Host $_ }
Assert-LastExitCode "harden_wavekit"

# Parse JSON summary line
$jsonLine = $hardenOut | Where-Object { $_ -like "HARDEN_SUMMARY_JSON=*" } | Select-Object -Last 1
if (-not $jsonLine) {
  throw "HARDEN_SUMMARY_JSON not found. harden_wavekit output changed or failed."
}
$json = $jsonLine.Substring("HARDEN_SUMMARY_JSON=".Length)
$summary = $json | ConvertFrom-Json

# HARD FAIL if hardener had to change files (means generator isn't clean)
if ($summary.normalized_files -gt 0) {
  throw ("RELEASE_BLOCKED: wavekit not clean. normalized_files={0}. Fix generator (no BOM/CRLF)." -f $summary.normalized_files)
}

Write-Host ""
Write-Host "==> seal release dir"
$sha = (git rev-parse --short=12 HEAD).Trim()
Assert-LastExitCode "git_rev_parse"

$rel = "exports\releases\$ProductId\$sha"
New-Item -ItemType Directory -Force $rel | Out-Null

Copy-Item ("exports\wave_kit_{0}.zip" -f $ProductId), ("exports\wave_kit_{0}.sha256" -f $ProductId) $rel -Force

Write-Host ("OK RELEASE_DIR={0}" -f $rel)
Write-Host ("OK FILE={0}" -f (Join-Path $rel ("wave_kit_{0}.zip" -f $ProductId)))
Write-Host ("OK SHA ={0}" -f (Join-Path $rel ("wave_kit_{0}.sha256" -f $ProductId)))
