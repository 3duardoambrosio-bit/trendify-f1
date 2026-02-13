param(
  [string]$Marker = "SYNAPSE F1 GATE: START"
)

$ErrorActionPreference="Stop"

Write-Host "=== F1: VERIFY LOCAL HOOKS (AUTO hooksPath) ===" -ForegroundColor Cyan

# [0] Snapshot
$root  = (git rev-parse --show-toplevel).Trim()
$head  = (git rev-parse --short HEAD).Trim()
$dirty = (git status --porcelain | Measure-Object).Count

"root=$root"
"head_short=$head"
"dirty_lines=$dirty"
if ($dirty -ne 0) { throw "F1 STOP: working tree debe estar limpio para auditoría" }

# [1] Effective hooksPath
$hooksPathEff = (git config --get core.hooksPath 2>$null)
"hooksPath_effective=" + (($hooksPathEff | ForEach-Object { $_.Trim() }) -join "")

if ([string]::IsNullOrWhiteSpace($hooksPathEff)) {
  $hooksDir = Join-Path $root ".git\hooks"
  "hooks_dir_mode=DEFAULT(.git/hooks)"
} else {
  $hp = $hooksPathEff.Trim()
  $hooksDir = if ([System.IO.Path]::IsPathRooted($hp)) { $hp } else { Join-Path $root $hp }
  "hooks_dir_mode=core.hooksPath"
}

"hooks_dir_effective=$hooksDir"

# [2] Validate pre-commit exists + marker
$hookPath = Join-Path $hooksDir "pre-commit"
$exists = [int](Test-Path $hookPath)
"pre_commit_exists=" + $exists

$bytes = 0
$markerHits = 0
if ($exists -eq 1) {
  $raw = Get-Content $hookPath -Raw
  $bytes = $raw.Length
  $markerHits = [int]($raw -match [regex]::Escape($Marker))
}
"pre_commit_bytes=" + $bytes
"marker_hits=" + $markerHits

# [3] Acceptance (numeric)
Write-Host "`n=== ACCEPTANCE (NUMERIC) ===" -ForegroundColor Green
"RULE_A pre_commit_exists == 1 => " + $exists
"RULE_B marker_hits == 1 => " + $markerHits
"RULE_C pre_commit_bytes >= 20 => " + [int]($bytes -ge 20)

if ($exists -ne 1) { throw "F1 STOP: pre-commit hook NO existe en hooksDir efectivo" }
if ($markerHits -ne 1) { throw "F1 STOP: hook no contiene marcador esperado (instalación corrupta)" }
if ($bytes -lt 20) { throw "F1 STOP: hook demasiado corto (probable corrupción)" }

"ACCEPTANCE_OK=1"

Write-Host "`n=== ESTADO COMPLETO ===" -ForegroundColor Cyan
"hook_path=$hookPath"
