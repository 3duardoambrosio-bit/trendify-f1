param(
  [string]$RepoRoot = (Get-Location).Path,
  [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function CountOf($x) {
  if ($null -eq $x) { return 0 }
  return @($x).Count
}

$repo = (Resolve-Path $RepoRoot).Path
$gate = Join-Path $repo "scripts\gate_f1.ps1"

if (-not (Test-Path $gate)) {
  throw "A8_R43K_FAIL_GATE_NOT_FOUND=$gate"
}

$lines = @(Get-Content -Path $gate -Encoding UTF8)
$text = $lines -join "`n"

$exitZero = @()
$registry = @()
$noVerify = @()
$passMarkers = @()

for ($i = 0; $i -lt $lines.Count; $i++) {
  $n = $i + 1
  $line = [string]$lines[$i]

  if ($line -match '^\s*exit\s+0\b') { $exitZero += $n }
  if ($line -match '(?i)check_a8_r43g_registry_gates\.ps1') { $registry += $n }
  if ($line -match '(?i)--no-verify') { $noVerify += $n }
  if ($line -match '(?i)(LOCAL_.*PASS|ALL_PASS|PASS=1|PASS_MARKER|READY_FOR_.*PASS)') { $passMarkers += $n }
}

$localPassExitZero = @()
$exemptExitZero = @()
$exitBeforeRegistry = @()

foreach ($n in $exitZero) {
  $idx = $n - 1
  $start = [Math]::Max(0, $idx - 20)
  $window = ($lines[$start..$idx] -join "`n")

  if ($window -match '(?i)(usage|show[_-]?help|get-help|\b-help\b|--help|parameter help|print help)') {
    $exemptExitZero += $n
    continue
  }

  $localPassExitZero += $n

  $registryBefore = @($registry | Where-Object { $_ -lt $n })
  if ((CountOf $registryBefore) -lt 1) {
    $exitBeforeRegistry += $n
  }
}

$toolPattern = [regex]'(?i)(?:^|[\s''"`(])(?:\.?[\\/])?(tools[\\/][^''"`\s\)]+?\.ps1)'
$toolRefs = @()

foreach ($m in $toolPattern.Matches($text)) {
  $raw = [string]$m.Groups[1].Value
  if ([string]::IsNullOrWhiteSpace($raw)) { continue }
  $norm = $raw.Replace("/", "\").Trim()
  if ($toolRefs -notcontains $norm) { $toolRefs += $norm }
}

$missingTools = @()
foreach ($ref in $toolRefs) {
  if (-not (Test-Path (Join-Path $repo $ref))) {
    $missingTools += $ref
  }
}

$failures = @()

if ((CountOf $exitZero) -lt 1) { $failures += "EXIT_ZERO_COUNT_LT_1" }
if ((CountOf $registry) -lt 1) { $failures += "REGISTRY_GATE_INVOCATION_NOT_FOUND" }
if ((CountOf $localPassExitZero) -lt 1) { $failures += "LOCAL_PASS_EXIT_ZERO_COUNT_LT_1" }
if ((CountOf $exitBeforeRegistry) -ne 0) { $failures += "EXIT_ZERO_BEFORE_REGISTRY_GATE_COUNT=$(CountOf $exitBeforeRegistry)" }
if ((CountOf $noVerify) -ne 0) { $failures += "NO_VERIFY_REFERENCE_IN_GATE_F1_COUNT=$(CountOf $noVerify)" }
if ((CountOf $missingTools) -ne 0) { $failures += "MISSING_TOOL_REFERENCE_COUNT=$(CountOf $missingTools)" }

$result = [ordered]@{
  pass = ((CountOf $failures) -eq 0)
  gate_file = "scripts/gate_f1.ps1"
  exit_zero_count = CountOf $exitZero
  exempt_exit_zero_count = CountOf $exemptExitZero
  local_pass_exit_zero_count = CountOf $localPassExitZero
  registry_gate_hit_count = CountOf $registry
  exit_zero_before_registry_gate_count = CountOf $exitBeforeRegistry
  no_verify_in_gate_count = CountOf $noVerify
  pass_marker_count = CountOf $passMarkers
  literal_tool_reference_count = CountOf $toolRefs
  missing_tool_reference_count = CountOf $missingTools
  exit_zero_lines = @($exitZero)
  exempt_exit_zero_lines = @($exemptExitZero)
  local_pass_exit_zero_lines = @($localPassExitZero)
  registry_gate_lines = @($registry)
  exit_zero_before_registry_gate_lines = @($exitBeforeRegistry)
  no_verify_lines = @($noVerify)
  missing_tool_references = @($missingTools)
  failures = @($failures)
}

Write-Host "A8_R43K_EXIT_ZERO_COUNT=$($result.exit_zero_count)"
Write-Host "A8_R43K_EXEMPT_EXIT_ZERO_COUNT=$($result.exempt_exit_zero_count)"
Write-Host "A8_R43K_LOCAL_PASS_EXIT_ZERO_COUNT=$($result.local_pass_exit_zero_count)"
Write-Host "A8_R43K_REGISTRY_GATE_HIT_COUNT=$($result.registry_gate_hit_count)"
Write-Host "A8_R43K_EXIT_ZERO_BEFORE_REGISTRY_GATE_COUNT=$($result.exit_zero_before_registry_gate_count)"
Write-Host "A8_R43K_NO_VERIFY_IN_GATE_COUNT=$($result.no_verify_in_gate_count)"
Write-Host "A8_R43K_PASS_MARKER_COUNT=$($result.pass_marker_count)"
Write-Host "A8_R43K_LITERAL_TOOL_REFERENCE_COUNT=$($result.literal_tool_reference_count)"
Write-Host "A8_R43K_MISSING_TOOL_REFERENCE_COUNT=$($result.missing_tool_reference_count)"

if (-not [string]::IsNullOrWhiteSpace($ReportPath)) {
  $dir = Split-Path -Parent $ReportPath
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $result | ConvertTo-Json -Depth 8 | Set-Content -Path $ReportPath -Encoding UTF8
  Write-Host "A8_R43K_REPORT_PATH=$ReportPath"
}

if ((CountOf $failures) -ne 0) {
  Write-Host "A8_R43K_FAILURES_BEGIN"
  $failures | ForEach-Object { Write-Host $_ }
  Write-Host "A8_R43K_FAILURES_END"
  Write-Host "A8_R43K_PASS=0"
  exit 1
}

Write-Host "A8_R43K_PASS=1"
exit 0
