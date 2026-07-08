param(
  [switch]$Strict,
  [string[]]$Gap = @(),
  [string[]]$Session = @()
)

$ErrorActionPreference="Stop"
Write-Host "=== OPS REALITY GATE (v3 tag coverage) ==="

$gapsPath = Join-Path $PSScriptRoot "..\config\revenue_engineering\session_gaps.json"
if (-not (Test-Path $gapsPath)) { Write-Error "Missing: $gapsPath"; exit 3 }

$j = Get-Content $gapsPath -Raw | ConvertFrom-Json
$all = @()
$j.sessions.psobject.Properties | ForEach-Object {
  $sid = $_.Name
  $items = @($_.Value.must_have_before_live) + @($_.Value.v3_injections)
  foreach ($g in $items) {
    if ($g -and ($g.Trim().Length -gt 0)) {
      $all += [pscustomobject]@{ session=$sid; gap=$g }
    }
  }
}

$selected = @($all)

if ($Session.Count -gt 0) {
  $selected = @($selected | Where-Object { $_.session -in $Session })
}

if ($Gap.Count -gt 0) {
  $selected = @($selected | Where-Object { $_.gap -in $Gap })
}

if (($Session.Count -gt 0 -or $Gap.Count -gt 0) -and $selected.Count -eq 0) {
  Write-Error "No gaps matched the requested scope."
  exit 4
}

$codeRoots = @("synapse","ops","infra","vault")
$testRoots = @("tests","ops\tests")

function Count-Hits([string[]]$roots, [string]$needle) {
  $files = @()
  foreach ($r in $roots) {
    if (Test-Path $r) { $files += Get-ChildItem $r -Recurse -File -Include *.py,*.ps1 }
  }
  if ($files.Count -eq 0) { return 0 }
  return @($files | Select-String -SimpleMatch -Pattern $needle -ErrorAction SilentlyContinue).Count
}

$missing = @()
foreach ($row in $selected) {
  $tag = "V3GAP:$($row.gap)"
  $c = Count-Hits $codeRoots $tag
  $t = Count-Hits $testRoots $tag
  if ($c -lt 1 -or $t -lt 1) {
    $missing += [pscustomobject]@{ session=$row.session; gap=$row.gap; code_hits=$c; test_hits=$t }
  }
}

"scope_sessions=$($Session.Count)"
"scope_gaps=$($Gap.Count)"
"total_gaps_considered=$($selected.Count)"
"missing_gaps=$($missing.Count)"

if ($missing.Count -gt 0) {
  Write-Host ""
  Write-Host "=== MISSING TAG COVERAGE (informational unless -Strict) ==="
  $missing | Sort session,gap | Format-Table -AutoSize | Out-String | Write-Host
  if ($Strict) { exit 7 }
}

Write-Host "[PASS] Ops Reality OK"