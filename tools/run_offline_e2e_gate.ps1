param(
  [int]$Cycles = 25,
  [string]$RepoRoot = "",
  [string]$EvidenceRoot = "",
  [switch]$AllowDirtyRepo
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Utf8NoBom {
  param([string]$Path, [string[]]$Lines)
  $dir = Split-Path $Path -Parent
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
  $enc = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllLines($Path, $Lines, $enc)
}

function Assert-IntEq {
  param([int]$Actual, [int]$Expected, [string]$Name)
  Write-Host "$Name=$Actual"
  if ($Actual -ne $Expected) { throw "$($Name)_BAD expected=$Expected actual=$Actual" }
}

function Invoke-PythonDirect {
  param([string]$Label, [string]$PythonExe, [string[]]$Arguments)
  Write-Host ""
  Write-Host "================ $Label"
  $old = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    & $PythonExe @Arguments
    $rc = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $old
  }
  Write-Host "$($Label)_RC=$rc"
  if ($rc -ne 0) { throw "$($Label)_FAILED_RC=$rc" }
}

function Invoke-PythonCapture {
  param([string]$Label, [string]$PythonExe, [string[]]$Arguments, [string]$LogPath)
  Write-Host ""
  Write-Host "================ $Label"
  $old = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $output = & $PythonExe @Arguments 2>&1
    $rc = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $old
  }
  $lines = @($output | ForEach-Object { [string]$_ })
  Write-Utf8NoBom -Path $LogPath -Lines $lines
  $lines | ForEach-Object { Write-Host $_ }
  Write-Host "$($Label)_RC=$rc"
  if ($rc -ne 0) { throw "$($Label)_FAILED_RC=$rc" }
  return ($lines -join "`n")
}

Write-Host "============================================================"
Write-Host "A8-R52 OFFLINE E2E HARDENING GATE"
Write-Host "============================================================"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
} else {
  $RepoRoot = (Resolve-Path $RepoRoot).Path
}
Set-Location $RepoRoot

Write-Host ""
Write-Host "================ 01_GUARDRAILS"
$branch = (git branch --show-current).Trim()
$head = (git rev-parse --short HEAD).Trim()
$fullHead = (git rev-parse HEAD).Trim()
$subject = (git log -1 --pretty=%s).Trim()
$statusBefore = @(git status --short)
Write-Host "REPO=$RepoRoot"
Write-Host "BRANCH=$branch"
Write-Host "HEAD=$head"
Write-Host "FULL_HEAD=$fullHead"
Write-Host "SUBJECT=$subject"
Write-Host "STATUS_BEFORE_COUNT=$($statusBefore.Count)"
Write-Host "ALLOW_DIRTY_REPO=$([int]$AllowDirtyRepo.IsPresent)"
if (-not $AllowDirtyRepo.IsPresent -and $statusBefore.Count -ne 0) {
  Write-Host "STATUS_BEFORE_BEGIN"
  $statusBefore | ForEach-Object { Write-Host $_ }
  Write-Host "STATUS_BEFORE_END"
  throw "REPO_NOT_CLEAN_BEFORE=$($statusBefore.Count)"
}
if ($Cycles -le 0) { throw "CYCLES_MUST_BE_POSITIVE=$Cycles" }
$pythonExe = "python"
$venvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
if (Test-Path $venvPython) { $pythonExe = $venvPython }
Write-Host "PYTHON_EXE=$pythonExe"
Write-Host "CYCLES=$Cycles"

