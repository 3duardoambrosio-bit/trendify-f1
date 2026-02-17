param(
  [switch]$Strict
)

$path = Join-Path $PSScriptRoot "..\config\revenue_engineering\modules.json"
if (-not (Test-Path $path)) { Write-Error "Missing: $path"; exit 3 }

$j = Get-Content $path -Raw | ConvertFrom-Json
$mods = @($j.modules)

$inject  = @($mods | ? status -eq "INJECT")
$phase2  = @($mods | ? status -eq "PHASE2")
$blocked = @($mods | ? status -eq "BLOCKED")

Write-Host "=== REVENUE ENGINEERING GATE ==="
"inject_count=$($inject.Count)"
"phase2_count=$($phase2.Count)"
"blocked_count=$($blocked.Count)"

Write-Host ""
Write-Host "=== INJECT NOW (S10-S18/PRs) ==="
$inject | Select id,name,inject_session | Format-Table -AutoSize | Out-String | Write-Host

Write-Host "=== PHASE2 (needs infra/guardrails) ==="
$phase2 | Select id,name,inject_session | Format-Table -AutoSize | Out-String | Write-Host

Write-Host "=== BLOCKED (NO IMPLEMENTAR) ==="
$blocked | Select id,name,reason | Format-Table -AutoSize | Out-String | Write-Host

# Acceptance: blocked modules must NOT have inject_session
$bad = @($blocked | ? { $_.inject_session -ne $null })
if ($bad.Count -gt 0) { Write-Error "Blocked modules scheduled for injection (invalid)"; exit 7 }

if ($Strict -and $blocked.Count -gt 0) {
  Write-Error "STRICT FAIL: blocked_count>0"
  exit 8
}

Write-Host "[PASS] Revenue Engineering map OK"
exit 0


