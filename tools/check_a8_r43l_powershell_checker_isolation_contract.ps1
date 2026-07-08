param(
  [string]$RepoRoot = (Get-Location).Path,
  [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function CountOf($x) {
  if ($null -eq $x) { return 0 }
  return @($x).Count
}

$repo = (Resolve-Path $RepoRoot).Path

$files = @()
$files += Get-ChildItem -Path (Join-Path $repo "tools") -Filter "check_a8_*.ps1" -File -ErrorAction Stop
$files += Get-ChildItem -Path (Join-Path $repo "scripts") -Filter "*.ps1" -File -ErrorAction Stop
$files = @($files | Sort-Object FullName -Unique)

$parse = @()
$badAssign = @()
$badReturn = @()
$markers = 0

foreach ($f in $files) {
  $rel = $f.FullName.Substring($repo.Length).TrimStart("\", "/").Replace("\", "/")

  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$errors) | Out-Null

  foreach ($e in @($errors)) {
    $parse += ('{0}:{1}:{2}' -f $rel, $e.Extent.StartLineNumber, $e.Message)
  }

  if ((CountOf $errors) -ne 0) {
    continue
  }

  $lines = @(Get-Content -Path $f.FullName -Encoding UTF8)
  $text = $lines -join "`n"

  $markers += ([regex]::Matches($text, "A8_R43H_LASTEXITCODE_STRICTMODE_SAFE")).Count
  $markers += ([regex]::Matches($text, "A8_R43L_LASTEXITCODE_STRICTMODE_SAFE")).Count

  for ($i = 0; $i -lt $lines.Count; $i++) {
    $line = [string]$lines[$i]
    $start = [Math]::Max(0, $i - 10)
    $end = [Math]::Min($lines.Count - 1, $i + 10)
    $window = ($lines[$start..$end] -join "`n")

    $safe = (
      $window -match "Get-Variable\s+-Name\s+LASTEXITCODE" -or
      $window -match "A8_R43H_LASTEXITCODE_STRICTMODE_SAFE" -or
      $window -match "A8_R43L_LASTEXITCODE_STRICTMODE_SAFE"
    )

    if ($line -match '^\s*\$[A-Za-z_][A-Za-z0-9_]*\s*=\s*\$LASTEXITCODE\s*$' -and -not $safe) {
      $badAssign += ('{0}:{1}:{2}' -f $rel, ($i + 1), $line.Trim())
    }

    if ($line -match '^\s*return\s+\$LASTEXITCODE\s*$' -and -not $safe) {
      $badReturn += ('{0}:{1}:{2}' -f $rel, ($i + 1), $line.Trim())
    }
  }
}

$result = [ordered]@{
  pass = ((CountOf $parse) -eq 0 -and (CountOf $badAssign) -eq 0 -and (CountOf $badReturn) -eq 0 -and $markers -ge 11)
  scanned_file_count = CountOf $files
  parse_error_count = CountOf $parse
  unsafe_assignment_count = CountOf $badAssign
  unsafe_return_count = CountOf $badReturn
  marker_total = $markers
  parse_errors = @($parse)
  unsafe_assignments = @($badAssign)
  unsafe_returns = @($badReturn)
}

Write-Host "A8_R43L_SCANNED_FILE_COUNT=$($result.scanned_file_count)"
Write-Host "A8_R43L_PARSE_ERROR_COUNT=$($result.parse_error_count)"
Write-Host "A8_R43L_UNSAFE_LASTEXITCODE_ASSIGNMENT_COUNT=$($result.unsafe_assignment_count)"
Write-Host "A8_R43L_UNSAFE_RETURN_LASTEXITCODE_COUNT=$($result.unsafe_return_count)"
Write-Host "A8_R43L_STRICTMODE_SAFE_MARKER_TOTAL=$($result.marker_total)"

if (-not [string]::IsNullOrWhiteSpace($ReportPath)) {
  $dir = Split-Path -Parent $ReportPath
  if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }

  $result | ConvertTo-Json -Depth 8 | Set-Content -Path $ReportPath -Encoding ascii
  Write-Host "A8_R43L_REPORT_PATH=$ReportPath"
}

if (-not $result.pass) {
  Write-Host "A8_R43L_FAILURES_BEGIN"
  foreach ($item in @($parse + $badAssign + $badReturn)) {
    Write-Host $item
  }
  Write-Host "A8_R43L_FAILURES_END"
  Write-Host "A8_R43L_PASS=0"
  exit 1
}

Write-Host "A8_R43L_PASS=1"
exit 0