Write-Host ""
Write-Host "================ 02_EVIDENCE_ROOT"
if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $EvidenceRoot = "C:\Temp\SYNAPSE_A8_R52_OFFLINE_E2E_GATE_$stamp"
}
while ($EvidenceRoot.EndsWith("\") -or $EvidenceRoot.EndsWith("/")) {
  $EvidenceRoot = $EvidenceRoot.Substring(0, $EvidenceRoot.Length - 1)
}
$evidenceDir = Join-Path $EvidenceRoot "evidence"
$logsDir = Join-Path $EvidenceRoot "logs"
$manifestPath = Join-Path $EvidenceRoot "A8_R52_OFFLINE_E2E_GATE_MANIFEST.txt"
$zipPath = Join-Path $EvidenceRoot "synapse_a8_r52_offline_e2e_gate_evidence.zip"
New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
$statusLog = Join-Path $logsDir "synapse_cli_status.txt"
$doctorLog = Join-Path $logsDir "synapse_cli_doctor.txt"
Write-Host "EVIDENCE_ROOT=$EvidenceRoot"
Write-Host "EVIDENCE_DIR=$evidenceDir"
Write-Host "LOGS_DIR=$logsDir"

Invoke-PythonDirect -Label "BURNIN_E2E" -PythonExe $pythonExe -Arguments @("scripts\run_burnin_mock.py", "--cycles", "$Cycles", "--out-dir", "$evidenceDir")

Write-Host ""
Write-Host "================ 03_VALIDATE_OUTPUTS"
$summaryPath = Join-Path $evidenceDir "burnin_summary.json"
$ledgerPath = Join-Path $evidenceDir "ledger.ndjson"
$idemPath = Join-Path $evidenceDir "idem.sqlite3"
$summaryExists = [int](Test-Path $summaryPath)
$ledgerExists = [int](Test-Path $ledgerPath)
$idemExists = [int](Test-Path $idemPath)
Write-Host "SUMMARY_EXISTS=$summaryExists"
Write-Host "LEDGER_EXISTS=$ledgerExists"
Write-Host "IDEMPOTENCY_DB_EXISTS=$idemExists"
if ($summaryExists -ne 1) { throw "SUMMARY_MISSING=$summaryPath" }
if ($ledgerExists -ne 1) { throw "LEDGER_MISSING=$ledgerPath" }
if ($idemExists -ne 1) { throw "IDEMPOTENCY_DB_MISSING=$idemPath" }
$summary = Get-Content -Path $summaryPath -Raw | ConvertFrom-Json
$ledgerLineCount = @(Get-Content $ledgerPath).Count
$expectedDispatch = $Cycles * 4
$expectedLedger = $Cycles * 3
$expectedBlocked = $Cycles
$expectedDispatched = $Cycles
$expectedSkipped = $Cycles * 2
Assert-IntEq -Actual ([int]$summary.cycles) -Expected $Cycles -Name "SUMMARY_CYCLES"
Assert-IntEq -Actual ([int]$summary.dispatch_count) -Expected $expectedDispatch -Name "SUMMARY_DISPATCH_COUNT"
Assert-IntEq -Actual ([int]$summary.ledger_event_count) -Expected $expectedLedger -Name "SUMMARY_LEDGER_EVENT_COUNT"
Assert-IntEq -Actual ([int]$ledgerLineCount) -Expected $expectedLedger -Name "LEDGER_LINE_COUNT"
Assert-IntEq -Actual ([int]$summary.normalized_outcome_counts.BLOCKED) -Expected $expectedBlocked -Name "SUMMARY_BLOCKED_COUNT"
Assert-IntEq -Actual ([int]$summary.normalized_outcome_counts.DISPATCHED) -Expected $expectedDispatched -Name "SUMMARY_DISPATCHED_COUNT"
Assert-IntEq -Actual ([int]$summary.normalized_outcome_counts.SKIPPED) -Expected $expectedSkipped -Name "SUMMARY_SKIPPED_COUNT"
Assert-IntEq -Actual ([int]$summary.blocked_error_counts.pre_spend_gate_blocked) -Expected $expectedBlocked -Name "SUMMARY_PRE_SPEND_GATE_BLOCKED_COUNT"

$statusText = Invoke-PythonCapture -Label "SYNAPSE_CLI_STATUS" -PythonExe $pythonExe -Arguments @("-m", "synapse.cli", "status") -LogPath $statusLog
if (-not $AllowDirtyRepo.IsPresent -and $statusText -notmatch "dirty_lines=0") { throw "CLI_STATUS_DIRTY_LINES_NOT_ZERO" }
if ($statusText -notmatch "doctor_overall=GREEN") { throw "CLI_STATUS_DOCTOR_NOT_GREEN" }
if ($statusText -notmatch "flag_shopify_live=0") { throw "CLI_STATUS_SHOPIFY_LIVE_NOT_ZERO" }
if ($statusText -notmatch "flag_meta_live_api=0") { throw "CLI_STATUS_META_LIVE_NOT_ZERO" }
if ($statusText -notmatch "flag_dropi_live_orders=0") { throw "CLI_STATUS_DROPI_LIVE_NOT_ZERO" }
$doctorText = Invoke-PythonCapture -Label "SYNAPSE_CLI_DOCTOR" -PythonExe $pythonExe -Arguments @("-m", "synapse.cli", "doctor") -LogPath $doctorLog
if ($doctorText -notmatch "OVERALL:\s+GREEN") { throw "CLI_DOCTOR_OVERALL_NOT_GREEN" }

Write-Host ""
Write-Host "================ 04_PACKAGE_EVIDENCE"
$summaryHash = (Get-FileHash $summaryPath -Algorithm SHA256).Hash
$ledgerHash = (Get-FileHash $ledgerPath -Algorithm SHA256).Hash
$idemHash = (Get-FileHash $idemPath -Algorithm SHA256).Hash
$statusHash = (Get-FileHash $statusLog -Algorithm SHA256).Hash
$doctorHash = (Get-FileHash $doctorLog -Algorithm SHA256).Hash
$manifestLines = @(
  "A8-R52 OFFLINE E2E HARDENING GATE MANIFEST",
  "REPO=$RepoRoot",
  "BRANCH=$branch",
  "HEAD=$head",
  "FULL_HEAD=$fullHead",
  "SUBJECT=$subject",
  "CYCLES=$Cycles",
  "EXPECTED_DISPATCH_COUNT=$expectedDispatch",
  "EXPECTED_LEDGER_EVENT_COUNT=$expectedLedger",
  "SUMMARY_SHA256=$summaryHash",
  "LEDGER_SHA256=$ledgerHash",
  "IDEMPOTENCY_DB_SHA256=$idemHash",
  "CLI_STATUS_LOG_SHA256=$statusHash",
  "CLI_DOCTOR_LOG_SHA256=$doctorHash",
  "SUMMARY_DISPATCH_COUNT=$($summary.dispatch_count)",
  "SUMMARY_LEDGER_EVENT_COUNT=$($summary.ledger_event_count)",
  "SUMMARY_PRE_SPEND_GATE_BLOCKED_COUNT=$($summary.blocked_error_counts.pre_spend_gate_blocked)",
  "NO_LAUNCH=1",
  "NO_SPEND=1",
  "NO_EXTERNAL_MUTATION=1",
  "NO_SHOPIFY_MUTATION=1",
  "NO_META_MUTATION=1",
  "NO_DROPI_MUTATION=1"
)
Write-Utf8NoBom -Path $manifestPath -Lines $manifestLines
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path @($evidenceDir, $logsDir, $manifestPath) -DestinationPath $zipPath -Force
$zipExists = [int](Test-Path $zipPath)
$zipSize = (Get-Item $zipPath).Length
$zipHash = (Get-FileHash $zipPath -Algorithm SHA256).Hash
Write-Host "EVIDENCE_ZIP=$zipPath"
Write-Host "EVIDENCE_ZIP_EXISTS=$zipExists"
Write-Host "EVIDENCE_ZIP_SIZE_BYTES=$zipSize"
Write-Host "EVIDENCE_ZIP_SHA256=$zipHash"
if ($zipExists -ne 1) { throw "EVIDENCE_ZIP_NOT_CREATED" }
if ($zipSize -le 1000) { throw "EVIDENCE_ZIP_TOO_SMALL=$zipSize" }

Write-Host ""
Write-Host "================ 05_REPO_CLEAN_VERIFY"
$statusAfter = @(git status --short)
Write-Host "STATUS_AFTER_COUNT=$($statusAfter.Count)"
if (-not $AllowDirtyRepo.IsPresent -and $statusAfter.Count -ne 0) {
  Write-Host "STATUS_AFTER_BEGIN"
  $statusAfter | ForEach-Object { Write-Host $_ }
  Write-Host "STATUS_AFTER_END"
  throw "REPO_NOT_CLEAN_AFTER=$($statusAfter.Count)"
}
Write-Host "A8_R52_OFFLINE_E2E_GATE_PASS=1"
