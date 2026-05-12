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

function Age($Name, $Minimum, $Actual) {
  Write-Host "$Name=$Actual"
  if ([int]$Actual -lt [int]$Minimum) {
    throw "$Name`_TOO_LOW minimum=$Minimum actual=$Actual"
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

$functionBeginCount = ([regex]::Matches($text, "(?m)^\s*#\s*A8_R43H_REGISTRY_GATE_FUNCTION_BEGIN\s*$")).Count
$functionEndCount = ([regex]::Matches($text, "(?m)^\s*#\s*A8_R43H_REGISTRY_GATE_FUNCTION_END\s*$")).Count
$callBeginMatches = [regex]::Matches($text, "(?m)^\s*#\s*A8_R43H_REGISTRY_GATE_CALL_BEGIN\s*$")
$callEndCount = ([regex]::Matches($text, "(?m)^\s*#\s*A8_R43H_REGISTRY_GATE_CALL_END\s*$")).Count

$writeBeginCount = ([regex]::Matches($text, 'Write-Host\s+"A8_R43H_REGISTRY_GATE_BEGIN"')).Count
$writePassCount = ([regex]::Matches($text, 'Write-Host\s+"A8_R43H_REGISTRY_GATE_PASS=1"')).Count
$referenceCount = ([regex]::Matches($text, "tools/check_a8_r43g_registry_gates.ps1")).Count
$failureThrowCount = ([regex]::Matches($text, "A8_R43H_REGISTRY_GATE_FAILED")).Count

$localPassPattern = '(?m)^\s*Write-Host\s+["'']=== SYNAPSE F1 GATE: PASS ===["'']\s*$'
$localPassMatches = [regex]::Matches($text, $localPassPattern)

Aeq "A8_R43H_FUNCTION_BEGIN_COUNT" 1 $functionBeginCount
Aeq "A8_R43H_FUNCTION_END_COUNT" 1 $functionEndCount
Aeq "A8_R43H_WRITE_BEGIN_COUNT" 1 $writeBeginCount
Aeq "A8_R43H_WRITE_PASS_COUNT" 1 $writePassCount
Aeq "A8_R43H_GATE_REFERENCE_COUNT" 1 $referenceCount
Aeq "A8_R43H_FAILURE_THROW_COUNT" 1 $failureThrowCount
Age "A8_R43H_LOCAL_PASS_MARKER_COUNT" 1 $localPassMatches.Count

Aeq "A8_R43H_GATE_CALL_BEGIN_COUNT" $localPassMatches.Count $callBeginMatches.Count
Aeq "A8_R43H_GATE_CALL_END_COUNT" $localPassMatches.Count $callEndCount

$beforeEach = 1
for ($i = 0; $i -lt $localPassMatches.Count; $i++) {
  if ($callBeginMatches[$i].Index -gt $localPassMatches[$i].Index) {
    $beforeEach = 0
  }
}

Aeq "A8_R43H_GATE_CALL_BEFORE_EACH_LOCAL_PASS" 1 $beforeEach
Aeq "A8_R43H_GATE_CALL_COUNT_EQUALS_PASS_COUNT" 1 ([int]($callBeginMatches.Count -eq $localPassMatches.Count))

& $centralGate -Repo $Repo
$rc = $LASTEXITCODE
if ($null -eq $rc) { $rc = 0 }

Aeq "A8_R43H_CENTRAL_GATE_RC" 0 $rc

Write-Host "A8_R43H_LOCAL_VALIDATION_REGISTRY_GATE_PASS=1"
