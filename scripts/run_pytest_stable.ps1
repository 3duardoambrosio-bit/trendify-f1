param(
  [string[]]$Targets = @("tests"),
  [int]$TimeoutSec = 120,
  [switch]$CollectOnly,
  [switch]$AllowPluginAutoload
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
# A8-R28_STABLE_PYTEST_BASETEMP_BEGIN
# Keep pytest temporary cleanup outside the repository on Windows.
# This prevents repo-relative Temp* folders and reduces pytest cleanup KeyboardInterrupt risk.
$A8R28PytestBaseTempRoot = "C:\Temp"
if (-not (Test-Path -LiteralPath $A8R28PytestBaseTempRoot)) {
  New-Item -ItemType Directory -Path $A8R28PytestBaseTempRoot -Force | Out-Null
}
$A8R28PytestBaseTemp = (Join-Path $A8R28PytestBaseTempRoot ("trendify_pytest_{0}_{1}" -f $PID, (Get-Date -Format "yyyyMMdd_HHmmss"))) -replace "\\", "/"
if ([string]::IsNullOrWhiteSpace($env:PYTEST_ADDOPTS)) {
  $env:PYTEST_ADDOPTS = "--basetemp=$A8R28PytestBaseTemp"
} elseif ($env:PYTEST_ADDOPTS -notmatch "(^|\s)--basetemp(=|\s)") {
  $env:PYTEST_ADDOPTS = "$($env:PYTEST_ADDOPTS) --basetemp=$A8R28PytestBaseTemp"
}
Write-Host "PYTEST_BASETEMP_STABLE=1"
Write-Host "PYTEST_BASETEMP_PATH=$A8R28PytestBaseTemp"
Write-Host "PYTEST_ADDOPTS_EFFECTIVE=$env:PYTEST_ADDOPTS"
# A8-R28_STABLE_PYTEST_BASETEMP_END

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$python = Join-Path $repo "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

$outRoot = "C:\Temp"
if (-not (Test-Path $outRoot)) {
  New-Item -ItemType Directory -Path $outRoot | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutPath = Join-Path $outRoot "trendify_pytest_stable_$stamp.stdout.txt"
$stderrPath = Join-Path $outRoot "trendify_pytest_stable_$stamp.stderr.txt"

function Quote-Arg {
  param([string]$Value)

  if ($null -eq $Value) {
    return '""'
  }

  $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
  return '"' + $escaped + '"'
}

$argsList = @("-m", "pytest")

foreach ($target in $Targets) {
  if ($null -ne $target -and $target.Trim().Length -gt 0) {
    $argsList += $target
  }
}

if ($CollectOnly) {
  $argsList += "--collect-only"
}

$argsList += "-q"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $python
$psi.Arguments = ($argsList | ForEach-Object { Quote-Arg $_ }) -join " "
$psi.WorkingDirectory = $repo
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.EnvironmentVariables["PYTHONPATH"] = $repo

if (-not $AllowPluginAutoload) {
  $psi.EnvironmentVariables["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
}

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi

$stdoutBuilder = New-Object System.Text.StringBuilder
$stderrBuilder = New-Object System.Text.StringBuilder

$outHandler = [System.Diagnostics.DataReceivedEventHandler]{
  param($sender, $eventArgs)
  if ($null -ne $eventArgs.Data) {
    [void]$stdoutBuilder.AppendLine($eventArgs.Data)
  }
}

$errHandler = [System.Diagnostics.DataReceivedEventHandler]{
  param($sender, $eventArgs)
  if ($null -ne $eventArgs.Data) {
    [void]$stderrBuilder.AppendLine($eventArgs.Data)
  }
}

$proc.add_OutputDataReceived($outHandler)
$proc.add_ErrorDataReceived($errHandler)

[void]$proc.Start()
$proc.BeginOutputReadLine()
$proc.BeginErrorReadLine()

$finished = $proc.WaitForExit($TimeoutSec * 1000)

if (-not $finished) {
  try { $proc.Kill() } catch {}
  $proc.WaitForExit()
  $exitCode = 124
  $timedOut = 1
} else {
  $proc.WaitForExit()
  $exitCode = $proc.ExitCode
  $timedOut = 0
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($stdoutPath, $stdoutBuilder.ToString(), $utf8NoBom)
[System.IO.File]::WriteAllText($stderrPath, $stderrBuilder.ToString(), $utf8NoBom)

Write-Host "PYTEST_STABLE_PYTHON=$python"
Write-Host "PYTEST_STABLE_TARGETS=$($Targets -join ',')"
Write-Host "PYTEST_STABLE_COLLECT_ONLY=$([int]$CollectOnly)"
Write-Host "PYTEST_STABLE_PLUGIN_AUTOLOAD=$([int]$AllowPluginAutoload)"
Write-Host "PYTEST_STABLE_TIMEOUT_SEC=$TimeoutSec"
Write-Host "PYTEST_STABLE_RC=$exitCode"
Write-Host "PYTEST_STABLE_TIMEOUT=$timedOut"
Write-Host "PYTEST_STABLE_STDOUT=$stdoutPath"
Write-Host "PYTEST_STABLE_STDERR=$stderrPath"

Write-Host "PYTEST_STABLE_STDOUT_BEGIN"
if (Test-Path $stdoutPath) {
  Get-Content $stdoutPath | Select-Object -First 120 | ForEach-Object { Write-Host $_ }
}
Write-Host "PYTEST_STABLE_STDOUT_END"

Write-Host "PYTEST_STABLE_STDERR_BEGIN"
if (Test-Path $stderrPath) {
  Get-Content $stderrPath | Select-Object -First 120 | ForEach-Object { Write-Host $_ }
}
Write-Host "PYTEST_STABLE_STDERR_END"

exit $exitCode