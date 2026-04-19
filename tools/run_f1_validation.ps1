param(
  [ValidateSet("status","burnin","bundle","both")]
  [string]$Mode = "status",

  [string]$BundleOutputRoot = "C:\Temp\synapse_segmented_burnin_audit",
  [int]$Iterations = 1,
  [string]$Secret = "shpss_test_secret"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path ".").Path
$burninSegmented = Join-Path $repo "tools\run_synthetic_burnin_segmented.ps1"
$auditBuilder = Join-Path $repo "tools\build_segmented_burnin_audit_bundle.ps1"

if (-not (Test-Path -LiteralPath $burninSegmented)) {
  throw "SEGMENTED_BURNIN_NOT_FOUND=$burninSegmented"
}
if (-not (Test-Path -LiteralPath $auditBuilder)) {
  throw "AUDIT_BUILDER_NOT_FOUND=$auditBuilder"
}

$head = (git rev-parse --short HEAD).Trim()
[string[]]$status = @(git status --short)
$status = @($status | Where-Object { $_ -and $_.Trim().Length -gt 0 })

Write-Host "MODE=$Mode"
Write-Host "HEAD=$head"
Write-Host "STATUS_DIRTY_COUNT=$($status.Count)"
Write-Host "LAST_COMMIT_BEGIN"
git log -1 --stat --oneline
Write-Host "LAST_COMMIT_END"

if ($Mode -eq "status") {
  exit 0
}

if ($Mode -eq "burnin" -or $Mode -eq "both") {
  Write-Host "BURNIN_SEGMENTED_START=1"
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $burninSegmented -Iterations $Iterations -OutputRoot (Join-Path $BundleOutputRoot "run_only") -Secret $Secret
  $burninExit = $LASTEXITCODE
  Write-Host "BURNIN_SEGMENTED_EXIT_CODE=$burninExit"
  if ($burninExit -ne 0) {
    throw "BURNIN_SEGMENTED_FAILED EXIT_CODE=$burninExit"
  }
}

if ($Mode -eq "bundle" -or $Mode -eq "both") {
  [string[]]$allowedDirty = @(
    "tools/build_segmented_burnin_audit_bundle.ps1",
    "tools/run_f1_validation.ps1"
  )
  $allowedDirtyArg = ($allowedDirty -join ",")

  Write-Host "AUDIT_BUNDLE_START=1"
  Write-Host "AUDIT_BUNDLE_ALLOWED_DIRTY_BEGIN"
  $allowedDirty | ForEach-Object { Write-Host $_ }
  Write-Host "AUDIT_BUNDLE_ALLOWED_DIRTY_END"

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $auditBuilder -OutputRoot $BundleOutputRoot -Iterations $Iterations -Secret $Secret -AllowedDirtyPaths $allowedDirtyArg
  $bundleExit = $LASTEXITCODE
  Write-Host "AUDIT_BUNDLE_EXIT_CODE=$bundleExit"
  if ($bundleExit -ne 0) {
    throw "AUDIT_BUNDLE_FAILED EXIT_CODE=$bundleExit"
  }
}

Write-Host "F1_VALIDATION_OK=1"
exit 0
