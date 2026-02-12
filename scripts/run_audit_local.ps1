param()

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

chcp 65001 | Out-Null
$env:PYTHONUTF8="1"
$env:PYTHONIOENCODING="utf-8"
$env:NO_COLOR="1"

New-Item -ItemType Directory -Force ".audit_local" | Out-Null

pytest -q --ignore=exports 2>&1 | Out-File ".audit_local\pytest.txt" -Encoding utf8
python -m synapse.infra.doctor 2>&1 | Out-File ".audit_local\doctor.txt" -Encoding utf8

Get-ChildItem -Recurse -Filter *.py ops,synapse,infra,scripts,buyer |
  Where-Object { $_.FullName -notmatch "\\scripts\\hygiene_sweep_fase3\.py$" } |
  Select-String -Pattern "^\s*except\s*:\s*$" |
  ForEach-Object { $_.Path + ":" + $_.LineNumber + "  " + $_.Line.Trim() } |
  Out-File ".audit_local\bare_except.txt" -Encoding utf8

Get-ChildItem -Recurse -Filter *.py ops,synapse,infra,scripts,buyer |
  Where-Object { $_.FullName -notmatch "\\scripts\\hygiene_sweep_fase3\.py$" } |
  Select-String -Pattern "utcnow\(" |
  ForEach-Object { $_.Path + ":" + $_.LineNumber + "  " + $_.Line.Trim() } |
  Out-File ".audit_local\utcnow.txt" -Encoding utf8

$bare = (Get-Content ".audit_local\bare_except.txt" | Measure-Object -Line).Lines
$utc  = (Get-Content ".audit_local\utcnow.txt" | Measure-Object -Line).Lines

@(
  "bare_except_lines=$bare"
  "utcnow_lines=$utc"
  ""
  "--- PYTEST (tail) ---"
) + (Get-Content ".audit_local\pytest.txt" -Tail 12) + @(
  ""
  "--- DOCTOR (tail) ---"
) + (Get-Content ".audit_local\doctor.txt" -Tail 20) |
  Out-File ".audit_local\summary.txt" -Encoding utf8

Write-Host "AUDIT LOCAL listo -> .audit_local\summary.txt"
Write-Host "bare_except_lines=$bare | utcnow_lines=$utc"