[CmdletBinding()]
param(
  [switch]$SkipPytest
)

$ErrorActionPreference = "Stop"

Write-Host "=== F1 PRE-FLIGHT (NO MUTATIONS) ==="

Write-Host "`n[1] HEAD + clean"
$head  = (git rev-parse --short HEAD)
$dirty = (git status --porcelain | Measure-Object).Count
"HEAD_SHORT=$head"
"dirty_lines=$dirty"
if ($dirty -ne 0) { throw "F1 STOP: working tree no está limpio" }

Write-Host "`n[2] EOL truth (git ls-files --eol) critical set"
$paths = @(
  ".gitattributes",
  ".gitignore",
  ".github/workflows/f1.yml",
  "ops/dropi_dump_ingest.py",
  "synapse/meta_auth_check.py",
  "synapse/creative_assets_build.py",
  "tests/p0/test_repo_compiles_p0.py",
  "tests/p0/test_eol_lf_gate_p0.py"
)


$eol = git ls-files --eol -- $paths
$eol | ForEach-Object { $_ }

$bad = @()
foreach ($ln in $eol) {
  if ($ln -notmatch "\bi/lf\b" -or $ln -notmatch "\bw/lf\b") { $bad += $ln }
}
"eol_bad_lines=$($bad.Count)"
if ($bad.Count -ne 0) {
  $bad | ForEach-Object { "BAD_EOLOPT: $_" }
  throw "F1 STOP: hay archivos críticos no-LF"
}

if (-not $SkipPytest) {
  Write-Host "`n[3] pytest (captura output sin pipe)"
  New-Item -Force -ItemType Directory .tmp | Out-Null
  cmd /c "pytest -q > .tmp\pytest_out.txt 2>&1"
  "pytest_exit=$LASTEXITCODE"
  if ($LASTEXITCODE -ne 0) {
    Get-Content .tmp\pytest_out.txt -TotalCount 260
    throw "F1 STOP: pytest falló"
  }

  Write-Host "`n[4] warnings prohibidos (invalid escape sequence)"
  $hits = (Select-String -Path .tmp\pytest_out.txt -SimpleMatch "invalid escape sequence" -ErrorAction SilentlyContinue | Measure-Object).Count
  "invalid_escape_hits=$hits"
  if ($hits -ne 0) {
    Select-String -Path .tmp\pytest_out.txt -SimpleMatch "invalid escape sequence"
    throw "F1 STOP: warnings prohibidos detectados"
  }
} else {
  Write-Host "`n[3] pytest: SKIPPED (SkipPytest=1)"
  "pytest_exit=SKIPPED"
  "invalid_escape_hits=SKIPPED"
}

Write-Host "`nACCEPTANCE: dirty_lines=0 AND eol_bad_lines=0 AND pytest_exit in {0,SKIPPED} AND invalid_escape_hits in {0,SKIPPED}" -ForegroundColor Green
