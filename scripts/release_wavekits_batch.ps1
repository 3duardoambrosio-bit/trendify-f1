Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# =========================
# WAVEKIT BATCH RELEASE (NO API/TOKENS)
# Dropi selection happens automatically from dump evidence:
#   dump.json -> shortlist.csv -> canonical_products.csv -> wavekits
# =========================

$DumpJson = "data\evidence\launch_candidates_dropi_dump_f1_v2.json"
$OutRoot  = "exports"

function Stop-Release([string]$Message) { throw $Message }

function Test-GitCleanGuard {
  $s = (git status --porcelain) 2>$null
  if ($LASTEXITCODE -ne 0) { Stop-Release "GIT not available / not a repo." }

  $lines = @()
  if ($s) { $lines = $s -split "`n" | ForEach-Object { $_.TrimEnd() } }

  # If .gitignore is doing its job, exports won't show. Still keep a safety net.
  $bad = $lines | Where-Object {
    $_ -and
    ($_ -notmatch "^\?\?\s+exports[/\\]") -and
    ($_ -notmatch "^\?\?\s+_extracted[/\\]") -and
    ($_ -notmatch "^\?\?\s+\.env$")
  }

  if ($bad -and $bad.Count -gt 0) {
    Write-Host "DIRTY_TREE (non-generated changes):"
    $bad | ForEach-Object { Write-Host $_ }
    Stop-Release "Refusing to release from a dirty working tree (non-generated). Commit or restore changes."
  }
}

function Get-ProductIdsFromCanonical([string]$CsvPath) {
  if (-not (Test-Path $CsvPath)) { Stop-Release ("Missing canonical CSV: {0}" -f $CsvPath) }

  $ids = @()
  $rows = Import-Csv $CsvPath
  foreach ($r in $rows) {
    $prodId = ($r.product_id).ToString().Trim()
    if ($prodId) { $ids += $prodId }
  }

  if (-not $ids -or $ids.Count -eq 0) { Stop-Release "No product_id rows found in canonical CSV." }

  # Force array output even for single element (StrictMode safe)
  return @($ids)
}

Write-Host "============================================================"
Write-Host "WAVEKIT BATCH RELEASE (NO API/TOKENS)"
Write-Host "============================================================"
Write-Host ("Repo: {0}" -f (Get-Location))
Write-Host ("Dump: {0}" -f $DumpJson)
Write-Host ("OutRoot: {0}" -f $OutRoot)
Write-Host ""

Write-Host "==> git clean guard"
Test-GitCleanGuard

Write-Host "==> pytest"
pytest -q
if ($LASTEXITCODE -ne 0) { Stop-Release "pytest failed." }

Write-Host ""
Write-Host "==> doctor"
python -m synapse.infra.doctor
if ($LASTEXITCODE -ne 0) { Stop-Release "doctor failed." }

if (-not (Test-Path $DumpJson)) {
  Stop-Release ("Missing dump JSON evidence: {0}" -f $DumpJson)
}

# Batch id = current git sha
$sha = (git rev-parse --short=12 HEAD).Trim()
$batchDir = "exports\releases\_batch\$sha"
New-Item -ItemType Directory -Force $batchDir | Out-Null

# Everything generated stays inside exports (ignored)
$ShortlistCsv = Join-Path $batchDir "shortlist.csv"
$CanonicalOut = Join-Path $batchDir "canonical_products.csv"

Write-Host ""
Write-Host "==> autopick shortlist (from Dropi dump)"
python scripts\dropi_autopick.py --dump $DumpJson --out $ShortlistCsv --n 20
if ($LASTEXITCODE -ne 0) { Stop-Release "dropi_autopick failed." }
if (-not (Test-Path $ShortlistCsv)) { Stop-Release ("shortlist not produced: {0}" -f $ShortlistCsv) }

