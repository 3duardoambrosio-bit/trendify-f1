param(
  [string]$Root = "."
)

$ErrorActionPreference = "Stop"

# Busca imports del v1 real (NO el _DEPRECATED)
$patterns = @(
  "from ops\.capital_shield import",
  "import ops\.capital_shield",
  "ops\.capital_shield\."
)

$hits = @()

$files = Get-ChildItem -Path $Root -Recurse -File -Filter "*.py" | Where-Object {
  $_.FullName -notmatch "capital_shield_v1_DEPRECATED\.py" -and
  $_.FullName -notmatch "\\docs\\" -and
  $_.FullName -notmatch "\\\.venv\\" -and
  $_.FullName -notmatch "\\build\\" -and
  $_.FullName -notmatch "\\dist\\"
}

foreach ($p in $patterns) {
  $m = $files | Select-String -Pattern $p
  if ($m) { $hits += $m }
}

$cnt = @($hits).Count
Write-Host ("capital_shield_v1_import_hits=" + $cnt)

if ($cnt -ne 0) {
  $hits | ForEach-Object {
    Write-Host ("HIT: " + $_.Path + ":" + $_.LineNumber + " :: " + $_.Line.Trim())
  }
  exit 1
}

exit 0
