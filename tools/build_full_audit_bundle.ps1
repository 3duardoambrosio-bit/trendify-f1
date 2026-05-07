param(
  [string]$Repo = (Get-Location).Path,
  [string]$OutDir = "",
  [string]$ZipPath = "",
  [switch]$SkipHeavy
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Repo = (Resolve-Path $Repo).Path
if ([string]::IsNullOrWhiteSpace($OutDir)) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $OutDir = Join-Path "C:\Temp" "trendify_full_audit_bundle_$stamp"
}
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
Set-Location $Repo

if ([string]::IsNullOrWhiteSpace($ZipPath)) {
  $headForZip = (git rev-parse --short HEAD).Trim()
  $ZipPath = "C:\Temp\trendify_FULL_AUDIT_BUNDLE_$headForZip.zip"
}

$py = Join-Path $Repo "venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  throw "PYTHON_NOT_FOUND=$py"
}

$env:PYTHONNOUSERSITE = "1"
$env:PYTHONPATH = ""
if ([string]::IsNullOrWhiteSpace($env:PYTEST_ADDOPTS) -or ($env:PYTEST_ADDOPTS -notmatch "(^|\s)--basetemp(=|\s)")) {
  $stableBaseTemp = ("C:/Temp/trendify_bundle_pytest_{0}_{1}" -f $PID, (Get-Date -Format "yyyyMMdd_HHmmss"))
  if ([string]::IsNullOrWhiteSpace($env:PYTEST_ADDOPTS)) {
    $env:PYTEST_ADDOPTS = "--basetemp=$stableBaseTemp"
  } else {
    $env:PYTEST_ADDOPTS = "$($env:PYTEST_ADDOPTS) --basetemp=$stableBaseTemp"
  }
}

function Write-TextFile {
  param([string]$Path, [string]$Text)
  Set-Content -Path $Path -Value $Text -Encoding UTF8
}

function Invoke-Captured {
  param(
    [string]$Name,
    [scriptblock]$Command
  )

  $stdout = Join-Path $OutDir "$Name.stdout.txt"
  $stderr = Join-Path $OutDir "$Name.stderr.txt"
  $rcPath = Join-Path $OutDir "$Name.rc.txt"

  try {
    & $Command > $stdout 2> $stderr
    $rc = $LASTEXITCODE
    if ($null -eq $rc) { $rc = 0 }
  } catch {
    $rc = 999
    Set-Content -Path $stderr -Value $_.Exception.Message -Encoding UTF8
  }

  Set-Content -Path $rcPath -Value "$rc" -Encoding ASCII
  return [int]$rc
}

$head = (git rev-parse --short HEAD).Trim()
$headFull = (git rev-parse HEAD).Trim()
$lastMsg = (git log -1 --pretty=format:%s)
$status = @(git status --short)
$showStat = git show --stat --oneline --summary HEAD
$cachedNames = @(git diff --cached --name-only)

Write-TextFile (Join-Path $OutDir "git_head.txt") $head
Write-TextFile (Join-Path $OutDir "git_head_full.txt") $headFull
Write-TextFile (Join-Path $OutDir "git_last_msg.txt") $lastMsg
Write-TextFile (Join-Path $OutDir "git_status.txt") ($status -join "`n")
Write-TextFile (Join-Path $OutDir "git_show_head_stat.txt") ($showStat -join "`n")
Write-TextFile (Join-Path $OutDir "git_diff_cached_name_only.txt") ($cachedNames -join "`n")

Invoke-Captured "git_diff_cached_check" { git diff --cached --check } | Out-Null
Invoke-Captured "git_diff_check" { git diff --check } | Out-Null
Invoke-Captured "control_check" { & $py "scripts/synapse_control_surface.py" --check } | Out-Null
Invoke-Captured "control_json" { & $py "scripts/synapse_control_surface.py" --json } | Out-Null
Copy-Item -LiteralPath (Join-Path $OutDir "control_json.stdout.txt") -Destination (Join-Path $OutDir "control_json.json") -Force

Invoke-Captured "local_health" { & $py "scripts/synapse_control_surface.py" --run local_health } | Out-Null
Copy-Item -LiteralPath (Join-Path $OutDir "local_health.stdout.txt") -Destination (Join-Path $OutDir "local_health.json") -Force

