param()

$ErrorActionPreference="Stop"
Write-Host "=== POLICY EXPOSURE GATE (blocked modules must not exist in runtime code) ==="

$mapPath = Join-Path $PSScriptRoot "..\config\revenue_engineering\modules.json"
if (-not (Test-Path $mapPath)) { Write-Error "Missing: $mapPath"; exit 3 }

$j = Get-Content $mapPath -Raw | ConvertFrom-Json
$blocked = @($j.modules | Where-Object status -eq "BLOCKED")

$runtimeRoots = @("synapse","ops","infra")
$files = @()
foreach ($r in $runtimeRoots) {
  if (Test-Path $r) { $files += Get-ChildItem $r -Recurse -File -Include *.py,*.ps1 }
}

$hits = @()
foreach ($b in $blocked) {
  $needles = @($b.name, $b.id)
  foreach ($n in $needles) {
    if (-not $n) { continue }
    $c = @($files | Select-String -SimpleMatch -Pattern $n -ErrorAction SilentlyContinue).Count
    if ($c -gt 0) { $hits += [pscustomobject]@{ blocked_id=$b.id; needle=$n; hits=$c } }
  }
}

"blocked_count=$($blocked.Count)"
"forbidden_hits=$($hits.Count)"

if ($hits.Count -gt 0) {
  Write-Host ""
  Write-Host "=== FORBIDDEN REFERENCES IN RUNTIME CODE ==="
  $hits | Format-Table -AutoSize | Out-String | Write-Host
  exit 9
}

Write-Host "[PASS] No blocked module refs in runtime code"
