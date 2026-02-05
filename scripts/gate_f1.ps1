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

# DEV auto-bootstrap (SOLO si faltan fixtures)
function Get-MissingFixtures {
  $paths = @(
    "data\evidence\launch_candidates_dropi_dump_f1_v2.json",
    "data\evidence\products\toy-001.json",
    "data\catalog\candidates_real.csv",
    "data\launch\shortlist_dropi_f1.csv"
  )
  $missing = New-Object System.Collections.Generic.List[string]
  foreach ($p in $paths) { if (-not (Test-Path $p)) { $missing.Add($p) } }
  return ,$missing
}

$bootstrapUsed = 0
if ($Mode -eq "dev") {
  $missing = Get-MissingFixtures
  "MISSING_FIXTURES_COUNT={0}" -f $missing.Count | Out-Host
  if ($missing.Count -gt 0) {
    $bootstrap = "scripts\bootstrap_fixtures_dev.ps1"
    if (-not (Test-Path $bootstrap)) {
      $missing | ForEach-Object { "MISSING=$_"; } | Out-Host
      Fail 12 "NO bootstrap script: scripts/bootstrap_fixtures_dev.ps1"
    }

    Write-Host "=== DEV AUTO-BOOTSTRAP: START ==="
    $missing | ForEach-Object { "MISSING=$_"; } | Out-Host

    # Protege contra side-effects trackeados
    $preTracked = Status-Lines

    & powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap
    $bexit = $LASTEXITCODE
    "BOOTSTRAP_EXIT={0}" -f $bexit | Out-Host
    if ($bexit -ne 0) { Fail 13 ("BOOTSTRAP_EXIT={0}" -f $bexit) }

    $missing2 = Get-MissingFixtures
    "MISSING_AFTER_BOOTSTRAP={0}" -f $missing2.Count | Out-Host
    if ($missing2.Count -gt 0) {
      $missing2 | ForEach-Object { "STILL_MISSING=$_"; } | Out-Host
      Fail 14 "BOOTSTRAP_INCOMPLETE"
    }

    # Si esto ensucia el repo (archivos trackeados/untracked no ignorados), fallamos duro
    $postTracked = Status-Lines
    "STATUS_LINES_PRE={0} STATUS_LINES_POST={1}" -f $preTracked,$postTracked | Out-Host
    if ($postTracked -ne 0) {
      git status --porcelain | Out-Host
      Fail 15 "BOOTSTRAP_DIRTY_REPO (asegura gitignore para data/ y exports/)"
    }

    Write-Host "=== DEV AUTO-BOOTSTRAP: OK ==="
    $bootstrapUsed = 1
  }
}
"BOOTSTRAP_USED={0}" -f $bootstrapUsed | Out-Host

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

# TESTS: HARD siempre (pero robusto si faltan dirs)
$roots = @("tests","buyer/tests","infra/tests","ops/tests")
$existing = @()
foreach ($r in $roots) { if (Test-Path $r) { $existing += $r } }
"TEST_ROOTS_FOUND={0}" -f $existing.Count | Out-Host
if ($existing.Count -eq 0) { Fail 30 "NO test roots found" }

& pytest @($existing) -q --tb=no
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
Write-Host ("ACCEPTANCE: pytest_exit=0 doctor_exit={0} doctor_overall={1} bootstrap_used={2}" -f $doctorExit,$doctorOverall,$bootstrapUsed)
exit 0