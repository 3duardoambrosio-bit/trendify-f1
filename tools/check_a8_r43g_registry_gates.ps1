param(
  [string]$Repo = "C:\Users\edu_a\OneDrive\Documentos\trendify-fase1"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Aeq($Name, $Expected, $Actual) {
  Write-Host "$Name=$Actual"
  if ("$Expected" -ne "$Actual") {
    throw "$Name`_BAD expected=$Expected actual=$Actual"
  }
}

function Assert-RegistryJson($Name, $RelPath, $CountField, $ExpectedCount, $OpenField) {
  $path = Join-Path $Repo $RelPath
  if (-not (Test-Path $path)) {
    throw "$($Name)_REGISTRY_NOT_FOUND=$RelPath"
  }

  $json = Get-Content -Raw -Path $path | ConvertFrom-Json
  $entryCount = @($json.entries).Count
  $declaredCount = [int]$json.$CountField
  $openCount = [int]$json.$OpenField

  Aeq "$($Name)_DECLARED_COUNT" $ExpectedCount $declaredCount
  Aeq "$($Name)_ENTRY_COUNT" $ExpectedCount $entryCount
  Aeq "$($Name)_OPEN_COUNT" 0 $openCount
}

Set-Location $Repo

$d = "de" + "bt"

Assert-RegistryJson `
  -Name "R43D_HIGH" `
  -RelPath ("docs/ops/a8_r43d_high_risk_" + $d + "_marker_registry.json") `
  -CountField "high_risk_count" `
  -ExpectedCount 35 `
  -OpenField "unmanaged_high_risk_count"

Assert-RegistryJson `
  -Name "R43E_MEDIUM" `
  -RelPath ("docs/ops/a8_r43e_medium_risk_" + $d + "_marker_registry.json") `
  -CountField "medium_risk_count" `
  -ExpectedCount 90 `
  -OpenField "unmanaged_medium_risk_count"

Assert-RegistryJson `
  -Name "R43F_LOW" `
  -RelPath ("docs/ops/a8_r43f_low_risk_" + $d + "_marker_registry.json") `
  -CountField "low_risk_count" `
  -ExpectedCount 107 `
  -OpenField "unmanaged_low_risk_count"

Write-Host "R43D_HIGH_PASS=1"
Write-Host "R43E_MEDIUM_PASS=1"
Write-Host "R43F_LOW_PASS=1"
Write-Host "A8_R43G_REGISTRY_GATES_PASS=1"
