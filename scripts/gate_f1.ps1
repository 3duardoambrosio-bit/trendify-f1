param(
  [ValidateSet("dev","ops","release","precommit")] [string]$Mode = "dev"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Write-Host "=== SYNAPSE F1 GATE: START ==="
Write-Host ("MODE={0}" -f $Mode)

# UTF-8 hardening (evita UnicodeEncodeError en Windows cp1252)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

function Status-Lines { return (git status --porcelain | Measure-Object).Count }
function Fail([int]$Code,[string]$Msg) { Write-Host "=== SYNAPSE F1 GATE: FAIL ==="; Write-Host $Msg; exit $Code }

# Root guard
if (-not (Test-Path ".git")) { Fail 10 "NO .git (root incorrecto)" }
if (-not (Test-Path "pyproject.toml")) { Fail 11 "NO pyproject.toml (root incorrecto)" }

# PRE clean: solo en ops/release (y opcional en dev). En precommit NO.
if ($Mode -in @("ops","release")) {
  $pre = Status-Lines
  if ($pre -ne 0) {
    git status --porcelain | Out-Host
    Fail 2 ("PRE_STATUS_LINES={0}" -f $pre)
  }
}

# DOCTOR
$doctorExit = 0
$doctorOverall = "UNKNOWN"
try {
  # python -X utf8 fuerza UTF-8 mode (mejor que pelear con cp1252)
  $out = & python -X utf8 -m synapse.infra.doctor 2>&1
  $doctorExit = $LASTEXITCODE
  $ov = ($out | Select-String -Pattern "OVERALL:" -ErrorAction SilentlyContinue | Select-Object -Last 1).Line
  if ($ov) { $doctorOverall = ($ov -replace "^.*OVERALL:\s*","").Trim() }
} catch {
  $doctorExit = 99
  $doctorOverall = "CRASH"
}
Write-Host ("DOCTOR_EXIT={0} DOCTOR_OVERALL={1}" -f $doctorExit,$doctorOverall)

# Doctor HARD en ops/release; SOFT en dev/precommit
if ($Mode -in @("ops","release")) {
  if ($doctorExit -ne 0) { Fail 20 ("DOCTOR_EXIT={0}" -f $doctorExit) }
  if ($doctorOverall -notmatch "^GREEN") { Fail 21 ("DOCTOR_OVERALL={0}" -f $doctorOverall) }
}

# TESTS: HARD siempre
& pytest tests/ buyer/tests/ infra/tests/ ops/tests/ -q --tb=no
$pytestExit = $LASTEXITCODE
if ($pytestExit -ne 0) { Fail 3 ("PYTEST_EXIT={0}" -f $pytestExit) }

# POST clean: solo en ops/release
if ($Mode -in @("ops","release")) {
  $post = Status-Lines
  if ($post -ne 0) {
    git status --porcelain | Out-Host
    Fail 4 ("POST_STATUS_LINES={0}" -f $post)
  }
}

Write-Host "=== SYNAPSE F1 GATE: PASS ==="
Write-Host ("ACCEPTANCE: pytest_exit=0 doctor_exit={0} doctor_overall={1}" -f $doctorExit,$doctorOverall)
exit 0