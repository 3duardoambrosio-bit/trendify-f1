[CmdletBinding()]
param(
  [string[]]$PyCompilePaths = @(),
  [string[]]$PytestPaths = @(),
  [string]$Pattern = "",
  [string[]]$PatternFiles = @(),
  [switch]$QuietPytest,
  [switch]$StopOnFirstFailure
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$py = Join-Path $repo "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

[string[]]$statusBefore = @(git status --short)
$statusBefore = @($statusBefore | Where-Object { $_ -and $_.Trim().Length -gt 0 })

Write-Host "REPO=$repo"
Write-Host "PYTHON=$py"
Write-Host "STATUS_BEFORE_COUNT=$($statusBefore.Count)"
Write-Host "STATUS_BEFORE_BEGIN"
$statusBefore | ForEach-Object { Write-Host $_ }
Write-Host "STATUS_BEFORE_END"

$compileExit = 0
if ($PyCompilePaths.Count -gt 0) {
  foreach ($path in $PyCompilePaths) {
    if (-not (Test-Path $path)) {
      throw "PYCOMPILE_PATH_NOT_FOUND file=$path"
    }
  }

  & $py -m py_compile @PyCompilePaths
  $compileExit = $LASTEXITCODE
}
Write-Host "COMPILE_EXIT=$compileExit"

if ($compileExit -ne 0) {
  throw "COMPILE_FAILED exitcode=$compileExit"
}

$hasRg = $null -ne (Get-Command rg -ErrorAction SilentlyContinue)
[string[]]$patternHits = @()

if ($Pattern.Trim().Length -gt 0) {
  if ($PatternFiles.Count -eq 0) {
    throw "PATTERN_FILES_REQUIRED"
  }

  foreach ($file in $PatternFiles) {
    if (-not (Test-Path $file)) {
      throw "PATTERN_FILE_NOT_FOUND file=$file"
    }
  }

  if ($hasRg) {
    [string[]]$patternHits = @(
      rg -n -S --no-heading `
        $Pattern `
        @PatternFiles
    )
  }
  else {
    [string[]]$patternHits = @(
      git grep -n -I -E `
        $Pattern `
        -- @PatternFiles
    )
  }

  $patternHits = @($patternHits | Where-Object { $_ -and $_.Trim().Length -gt 0 })
}

Write-Host "HAS_RG=$([int]$hasRg)"
Write-Host "PATTERN_HIT_COUNT=$($patternHits.Count)"
Write-Host "PATTERN_HITS_BEGIN"
$patternHits | ForEach-Object { Write-Host $_ }
Write-Host "PATTERN_HITS_END"

if ($Pattern.Trim().Length -gt 0 -and $patternHits.Count -eq 0) {
  throw "PATTERN_NOT_FOUND"
}

$pytestExit = 0
if ($PytestPaths.Count -gt 0) {
  $pytestScript = Join-Path $PSScriptRoot "run_targeted_pytest.ps1"
  if (-not (Test-Path $pytestScript)) {
    throw "TARGETED_PYTEST_SCRIPT_NOT_FOUND=$pytestScript"
  }

  $invoke = @{
    Paths = $PytestPaths
  }

  if ($QuietPytest) { $invoke["Quiet"] = $true }
  if ($StopOnFirstFailure) { $invoke["StopOnFirstFailure"] = $true }

  & $pytestScript @invoke
  $pytestExit = $LASTEXITCODE
}
Write-Host "PYTEST_EXIT=$pytestExit"

if ($pytestExit -ne 0) {
  throw "PYTEST_FAILED exitcode=$pytestExit"
}

[string[]]$statusAfter = @(git status --short)
$statusAfter = @($statusAfter | Where-Object { $_ -and $_.Trim().Length -gt 0 })

Write-Host "STATUS_AFTER_COUNT=$($statusAfter.Count)"
Write-Host "STATUS_AFTER_BEGIN"
$statusAfter | ForEach-Object { Write-Host $_ }
Write-Host "STATUS_AFTER_END"

$accept = 0
if (
  $compileExit -eq 0 -and
  $pytestExit -eq 0 -and
  ($Pattern.Trim().Length -eq 0 -or $patternHits.Count -gt 0)
) {
  $accept = 1
}
Write-Host "NUMERIC_ACCEPTANCE_PASS=$accept"

exit 0
