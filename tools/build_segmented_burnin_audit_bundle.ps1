param(
  [string]$OutputRoot = "C:\Temp\synapse_segmented_burnin_audit",
  [int]$Iterations = 1,
  [string]$Secret = "shpss_test_secret",
  [string[]]$AllowedDirtyPaths = @()
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function New-Dir([string]$Path) {
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Normalize-DirtyList([string[]]$Items) {
  [string[]]$normalized = @()

  foreach ($entry in $Items) {
    if ($null -eq $entry) { continue }
    $parts = @(
      ($entry.ToString() -split '[,\s]+' | Where-Object { $_ -and $_.Trim().Length -gt 0 })
    )
    foreach ($part in $parts) {
      $normalized += $part.Trim()
    }
  }

  return @($normalized | Select-Object -Unique | Sort-Object)
}

$repo = (Resolve-Path ".").Path
$segmented = Join-Path $repo "tools\run_synthetic_burnin_segmented.ps1"

if (-not (Test-Path -LiteralPath $segmented)) {
  throw "SEGMENTED_LAUNCHER_NOT_FOUND=$segmented"
}

$head = (git rev-parse --short HEAD).Trim()
[string[]]$status = @(git status --short)
$status = @($status | Where-Object { $_ -and $_.Trim().Length -gt 0 })

$dirtyPaths = @($status | ForEach-Object { $_.Substring(3).Trim() } | Sort-Object)
$allowedDirtyNormalized = Normalize-DirtyList -Items $AllowedDirtyPaths

$unexpectedDirty = @($dirtyPaths | Where-Object { $_ -notin $allowedDirtyNormalized })
$missingAllowedDirty = @($allowedDirtyNormalized | Where-Object { $_ -notin $dirtyPaths })

$treeClean = [int]($status.Count -eq 0)
$allowedDirtyExact = [int](($allowedDirtyNormalized.Count -gt 0) -and ($unexpectedDirty.Count -eq 0) -and ($missingAllowedDirty.Count -eq 0) -and ($dirtyPaths.Count -eq $allowedDirtyNormalized.Count))

Write-Host "INNER_STATUS_DIRTY_COUNT=$($status.Count)"
Write-Host ("INNER_DIRTY_PATHS={0}" -f ($dirtyPaths -join ","))
Write-Host ("INNER_ALLOWED_DIRTY={0}" -f ($allowedDirtyNormalized -join ","))
Write-Host "INNER_TREE_CLEAN=$treeClean"
Write-Host "INNER_ALLOWED_DIRTY_EXACT=$allowedDirtyExact"

if (($treeClean -ne 1) -and ($allowedDirtyExact -ne 1)) {
  throw "TREE_NOT_CLEAN=$($status.Count)"
}

Remove-Item -LiteralPath $OutputRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Dir $OutputRoot

$runRoot = Join-Path $OutputRoot "run"
$evidenceRoot = Join-Path $OutputRoot "evidence"
New-Dir $runRoot
New-Dir $evidenceRoot

$summaryPath = Join-Path $runRoot "summary.segmented.json"
$stdoutLog = Join-Path $evidenceRoot "segmented_launcher.stdout.log"
$stderrLog = Join-Path $evidenceRoot "segmented_launcher.stderr.log"

$gitHeadFile = Join-Path $evidenceRoot "git_head.txt"
$gitStatusFile = Join-Path $evidenceRoot "git_status.txt"
$gitLogFile = Join-Path $evidenceRoot "git_log_1.txt"

(git rev-parse HEAD) | Set-Content -LiteralPath $gitHeadFile -Encoding UTF8
(git status --short --branch) | Set-Content -LiteralPath $gitStatusFile -Encoding UTF8
(git log -1 --stat) | Set-Content -LiteralPath $gitLogFile -Encoding UTF8

Remove-Item -LiteralPath $stdoutLog -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $stderrLog -Force -ErrorAction SilentlyContinue

[object[]]$captured = @(
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $segmented -Iterations $Iterations -OutputRoot $runRoot -Secret $Secret *>&1
)
$exitCode = $LASTEXITCODE

if ($captured.Count -gt 0) {
  $captured | Tee-Object -FilePath $stdoutLog | Out-Host
}
else {
  "" | Set-Content -LiteralPath $stdoutLog -Encoding UTF8
}

Write-Host "SEGMENTED_EXIT_CODE=$exitCode"
Write-Host "RUN_ROOT=$runRoot"
Write-Host "SUMMARY_EXISTS=$([int](Test-Path -LiteralPath $summaryPath))"

if (-not (Test-Path -LiteralPath $summaryPath)) {
  throw "SUMMARY_NOT_FOUND=$summaryPath"
}

$summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json

Write-Host "SUMMARY_TOTAL_STEPS=$($summary.total_steps)"
Write-Host "SUMMARY_PASSED_STEPS=$($summary.passed_steps)"
Write-Host "SUMMARY_FAILED_STEPS=$($summary.failed_steps)"
Write-Host "SUMMARY_OVERALL=$($summary.overall)"

if ($exitCode -ne 0) {
  throw "SEGMENTED_FAILED EXIT_CODE=$exitCode"
}
if ([int]$summary.total_steps -ne 7) {
  throw "SUMMARY_TOTAL_STEPS_UNEXPECTED=$($summary.total_steps)"
}
if ([int]$summary.failed_steps -ne 0) {
  throw "SUMMARY_FAILED_STEPS_UNEXPECTED=$($summary.failed_steps)"
}
if ([string]$summary.overall -ne "PASS") {
  throw "SUMMARY_OVERALL_UNEXPECTED=$($summary.overall)"
}

$zipPath = Join-Path $OutputRoot ("synapse_segmented_burnin_audit_" + $head + ".zip")
Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue

$zipSources = @($runRoot, $evidenceRoot)
Write-Host ("ZIP_SOURCES={0}" -f ($zipSources -join ";"))

Compress-Archive -Path $zipSources -DestinationPath $zipPath -CompressionLevel Optimal -Force

$zipExists = [int](Test-Path -LiteralPath $zipPath)
$zipSizeBytes = if ($zipExists -eq 1) { (Get-Item -LiteralPath $zipPath).Length } else { 0 }

Write-Host "ZIP_EXISTS=$zipExists"
Write-Host "ZIP_SIZE_BYTES=$zipSizeBytes"
Write-Host "ZIP_PATH=$zipPath"
Write-Host ('OPEN_ZIP_CMD=explorer.exe /select,"{0}"' -f $zipPath)

if ($zipExists -ne 1) {
  throw "ZIP_NOT_CREATED"
}
if ($zipSizeBytes -le 0) {
  throw "ZIP_EMPTY"
}

Write-Host "AUDIT_BUNDLE_OK=1"
