param(
  [Parameter(Mandatory=$true)]
  [ValidateNotNullOrEmpty()]
  [string]$DumpJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "=== RELEASE OFFLINE (BATCH -> MERGE -> CONTRACT) ===" -ForegroundColor Cyan
Write-Host ("Dump: " + $DumpJson)

if (-not (Test-Path $DumpJson)) {
  throw ("NO_EXISTE DumpJson: " + $DumpJson)
}

# 1) corre batch release existente (MISMO PROCESO => si truena, aquí muere)
& .\scripts\release_wavekits_batch.ps1 -DumpJson $DumpJson

# 2) encuentra batch más reciente
$latest = Get-ChildItem .\exports\releases\_batch -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $latest) { throw "No encontré exports\releases\_batch" }

$batchDir = $latest.FullName
Write-Host ("BATCH: " + $batchDir) -ForegroundColor Green

# 3) merge de shopify csvs
python .\scripts\merge_shopify_csvs.py --batch "$batchDir"
if ($LASTEXITCODE -ne 0) { throw "merge_shopify_csvs.py falló (exit=$LASTEXITCODE)" }

$csv = Join-Path $batchDir "shopify_import_all.csv"
if (-not (Test-Path $csv)) { throw ("No se creó " + $csv) }

# 4) contract gate
python .\scripts\shopify_contract_gate.py "$csv"
if ($LASTEXITCODE -ne 0) { throw "shopify_contract_gate.py falló (exit=$LASTEXITCODE)" }

Write-Host "OK: pipeline offline validado." -ForegroundColor Green
Write-Host ("CSV listo: " + $csv)
