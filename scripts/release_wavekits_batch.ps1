param(
  [string]$DumpJson = "data\evidence\launch_candidates_dropi_dump_f1_v3.json",
  [string]$OutRoot  = "exports"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# =========================
# WAVEKIT BATCH RELEASE (NO API/TOKENS)
# dump.json -> shortlist.csv -> canonical_products.csv -> QUALITY GATE -> wavekits -> shopify export v2 -> enrich -> harden -> release
# =========================

function Stop-Release([string]$Message) { throw $Message }

function Test-GitCleanGuard {
  $s = (git status --porcelain) 2>$null
  if ($LASTEXITCODE -ne 0) { Stop-Release "GIT not available / not a repo." }

  $lines = @()
  if ($s) { $lines = @($s -split "`n" | ForEach-Object { $_.TrimEnd() }) }

  # Force array ALWAYS (StrictMode-safe)
  $bad = @($lines | Where-Object {
    $_ -and
    ($_ -notmatch "^\?\?\s+exports[/\\]") -and
    ($_ -notmatch "^\?\?\s+_extracted[/\\]") -and
    ($_ -notmatch "^\?\?\s+_extracted_proof[/\\]") -and
    ($_ -notmatch "^\?\?\s+\.env$")
  })

  if ($bad.Count -gt 0) {
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
  return @($ids)
}

function Assert-ShopifyBodyNonEmpty([string]$ShopifyCsvPath) {
  if (-not (Test-Path $ShopifyCsvPath)) { Stop-Release ("Missing Shopify CSV: {0}" -f $ShopifyCsvPath) }

  python -c "import csv,sys; p=sys.argv[1]; r=list(csv.DictReader(open(p,encoding='utf-8',newline=''))); assert r, 'NO_ROWS'; b=(r[0].get('Body (HTML)') or '').strip(); assert b, 'EMPTY_BODY_HTML'; print('shopify_body: OK (len=%d)'%len(b))" $ShopifyCsvPath
  if ($LASTEXITCODE -ne 0) { Stop-Release ("Shopify Body (HTML) still empty after enrich: {0}" -f $ShopifyCsvPath) }
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

$sha = (git rev-parse --short=12 HEAD).Trim()
$batchDir = "exports\releases\_batch\$sha"
New-Item -ItemType Directory -Force $batchDir | Out-Null

# -------------------------------------------------------------
# NEW: sanitize dump evidence into batchDir (no side effects)
# -------------------------------------------------------------
Write-Host ""
Write-Host "==> sanitize dump evidence (block placeholder images)"
$DumpSanitized = Join-Path $batchDir "dump_sanitized.json"
python scripts\sanitize_evidence_images.py $DumpJson --output $DumpSanitized --replace-with null
if ($LASTEXITCODE -ne 0) { Stop-Release "sanitize_evidence_images failed." }

$SanitizeReport = ($DumpSanitized + ".sanitize_report.json")
if (-not (Test-Path $DumpSanitized)) { Stop-Release ("sanitize did not produce: {0}" -f $DumpSanitized) }

Write-Host ("- dump_sanitized: {0}" -f $DumpSanitized)
if (Test-Path $SanitizeReport) { Write-Host ("- sanitize_report: {0}" -f $SanitizeReport) }

# Use sanitized dump from here onward
$DumpJsonUsed = $DumpSanitized

$ShortlistCsv = Join-Path $batchDir "shortlist.csv"
$CanonicalOut = Join-Path $batchDir "canonical_products.csv"
# IMPORTANT: builder v2 writes THIS report name (no ".csv" in filename)
$canonReport  = Join-Path $batchDir "canonical_products.report.json"

Write-Host ""
Write-Host "==> autopick shortlist (from Dropi dump)"
python scripts\dropi_autopick.py --dump $DumpJsonUsed --out $ShortlistCsv --n 20
if ($LASTEXITCODE -ne 0) { Stop-Release "dropi_autopick failed." }
if (-not (Test-Path $ShortlistCsv)) { Stop-Release ("shortlist not produced: {0}" -f $ShortlistCsv) }

Write-Host ""
Write-Host "==> build canonical (from Dropi evidence) [v2]"
python scripts\build_canonical_from_dropi_v2.py --shortlist $ShortlistCsv --dump $DumpJsonUsed --out $CanonicalOut
if ($LASTEXITCODE -ne 0) { Stop-Release "build_canonical_from_dropi_v2 failed." }
if (-not (Test-Path $CanonicalOut)) { Stop-Release ("canonical not produced: {0}" -f $CanonicalOut) }

$ids = @(Get-ProductIdsFromCanonical $CanonicalOut)

Write-Host ""
Write-Host "==> canonical quality gate"
if (-not (Test-Path $canonReport)) { Stop-Release ("Missing canonical report: {0}" -f $canonReport) }

if ($ids.Count -eq 1 -and $ids[0] -eq "seed") {
  python scripts\canonical_quality_gate.py --report $canonReport --allow-seed
} else {
  python scripts\canonical_quality_gate.py --report $canonReport
}
if ($LASTEXITCODE -ne 0) { Stop-Release "canonical quality gate failed (evidence too thin)." }

Write-Host ""
Write-Host ("==> batch wavekits: {0} products" -f $ids.Count)

$index = @()

foreach ($prodId in $ids) {
  Write-Host ""
  Write-Host ("--- PRODUCT {0} ---" -f $prodId)

  $kitDir = Join-Path $OutRoot $prodId
  $shopCsv = Join-Path $kitDir "shopify\shopify_products.csv"

  Write-Host "==> wave --apply"
  python -m synapse.cli wave --product-id $prodId --apply --out-root $OutRoot --canonical-csv $CanonicalOut
  if ($LASTEXITCODE -ne 0) { Stop-Release ("wave failed for product_id={0}" -f $prodId) }

  Write-Host "==> export shopify csv (v2 schema)"
  python scripts\shopify_export_from_canonical.py --kit-dir $kitDir --canonical-csv $CanonicalOut
  if ($LASTEXITCODE -ne 0) { Stop-Release ("shopify_export_from_canonical failed for product_id={0}" -f $prodId) }

  Write-Host "==> enrich shopify csv"
  python scripts\enrich_shopify_csv.py --kit-dir $kitDir --canonical-csv $CanonicalOut
  if ($LASTEXITCODE -ne 0) { Stop-Release ("enrich_shopify_csv failed for product_id={0}" -f $prodId) }

  Write-Host "==> assert shopify body non-empty"
  Assert-ShopifyBodyNonEmpty $shopCsv

  Write-Host "==> harden_wavekit (STRICT)"
  $hardenOut = & python scripts\harden_wavekit.py $kitDir
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
    git_sha           = $sha
    product_id        = $prodId
    dump_json_input   = $DumpJson
    dump_json_used    = $DumpJsonUsed
    sanitize_report   = $SanitizeReport
    shortlist_csv     = $ShortlistCsv
    canonical_csv     = $CanonicalOut
    canonical_report  = $canonReport
    out_root          = $OutRoot
    harden            = $summary
    ts_utc            = (Get-Date).ToUniversalTime().ToString("o")
  }

  $metaPath = Join-Path $rel "release_meta.json"
  ($meta | ConvertTo-Json -Depth 10) | Out-File -FilePath $metaPath -Encoding utf8

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
Write-Host ("CANON_RPT:   {0}" -f $canonReport)
Write-Host ("DUMP_USED:   {0}" -f $DumpJsonUsed)
if (Test-Path $SanitizeReport) { Write-Host ("SAN_RPT:     {0}" -f $SanitizeReport) }
