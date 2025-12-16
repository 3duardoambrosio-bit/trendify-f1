param(
  [switch]$Fast
)
$ErrorActionPreference = "Stop"
cd (Split-Path $PSScriptRoot -Parent)

Write-Host "PYTHON:" (python --version)
python -m compileall -q .

if ($Fast) {
  pytest -q
} else {
  pytest
}