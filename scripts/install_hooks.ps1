Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-LFFile {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][AllowEmptyString()][string]$Content
  )
  $dir = Split-Path $Path -Parent
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
  $lf = $Content -replace "`r`n","`n"
  [System.IO.File]::WriteAllText($Path,$lf,[System.Text.UTF8Encoding]::new($false))
}

if (-not (Test-Path ".git")) { throw "NO .git (root incorrecto)" }
if (-not (Test-Path "scripts\gate_f1.ps1")) { throw "NO scripts\gate_f1.ps1" }
if (-not (Test-Path ".githooks")) { New-Item -ItemType Directory -Path ".githooks" | Out-Null }

# Construir hook con STRINGS SINGLE-QUOTED (cero expansiÃ³n de $? o $PS)
$hook = @(
  '#!/bin/sh',
  'set -e',
  '',
  'if command -v pwsh >/dev/null 2>&1; then PS="pwsh"; else PS="powershell.exe"; fi',
  '',
  '$PS -NoProfile -ExecutionPolicy Bypass -File scripts/gate_f1.ps1 -Mode precommit',
  'exit $?'
) -join "`n"

Write-LFFile -Path ".githooks\pre-commit" -Content ($hook + "`n")
git config core.hooksPath .githooks | Out-Null
Write-Host "OK: core.hooksPath=.githooks"
Write-Host 'OK: wrote .githooks/pre-commit (exit $? literal)'
