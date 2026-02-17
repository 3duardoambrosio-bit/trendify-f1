param([switch]$Strict)

$ErrorActionPreference="Stop"
Write-Host "=== CASHFLOW SANITY GATE (contract stub) ==="

$cfg = "config/finance/payment_methods.json"
"cashflow_cfg_exists=$([int]([bool](Test-Path $cfg)))"

if ($Strict -and -not (Test-Path $cfg)) {
  Write-Error "Missing required cashflow config: $cfg"
  exit 11
}

Write-Host "[PASS] Cashflow sanity contract OK"
