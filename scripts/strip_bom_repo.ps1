# scripts/strip_bom_repo.ps1
# Remove UTF-8 BOM from source files (surgical)
# marker: STRIP_BOM_REPO_2026-01-21_V2

param(
  [string]$Root = "."
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path $Root).Path

$ignoreDirs = @(".git",".venv","venv","__pycache__", ".pytest_cache","node_modules","data","secrets")

$exts = @(".py",".ps1",".md",".json",".html",".toml",".ini",".txt")
$specialNames = @("pytest.ini","pyproject.toml")

$BOM = [byte[]](0xEF,0xBB,0xBF)

function Is-Ignored([string]$fullPath) {
  $parts = $fullPath -split "[\\/]"
  foreach ($d in $ignoreDirs) {
    if ($parts -contains $d) { return $true }
  }
  return $false
}

[int]$checked = 0
[int]$fixed = 0

Get-ChildItem -Path $repo -Recurse -File | ForEach-Object {
  $full = $_.FullName
  if (Is-Ignored $full) { return }

  $name = $_.Name
  $ext  = $_.Extension.ToLowerInvariant()

  if (($exts -notcontains $ext) -and ($specialNames -notcontains $name)) { return }

  $checked++

  try { $bytes = [System.IO.File]::ReadAllBytes($full) } catch { return }

  if ($bytes.Length -ge 3 -and $bytes[0] -eq $BOM[0] -and $bytes[1] -eq $BOM[1] -and $bytes[2] -eq $BOM[2]) {
    $newBytes = New-Object byte[] ($bytes.Length - 3)
    [Array]::Copy($bytes, 3, $newBytes, 0, $newBytes.Length)
    [System.IO.File]::WriteAllBytes($full, $newBytes)
    $fixed++
  }
}

Write-Host "STRIP_BOM: OK" -ForegroundColor Green
Write-Host ("Checked: {0} files" -f $checked) -ForegroundColor Cyan
Write-Host ("Fixed BOM: {0} files" -f $fixed) -ForegroundColor Cyan