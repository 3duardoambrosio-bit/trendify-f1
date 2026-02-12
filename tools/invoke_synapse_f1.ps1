Set-StrictMode -Version Latest
$ErrorActionPreference="Stop"

function Invoke-SynapseF1 {
  param(
    [ValidateSet("ci","dev")]
    [string]$Mode="ci"
  )

  "BRANCH=$(git branch --show-current)"
  "HEAD=$(git log --oneline -1)"

  $dirty=(git status --porcelain | Measure-Object).Count
  "dirty_lines=$dirty"
  if($dirty -ne 0){ throw "FAIL: dirty_lines_expected_0 got=$dirty" }

  python .\tools\audit_f1.py | Out-Host
  if($LASTEXITCODE -ne 0){ throw "FAIL: audit_exit=$LASTEXITCODE" }

  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\verify_plus.ps1 $Mode
  "verify_plus_exit=$LASTEXITCODE"
  if($LASTEXITCODE -ne 0){ throw "FAIL: verify_plus_exit=$LASTEXITCODE" }

  "OK=1"
}

Invoke-SynapseF1 -Mode "ci"