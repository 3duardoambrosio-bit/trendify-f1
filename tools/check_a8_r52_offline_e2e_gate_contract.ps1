$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "A8-R52 OFFLINE E2E GATE STATIC CONTRACT CHECK"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

$tool = "tools/run_offline_e2e_gate.ps1"
$doc = "docs/ops/A8_R52_OFFLINE_E2E_HARDENING_GATE.md"
$test = "tests/ops/test_a8_r52_offline_e2e_gate_contract.py"

function Assert-FileExists {
  param([string]$Path)
  $exists = [int](Test-Path $Path)
  Write-Host "FILE_EXISTS[$Path]=$exists"
  if ($exists -ne 1) { throw "MISSING_FILE=$Path" }
}

function Assert-Contains {
  param([string]$Path, [string]$Marker, [string]$Name)
  $text = Get-Content -Path $Path -Raw
  $ok = [int]$text.Contains($Marker)
  Write-Host "$Name=$ok"
  if ($ok -ne 1) { throw "MISSING_MARKER name=$Name path=$Path marker=$Marker" }
}

function Assert-NoCrLfNoBom {
  param([string]$Path)
  $text = [System.IO.File]::ReadAllText((Join-Path $repo $Path))
  $bytes = [System.IO.File]::ReadAllBytes((Join-Path $repo $Path))
  $crlf = ([regex]::Matches($text, "`r`n")).Count
  $cr = ([regex]::Matches($text, "`r")).Count
  $bom = 0
  if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { $bom = 1 }
  Write-Host "NO_CRLF[$Path]=$([int]($crlf -eq 0))"
  Write-Host "NO_CR[$Path]=$([int]($cr -eq 0))"
  Write-Host "NO_BOM[$Path]=$([int]($bom -eq 0))"
  if ($crlf -ne 0) { throw "CRLF_FOUND path=$Path count=$crlf" }
  if ($cr -ne 0) { throw "CR_FOUND path=$Path count=$cr" }
  if ($bom -ne 0) { throw "BOM_FOUND path=$Path" }
}

Assert-FileExists $tool
Assert-FileExists $doc
Assert-FileExists $test

foreach ($p in @($tool, $doc, $test)) { Assert-NoCrLfNoBom $p }

Assert-Contains $tool "A8-R52 OFFLINE E2E HARDENING GATE" "TOOL_HEADER"
Assert-Contains $tool "scripts\run_burnin_mock.py" "TOOL_BURNIN_SCRIPT"
Assert-Contains $tool "SUMMARY_DISPATCH_COUNT" "TOOL_SUMMARY_DISPATCH_COUNT"
Assert-Contains $tool "SUMMARY_LEDGER_EVENT_COUNT" "TOOL_SUMMARY_LEDGER_EVENT_COUNT"
Assert-Contains $tool "SUMMARY_PRE_SPEND_GATE_BLOCKED_COUNT" "TOOL_PRE_SPEND_BLOCKED_COUNT"
Assert-Contains $tool "flag_shopify_live=0" "TOOL_SHOPIFY_LIVE_FLAG_OFF"
Assert-Contains $tool "flag_meta_live_api=0" "TOOL_META_LIVE_FLAG_OFF"
Assert-Contains $tool "flag_dropi_live_orders=0" "TOOL_DROPI_LIVE_FLAG_OFF"
Assert-Contains $tool "A8_R52_OFFLINE_E2E_GATE_PASS=1" "TOOL_PASS_MARKER"
Assert-Contains $tool "NO_EXTERNAL_MUTATION=1" "TOOL_NO_EXTERNAL_MUTATION"
Assert-Contains $tool "NO_SHOPIFY_MUTATION=1" "TOOL_NO_SHOPIFY_MUTATION"
Assert-Contains $tool "NO_META_MUTATION=1" "TOOL_NO_META_MUTATION"
Assert-Contains $tool "NO_DROPI_MUTATION=1" "TOOL_NO_DROPI_MUTATION"
Assert-Contains $tool "AllowDirtyRepo" "TOOL_ALLOW_DIRTY_AUTHORING"

Assert-Contains $doc "powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/run_offline_e2e_gate.ps1 -Cycles 25" "DOC_CANONICAL_COMMAND"
Assert-Contains $doc "ledger_event_count" "DOC_LEDGER_EVENT_COUNT"
Assert-Contains $doc "pre_spend_gate_blocked" "DOC_PRE_SPEND_GATE_BLOCKED"
Assert-Contains $doc "repo status after gate" "DOC_REPO_STATUS_GATE"
Assert-Contains $doc "NO_EXTERNAL_MUTATION=1" "DOC_NO_EXTERNAL_MUTATION"

Assert-Contains $test "test_a8_r52_offline_e2e_gate_has_required_markers" "TEST_MARKER_TEST"
Assert-Contains $test "A8_R52_OFFLINE_E2E_GATE_PASS=1" "TEST_PASS_MARKER"

Write-Host "A8_R52_OFFLINE_E2E_GATE_STATIC_CONTRACT_PASS=1"
