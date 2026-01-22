Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# =========================
# BATCH RELEASE (NO API/TOKENS)
# =========================
$CanonicalOut = "data\catalog\canonical_products.csv"
$ShortlistCsv = "data\launch\shortlist_dropi_f1.csv"
$DumpJson     = "data\evidence\launch_candidates_dropi_dump_f1_v2.json"
$OutRoot      = "exports"

function Fail([string]$msg){ throw $msg }

function Require-CleanGit(){
  $s = (git status --porcelain) 2>$null
  if($LASTEXITCODE -ne 0){ Fail "GIT not available / not a repo." }

  # Ignore generated outputs
  $lines = @()
  if($s){ $lines = $s -split "`n" | ForEach-Object { $_.TrimEnd() } }

  $bad = $lines | Where-Object {
    $_ -and
    ($_ -notmatch "^\?\?\s+exports[/\\]releases[/\\]") -and
    ($_ -notmatch "^\?\?\s+exports[/\\]wave_kit_.*\.(zip|sha256)$") -and
    ($_ -notmatch "^\?\?\s+exports[/\\]p\d+[/\\]") -and
    ($_ -notmatch "^\?\?\s+exports[/\\]seed[/\\]")
  }

  if($bad -and $bad.Count -gt 0){
    Write-Host "DIRTY_TREE (non-generated changes):"
    $bad | ForEach-Object { Write-Host $_ }
    Fail "Refusing to release from a dirty working tree (non-generated). Commit or restore changes."
  }
}

function Read-ProductIds([string]$csvPath){
  if(-not (Test-Path $csvPath)){ Fail ("Missing canonical CSV: {0}" -f $csvPath) }
  $ids = @()
  $rows = Import-Csv $csvPath
  foreach($r in $rows){
    $pid = ($r.product_id).ToString().Trim()
    if($pid){ $ids += $pid }
  }
  if(-not $ids -or $ids.Count -eq 0){ Fail "No product_id rows found in canonical CSV." }
  return $ids
}

Write-Host "============================================================"
Write-Host "WAVEKIT BATCH RELEASE (NO API/TOKENS)"
Write-Host "============================================================"
Write-Host ("Repo: {0}" -f (Get-Location))
Write-Host ("Shortlist: {0}" -f $ShortlistCsv)
Write-Host ("Dump: {0}" -f $DumpJson)
Write-Host ("CanonicalOut: {0}" -f $CanonicalOut)
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
Write-Host "==> build canonical (from Dropi evidence)"
python scripts\build_canonical_from_dropi.py --shortlist $ShortlistCsv --dump $DumpJson --out $CanonicalOut

$ids = Read-ProductIds $CanonicalOut
Write-Host ""
Write-Host ("==> batch wavekits: {0} products" -f $ids.Count)

$sha = (git rev-parse --short=12 HEAD).Trim()
$batchDir = "exports\releases\_batch\$sha"
New-Item -ItemType Directory -Force $batchDir | Out-Null

$index = @()

foreach($pid in $ids){
  Write-Host ""
  Write-Host ("--- PRODUCT {0} ---" -f $pid)

  Write-Host "==> wave --apply"
  python -m synapse.cli wave --product-id $pid --apply --out-root $OutRoot --canonical-csv $CanonicalOut

  Write-Host "==> harden_wavekit (STRICT)"
  $hardenOut = & python scripts\harden_wavekit.py (Join-Path $OutRoot $pid)
  $hardenOut | ForEach-Object { Write-Host $_ }

  $hit = $hardenOut | Where-Object { $_ -like "HARDEN_SUMMARY_JSON=*" } | Select-Object -Last 1
  if(-not $hit){ Fail "HARDEN_SUMMARY_JSON not found. harden_wavekit output changed or failed." }
  $json = $hit.Substring("HARDEN_SUMMARY_JSON=".Length)
  $summary = $json | ConvertFrom-Json

  if($summary.product_id -ne $pid){ Fail ("ProductId mismatch: summary={0} expected={1}" -f $summary.product_id, $pid) }

  $rel = "exports\releases\$pid\$sha"
  New-Item -ItemType Directory -Force $rel | Out-Null

  $zipPath = ("{0}\wave_kit_{1}.zip" -f $OutRoot, $pid)
  $shaPath = ("{0}\wave_kit_{1}.sha256" -f $OutRoot, $pid)

  if(-not (Test-Path $zipPath)){ Fail ("Missing zip: {0}" -f $zipPath) }
  if(-not (Test-Path $shaPath)){ Fail ("Missing sha sidecar: {0}" -f $shaPath) }

  Copy-Item $zipPath, $shaPath $rel -Force

  $meta = @{
    git_sha = $sha
    product_id = $pid
    canonical_csv = $CanonicalOut
    out_root = $OutRoot
    harden = $summary
    ts_utc = (Get-Date).ToUniversalTime().ToString("o")
  }
  $metaPath = Join-Path $rel "release_meta.json"
  ($meta | ConvertTo-Json -Depth 8) | Out-File -FilePath $metaPath -Encoding utf8

  $index += @{
    product_id = $pid
    release_dir = $rel
    zip = (Join-Path $rel ("wave_kit_{0}.zip" -f $pid))
    sha256 = (Join-Path $rel ("wave_kit_{0}.sha256" -f $pid))
    meta = $metaPath
  }
}

$indexPath = Join-Path $batchDir "index.json"
($index | ConvertTo-Json -Depth 6) | Out-File -FilePath $indexPath -Encoding utf8

Write-Host ""
Write-Host "============================================================"
Write-Host "BATCH RELEASE DONE"
Write-Host "============================================================"
Write-Host ("BATCH_INDEX: {0}" -f $indexPath)
Write-Host "COPY THIS (NOT A COMMAND):"
Write-Host ("GIT_SHA:     {0}" -f $sha)
Write-Host ("INDEX_JSON:  {0}" -f $indexPath)
