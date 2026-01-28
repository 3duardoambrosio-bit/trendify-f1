param(
  [Parameter(Mandatory=$true)]
  [ValidateNotNullOrEmpty()]
  [string]$DumpJson,

  [Parameter(Mandatory=$false)]
  [ValidateSet("demo","prod")]
  [string]$Mode = "demo"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "=== RELEASE OFFLINE (BATCH -> MERGE -> CONTRACT) ===" -ForegroundColor Cyan
Write-Host ("Dump: " + $DumpJson)
Write-Host ("Mode: " + $Mode)

if (-not (Test-Path $DumpJson)) {
  throw ("NO_EXISTE DumpJson: " + $DumpJson)
}

# 1) corre batch release existente (si truena, aquí muere)
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

# 4) contract gate (demo/prod)
$failOnWarn = $false
if ($Mode -eq "prod") { $failOnWarn = $true }  # prod = más estricto por default

if ($failOnWarn) {
  python .\scripts\shopify_contract_gate.py "$csv" --mode $Mode --fail-on-warn
} else {
  python .\scripts\shopify_contract_gate.py "$csv" --mode $Mode
}
if ($LASTEXITCODE -ne 0) { throw "shopify_contract_gate.py falló (exit=$LASTEXITCODE)" }

Write-Host "OK: pipeline offline validado." -ForegroundColor Green
Write-Host ("CSV listo: " + $csv)