Write-Host ""
Write-Host "==> build canonical (from Dropi evidence)"
python scripts\build_canonical_from_dropi.py --shortlist $ShortlistCsv --dump $DumpJson --out $CanonicalOut
if ($LASTEXITCODE -ne 0) { Stop-Release "build_canonical_from_dropi failed." }
if (-not (Test-Path $CanonicalOut)) { Stop-Release ("canonical not produced: {0}" -f $CanonicalOut) }

$ids = @(Get-ProductIdsFromCanonical $CanonicalOut)

Write-Host ""
Write-Host ("==> batch wavekits: {0} products" -f $ids.Count)

$index = @()

foreach ($prodId in $ids) {
  Write-Host ""
  Write-Host ("--- PRODUCT {0} ---" -f $prodId)

  Write-Host "==> wave --apply"
  python -m synapse.cli wave --product-id $prodId --apply --out-root $OutRoot --canonical-csv $CanonicalOut
  if ($LASTEXITCODE -ne 0) { Stop-Release ("wave failed for product_id={0}" -f $prodId) }

  Write-Host "==> harden_wavekit (STRICT)"
  $hardenOut = & python scripts\harden_wavekit.py (Join-Path $OutRoot $prodId)
  $hardenOut | ForEach-Object { Write-Host $_ }

  $hit = $hardenOut | Where-Object { $_ -like "HARDEN_SUMMARY_JSON=*" } | Select-Object -Last 1
  if (-not $hit) { Stop-Release "HARDEN_SUMMARY_JSON not found. harden_wavekit output changed or failed." }

  $json = $hit.Substring("HARDEN_SUMMARY_JSON=".Length)
  try { $summary = $json | ConvertFrom-Json } catch { Stop-Release "Failed to parse HARDEN_SUMMARY_JSON as JSON." }

  if ($summary.product_id -ne $prodId) {
    Stop-Release ("ProductId mismatch: summary={0} expected={1}" -f $summary.product_id, $prodId)
  }

  $rel = "exports\releases\$prodId\$sha"
  New-Item -ItemType Directory -Force $rel | Out-Null

  $zipPath = ("{0}\wave_kit_{1}.zip" -f $OutRoot, $prodId)
  $shaPath = ("{0}\wave_kit_{1}.sha256" -f $OutRoot, $prodId)

  if (-not (Test-Path $zipPath)) { Stop-Release ("Missing zip: {0}" -f $zipPath) }
  if (-not (Test-Path $shaPath)) { Stop-Release ("Missing sha sidecar: {0}" -f $shaPath) }

  Copy-Item $zipPath, $shaPath $rel -Force

  $meta = @{
    git_sha       = $sha
    product_id    = $prodId
    dump_json     = $DumpJson
    shortlist_csv = $ShortlistCsv
    canonical_csv = $CanonicalOut
    out_root      = $OutRoot
    harden        = $summary
    ts_utc        = (Get-Date).ToUniversalTime().ToString("o")
  }

  $metaPath = Join-Path $rel "release_meta.json"
  ($meta | ConvertTo-Json -Depth 8) | Out-File -FilePath $metaPath -Encoding utf8

  $index += @{
    product_id  = $prodId
    release_dir = $rel
    zip         = (Join-Path $rel ("wave_kit_{0}.zip" -f $prodId))
    sha256      = (Join-Path $rel ("wave_kit_{0}.sha256" -f $prodId))
    meta        = $metaPath
  }
}

$indexPath = Join-Path $batchDir "index.json"
($index | ConvertTo-Json -Depth 6) | Out-File -FilePath $indexPath -Encoding utf8

Write-Host ""
Write-Host "============================================================"
Write-Host "BATCH RELEASE DONE"
Write-Host "============================================================"
Write-Host ("BATCH_DIR:   {0}" -f $batchDir)
Write-Host ("BATCH_INDEX: {0}" -f $indexPath)
Write-Host "COPY THIS (NOT A COMMAND):"
Write-Host ("GIT_SHA:     {0}" -f $sha)
Write-Host ("INDEX_JSON:  {0}" -f $indexPath)
Write-Host ("SHORTLIST:   {0}" -f $ShortlistCsv)
Write-Host ("CANONICAL:   {0}" -f $CanonicalOut)