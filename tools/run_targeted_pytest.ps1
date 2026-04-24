[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string[]]$Paths,

  [switch]$Quiet,
  [switch]$StopOnFirstFailure
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$py = Join-Path $repo "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

foreach ($path in $Paths) {
  if (-not (Test-Path $path)) {
    throw "TEST_PATH_NOT_FOUND file=$path"
  }
}

$args = @("-m", "pytest")
if ($Quiet) { $args += "-q" }
if ($StopOnFirstFailure) { $args += "-x" }
$args += $Paths

Write-Host "REPO=$repo"
Write-Host "PYTHON=$py"
Write-Host "PYTEST_PATH_COUNT=$($Paths.Count)"
Write-Host "PYTEST_PATHS_BEGIN"
$Paths | ForEach-Object { Write-Host $_ }
Write-Host "PYTEST_PATHS_END"

& $py @args
$exitCode = $LASTEXITCODE

Write-Host "PYTEST_EXIT=$exitCode"
exit $exitCode
