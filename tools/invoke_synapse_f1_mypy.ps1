param(
  [switch]$Quiet
)

$ErrorActionPreference = "Stop"

function Invoke-NativeCapture {
  param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$Args
  )
  $out = & $Exe @Args 2>&1
  $code = $LASTEXITCODE
  if (-not $Quiet -and $out) { $out | Out-Host }
  return @{ out = $out; code = $code }
}

Write-Host "=== F1 MYPY GATE ==="

if (-not (Test-Path "pyproject.toml")) { throw "pyproject.toml not found in repo root" }

$r = Invoke-NativeCapture python -m mypy .
$mypyExit = [int]$r.code
$mypyErrLines = ($r.out | Select-String "error:" | Measure-Object).Count

"mypy_exit=$mypyExit"
"mypy_error_lines=$mypyErrLines"

if ($mypyExit -ne 0) { throw "MYPY EXIT != 0" }
if ($mypyErrLines -ne 0) { throw "MYPY HAS ERRORS" }

Write-Host "=== F1 MYPY GATE: GREEN ==="