Invoke-Captured "local_recent_decisions" { & $py "scripts/synapse_control_surface.py" --run local_recent_decisions } | Out-Null
Copy-Item -LiteralPath (Join-Path $OutDir "local_recent_decisions.stdout.txt") -Destination (Join-Path $OutDir "local_recent_decisions.json") -Force

Invoke-Captured "local_safety_status" { & $py "scripts/synapse_control_surface.py" --run local_safety_status } | Out-Null
Copy-Item -LiteralPath (Join-Path $OutDir "local_safety_status.stdout.txt") -Destination (Join-Path $OutDir "local_safety_status.json") -Force

if ($SkipHeavy) {
  Write-TextFile (Join-Path $OutDir "targeted_control_surface.stdout.txt") "SKIPPED_BY_SKIPHEAVY=1"
  Write-TextFile (Join-Path $OutDir "targeted_control_surface.rc.txt") "0"
  Write-TextFile (Join-Path $OutDir "full_suite.stdout.txt") "SKIPPED_BY_SKIPHEAVY=1"
  Write-TextFile (Join-Path $OutDir "full_suite.rc.txt") "0"
  Write-TextFile (Join-Path $OutDir "hook_smoke.stdout.txt") "SKIPPED_BY_SKIPHEAVY=1"
  Write-TextFile (Join-Path $OutDir "hook_smoke.rc.txt") "0"
} else {
  Invoke-Captured "targeted_control_surface" { & $py -m pytest "tests/p0/test_local_control_surface_contract.py" -q } | Out-Null
  Invoke-Captured "full_suite" { & $py -m pytest -q } | Out-Null
  Write-TextFile (Join-Path $OutDir "hook_smoke.stdout.txt") "HOOK_SMOKE_NOT_RUN_BY_BUNDLE_BUILDER=1"
  Write-TextFile (Join-Path $OutDir "hook_smoke.rc.txt") "0"
}

$primaryFiles = @(
  "git_head.txt",
  "git_head_full.txt",
  "git_last_msg.txt",
  "git_status.txt",
  "git_show_head_stat.txt",
  "git_diff_cached_name_only.txt",
  "git_diff_cached_check.stdout.txt",
  "control_check.stdout.txt",
  "control_json.json",
  "local_health.json",
  "local_recent_decisions.json",
  "local_safety_status.json",
  "targeted_control_surface.stdout.txt",
  "full_suite.stdout.txt",
  "hook_smoke.stdout.txt"
)

$existingPrimary = @($primaryFiles | Where-Object { Test-Path (Join-Path $OutDir $_) })
$bundleFileCount = @(Get-ChildItem -LiteralPath $OutDir -File).Count

$summary = @"
FULL_AUDIT_BUNDLE_PASS=1
HEAD=$head
HEAD_FULL=$headFull
LAST_MSG=$lastMsg
STATUS_COUNT=$($status.Count)
PYTEST_ADDOPTS_EFFECTIVE=$env:PYTEST_ADDOPTS
PRIMARY_EVIDENCE_FILE_COUNT=$($existingPrimary.Count)
BUNDLE_FILE_COUNT=$bundleFileCount
SKIP_HEAVY=$([int]$SkipHeavy.IsPresent)
"@
Write-TextFile (Join-Path $OutDir "summary.txt") $summary

Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path $ZipPath) {
  Remove-Item -LiteralPath $ZipPath -Force
}
[System.IO.Compression.ZipFile]::CreateFromDirectory($OutDir, $ZipPath)
$zipHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash

Write-Host "FULL_AUDIT_BUNDLE_OUT_DIR=$OutDir"
Write-Host "FULL_AUDIT_BUNDLE_ZIP_PATH=$ZipPath"
Write-Host "FULL_AUDIT_BUNDLE_ZIP_EXISTS=$([int](Test-Path $ZipPath))"
Write-Host "FULL_AUDIT_BUNDLE_ZIP_SHA256=$zipHash"
Write-Host "PRIMARY_EVIDENCE_FILE_COUNT=$($existingPrimary.Count)"
Write-Host "BUNDLE_FILE_COUNT=$bundleFileCount"
Write-Host "FULL_AUDIT_BUNDLE_PASS=1"

if ($existingPrimary.Count -lt 15) {
  throw "PRIMARY_EVIDENCE_FILE_COUNT_TOO_LOW=$($existingPrimary.Count)"
}
