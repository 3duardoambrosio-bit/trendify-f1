[CmdletBinding()]
param(
  [string]$TranscriptPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

[string[]]$statusBefore = @(git status --short)
$statusBefore = @($statusBefore | Where-Object { $_ -and $_.Trim().Length -gt 0 })

Write-Host "REPO=$repo"
Write-Host "STATUS_BEFORE_COUNT=$($statusBefore.Count)"
Write-Host "STATUS_BEFORE_BEGIN"
$statusBefore | ForEach-Object { Write-Host $_ }
Write-Host "STATUS_BEFORE_END"

if ($statusBefore.Count -ne 0) {
  throw "WORKTREE_NOT_CLEAN_BEFORE count=$($statusBefore.Count)"
}

$gateScript = Join-Path $repo "tools\run_f1_validation.ps1"
if (-not (Test-Path $gateScript)) {
  throw "GATE_SCRIPT_NOT_FOUND=$gateScript"
}

if ([string]::IsNullOrWhiteSpace($TranscriptPath)) {
  $ts = Get-Date -Format "yyyyMMdd_HHmmss"
  $logDir = Join-Path $env:TEMP "synapse_island_gate_$ts"
  $TranscriptPath = Join-Path $logDir "gate_transcript.txt"
}
else {
  $logDir = Split-Path -Parent $TranscriptPath
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Start-Transcript -Path $TranscriptPath -Force | Out-Null
try {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $gateScript
  $gateExit = $LASTEXITCODE
}
finally {
  Stop-Transcript | Out-Null
}

[string[]]$statusAfter = @(git status --short)
$statusAfter = @($statusAfter | Where-Object { $_ -and $_.Trim().Length -gt 0 })

Write-Host "GATE_EXIT=$gateExit"
Write-Host "LOG_PATH=$TranscriptPath"
Write-Host "OPEN_LOG_DIR=explorer.exe `"$logDir`""
Write-Host "OPEN_LOG_FILE=notepad `"$TranscriptPath`""
Write-Host "STATUS_AFTER_COUNT=$($statusAfter.Count)"
Write-Host "STATUS_AFTER_BEGIN"
$statusAfter | ForEach-Object { Write-Host $_ }
Write-Host "STATUS_AFTER_END"

$accept = 0
if ($gateExit -eq 0 -and $statusAfter.Count -eq 0) {
  $accept = 1
}
Write-Host "NUMERIC_ACCEPTANCE_PASS=$accept"

exit $gateExit
