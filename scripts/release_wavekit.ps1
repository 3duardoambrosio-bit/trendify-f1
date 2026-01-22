Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Release Gate (default: seed + canonical)
$ProductId    = "seed"
$CanonicalCsv = "data\catalog\candidates_real.csv"
$OutRoot      = "exports"

function Fail([string]$msg){
  throw $msg
}

function Require-CleanGit(){
  $lines = (git status --porcelain=v1) 2>$null
  if($LASTEXITCODE -ne 0){ Fail "GIT not available / not a repo." }

  if(-not $lines){ return }

  # Allowlist: generated outputs + caches (we ignore these)
  $allow = @(
    '^\?\?\s+exports[\\/]',
    '^\?\?\s+data[\\/]run[\\/]',
    '^\?\?\s+\.pytest_cache[\\/]',
    '^\?\?\s+__pycache__[\\/]',
    '^\?\?\s+\.mypy_cache[\\/]',
    '^\?\?\s+\.ruff_cache[\\/]',
    '^\?\?\s+\.venv[\\/]',
    '^\?\?\s+venv[\\/]',
    '^\?\?\s+\.coverage$',
    '^\?\?\s+coverage\.xml$'
  )

  $bad = @()
  foreach($l in $lines){
    $ok = $false
    foreach($pat in $allow){
      if($l -match $pat){ $ok = $true; break }
    }
    if(-not $ok){ $bad += $l }
  }

  if($bad.Count -gt 0){
    Write-Host "DIRTY_TREE (non-generated changes):"
    $bad | ForEach-Object { Write-Host $_ }
    Fail "Refusing to release from a dirty working tree (non-generated). Commit or restore changes."
  }
}

function Parse-HardenSummary([string[]]$lines){
  $hit = $lines | Where-Object { $_ -like "HARDEN_SUMMARY_JSON=*" } | Select-Object -Last 1
  if(-not $hit){ Fail "HARDEN_SUMMARY_JSON not found. harden_wavekit output changed or failed." }
  $json = $hit.Substring("HARDEN_SUMMARY_JSON=".Length)
  try { return ($json | ConvertFrom-Json) } catch { Fail "Failed to parse HARDEN_SUMMARY_JSON as JSON." }
}

Write-Host "============================================================"
Write-Host "WAVEKIT RELEASE GATE (NO API/TOKENS)"
Write-Host "============================================================"
Write-Host ("Repo: {0}" -f (Get-Location))
Write-Host ("ProductId: {0}" -f $ProductId)
Write-Host ("CanonicalCsv: {0}" -f $CanonicalCsv)
Write-Host ("OutRoot: {0}" -f $OutRoot)
Write-Host ""

Write-Host "==> git clean guard"
Require-CleanGit

Write-Host "==> pytest"
pytest -q

Write-Host ""
Write-Host "==> doctor"
python -m synapse.infra.doctor

Write-Host ""
Write-Host "==> wave --apply"
python -m synapse.cli wave --product-id $ProductId --apply --out-root $OutRoot --canonical-csv $CanonicalCsv

Write-Host ""
Write-Host "==> harden_wavekit (STRICT)"
$hardenOut = & python scripts\harden_wavekit.py (Join-Path $OutRoot $ProductId)
$hardenOut | ForEach-Object { Write-Host $_ }

$summary = Parse-HardenSummary $hardenOut
if($summary.product_id -ne $ProductId){ Fail ("ProductId mismatch: summary={0} expected={1}" -f $summary.product_id, $ProductId) }

$zipPath = ("{0}\wave_kit_{1}.zip" -f $OutRoot, $ProductId)
$shaPath = ("{0}\wave_kit_{1}.sha256" -f $OutRoot, $ProductId)
if(-not (Test-Path $zipPath)){ Fail ("Missing zip: {0}" -f $zipPath) }
if(-not (Test-Path $shaPath)){ Fail ("Missing sha sidecar: {0}" -f $shaPath) }

Write-Host ""
Write-Host "==> seal release dir"
$sha = (git rev-parse --short=12 HEAD).Trim()
$rel = "exports\releases\$ProductId\$sha"
New-Item -ItemType Directory -Force $rel | Out-Null

Copy-Item $zipPath, $shaPath $rel -Force

# Provenance meta
$meta = @{
  git_sha = $sha
  product_id = $ProductId
  canonical_csv = $CanonicalCsv
  out_root = $OutRoot
  harden = $summary
  ts_utc = (Get-Date).ToUniversalTime().ToString("o")
}
$metaPath = Join-Path $rel "release_meta.json"
($meta | ConvertTo-Json -Depth 10) | Out-File -FilePath $metaPath -Encoding utf8

Write-Host ("OK RELEASE_DIR={0}" -f $rel)
Write-Host ("OK FILE={0}" -f (Join-Path $rel ("wave_kit_{0}.zip" -f $ProductId)))
Write-Host ("OK SHA ={0}" -f (Join-Path $rel ("wave_kit_{0}.sha256" -f $ProductId)))
Write-Host ("OK META={0}" -f $metaPath)
