param(
  [int]$Iterations = 1,
  [string]$OutputRoot = "C:\Temp\synapse_burnin_segmented",
  [string]$Secret = "shpss_test_secret"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function New-Dir([string]$Path) {
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

$repo = (Resolve-Path ".").Path
$harness = Join-Path $repo "tools\run_synthetic_burnin.ps1"

if (-not (Test-Path -LiteralPath $harness)) {
  throw "HARNESS_NOT_FOUND=$harness"
}

Remove-Item -LiteralPath $OutputRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Dir $OutputRoot

$segments = @(
  [pscustomobject]@{
    Name = "segment_01_02"
    Steps = @("01_meta_pipeline_safe_client", "02_buyer")
  },
  [pscustomobject]@{
    Name = "segment_03_04"
    Steps = @("03_ops_tick", "04_shopify_writer")
  },
  [pscustomobject]@{
    Name = "segment_05_07"
    Steps = @("05_webhook_fixture_runner", "06_webhook_pytests", "07_refund_paths")
  }
)

$segmentResults = New-Object System.Collections.Generic.List[object]
$allStepResults = New-Object System.Collections.Generic.List[object]

foreach ($segment in $segments) {
  $segmentOut = Join-Path $OutputRoot $segment.Name
  $segmentSummary = Join-Path $segmentOut "summary.json"
  $segmentStdout = Join-Path $segmentOut "segment.stdout.log"
  $segmentStderr = Join-Path $segmentOut "segment.stderr.log"

  Remove-Item -LiteralPath $segmentOut -Recurse -Force -ErrorAction SilentlyContinue
  New-Dir $segmentOut

  $includeStepsArg = ($segment.Steps -join ",")

  Write-Host ""
  Write-Host "════════════════════════════════════════════════════════════"
  Write-Host ("SEGMENT_START={0}" -f $segment.Name)
  Write-Host ("SEGMENT_STEPS={0}" -f $includeStepsArg)
  Write-Host ("SEGMENT_STDOUT={0}" -f $segmentStdout)
  Write-Host ("SEGMENT_STDERR={0}" -f $segmentStderr)
  Write-Host "════════════════════════════════════════════════════════════"

  Remove-Item -LiteralPath $segmentStdout -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $segmentStderr -Force -ErrorAction SilentlyContinue

  $argList = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $harness,
    "-Iterations", $Iterations.ToString(),
    "-OutputRoot", $segmentOut,
    "-Secret", $Secret,
    "-IncludeSteps", $includeStepsArg
  )

  $proc = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList $argList `
    -RedirectStandardOutput $segmentStdout `
    -RedirectStandardError $segmentStderr `
    -Wait `
    -PassThru

  $segmentExit = $proc.ExitCode
  $summaryExists = [int](Test-Path -LiteralPath $segmentSummary)

  Write-Host "SEGMENT_EXIT_CODE=$segmentExit"
  Write-Host "SEGMENT_SUMMARY_EXISTS=$summaryExists"
  Write-Host "SEGMENT_SUMMARY_PATH=$segmentSummary"

  if (Test-Path -LiteralPath $segmentStdout) {
    Write-Host "SEGMENT_STDOUT_TAIL_BEGIN"
    Get-Content -LiteralPath $segmentStdout -Tail 120
    Write-Host "SEGMENT_STDOUT_TAIL_END"
  }

  if (Test-Path -LiteralPath $segmentStderr) {
    $stderrText = Get-Content -LiteralPath $segmentStderr -Raw
    if (($null -ne $stderrText) -and ($stderrText.Trim().Length -gt 0)) {
      Write-Host "SEGMENT_STDERR_TAIL_BEGIN"
      Get-Content -LiteralPath $segmentStderr -Tail 120
      Write-Host "SEGMENT_STDERR_TAIL_END"
    }
  }

  if ($summaryExists -ne 1) {
    throw "SEGMENT_SUMMARY_NOT_FOUND=$segmentSummary"
  }

  $summary = Get-Content -LiteralPath $segmentSummary -Raw | ConvertFrom-Json

  Write-Host "SEGMENT_TOTAL_STEPS=$($summary.total_steps)"
  Write-Host "SEGMENT_FAILED_STEPS=$($summary.failed_steps)"
  Write-Host "SEGMENT_OVERALL=$($summary.overall)"

  $segmentResults.Add([pscustomobject]@{
    name = $segment.Name
    exit_code = $segmentExit
    summary_path = $segmentSummary
    stdout_log = $segmentStdout
    stderr_log = $segmentStderr
    total_steps = [int]$summary.total_steps
    failed_steps = [int]$summary.failed_steps
    overall = [string]$summary.overall
  }) | Out-Null

  foreach ($r in $summary.results) {
    $allStepResults.Add($r) | Out-Null
  }

  if ($segmentExit -ne 0) {
    throw "SEGMENT_FAILED=$($segment.Name)"
  }
}

$totalSteps = $allStepResults.Count
$failedSteps = @($allStepResults | Where-Object { -not $_.ok }).Count
$passedSteps = $totalSteps - $failedSteps
$overall = if ($failedSteps -eq 0) { "PASS" } else { "FAIL" }

$masterSummary = [pscustomobject]@{
  iterations = $Iterations
  total_steps = $totalSteps
  passed_steps = $passedSteps
  failed_steps = $failedSteps
  overall = $overall
  segments = $segmentResults
  results = $allStepResults
}

$masterSummaryPath = Join-Path $OutputRoot "summary.segmented.json"
$masterSummary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $masterSummaryPath -Encoding UTF8

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════"
Write-Host "SEGMENTED BURN-IN SUMMARY"
Write-Host "════════════════════════════════════════════════════════════"
Write-Host "TOTAL_STEPS=$totalSteps"
Write-Host "PASSED_STEPS=$passedSteps"
Write-Host "FAILED_STEPS=$failedSteps"
Write-Host "OVERALL=$overall"
Write-Host "MASTER_SUMMARY_PATH=$masterSummaryPath"

if ($failedSteps -ne 0) {
  exit 1
}

exit 0

