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

Set-Location $Repo

$localGate = Join-Path $Repo "scripts/gate_f1.ps1"
$centralGate = Join-Path $Repo "tools/check_a8_r43g_registry_gates.ps1"

if (-not (Test-Path $localGate)) {
  throw "A8_R43H_LOCAL_GATE_NOT_FOUND=$localGate"
}

if (-not (Test-Path $centralGate)) {
  throw "A8_R43H_CENTRAL_GATE_NOT_FOUND=$centralGate"
}

$text = Get-Content -Raw -Path $localGate

$commentBeginCount = ([regex]::Matches($text, "(?m)^\s*#\s*A8_R43H_REGISTRY_GATE_BEGIN\s*$")).Count
$commentEndCount = ([regex]::Matches($text, "(?m)^\s*#\s*A8_R43H_REGISTRY_GATE_END\s*$")).Count
$writeBeginCount = ([regex]::Matches($text, 'Write-Host\s+"A8_R43H_REGISTRY_GATE_BEGIN"')).Count
$writePassCount = ([regex]::Matches($text, 'Write-Host\s+"A8_R43H_REGISTRY_GATE_PASS=1"')).Count
$referenceCount = ([regex]::Matches($text, "tools/check_a8_r43g_registry_gates.ps1")).Count
$failureThrowCount = ([regex]::Matches($text, "A8_R43H_REGISTRY_GATE_FAILED")).Count

Aeq "A8_R43H_COMMENT_BEGIN_COUNT" 1 $commentBeginCount
Aeq "A8_R43H_COMMENT_END_COUNT" 1 $commentEndCount
Aeq "A8_R43H_WRITE_BEGIN_COUNT" 1 $writeBeginCount
Aeq "A8_R43H_WRITE_PASS_COUNT" 1 $writePassCount
Aeq "A8_R43H_GATE_REFERENCE_COUNT" 1 $referenceCount
Aeq "A8_R43H_FAILURE_THROW_COUNT" 1 $failureThrowCount

& $centralGate -Repo $Repo
$rc = $LASTEXITCODE
if ($null -eq $rc) { $rc = 0 }

Aeq "A8_R43H_CENTRAL_GATE_RC" 0 $rc

Write-Host "A8_R43H_LOCAL_VALIDATION_REGISTRY_GATE_PASS=1"
