param(
  [ValidateSet("dev","ops","release","precommit","hook")] [string]$Mode = "dev"
)

Set-StrictMode -Version Latest
# A8-R28_STABLE_PYTEST_BASETEMP_BEGIN
# Keep pytest temporary cleanup outside the repository on Windows.
# This prevents repo-relative Temp* folders and reduces pytest cleanup KeyboardInterrupt risk.
$A8R28PytestBaseTempRoot = "C:\Temp"
if (-not (Test-Path -LiteralPath $A8R28PytestBaseTempRoot)) {
  New-Item -ItemType Directory -Path $A8R28PytestBaseTempRoot -Force | Out-Null
}
$A8R28PytestBaseTemp = (Join-Path $A8R28PytestBaseTempRoot ("trendify_pytest_{0}_{1}" -f $PID, (Get-Date -Format "yyyyMMdd_HHmmss"))) -replace "\\", "/"
if ([string]::IsNullOrWhiteSpace($env:PYTEST_ADDOPTS)) {
  $env:PYTEST_ADDOPTS = "--basetemp=$A8R28PytestBaseTemp"
} elseif ($env:PYTEST_ADDOPTS -notmatch "(^|\s)--basetemp(=|\s)") {
  $env:PYTEST_ADDOPTS = "$($env:PYTEST_ADDOPTS) --basetemp=$A8R28PytestBaseTemp"
}
Write-Host "PYTEST_BASETEMP_STABLE=1"
Write-Host "PYTEST_BASETEMP_PATH=$A8R28PytestBaseTemp"
Write-Host "PYTEST_ADDOPTS_EFFECTIVE=$env:PYTEST_ADDOPTS"
# A8-R28_STABLE_PYTEST_BASETEMP_END

# A8-R28_GATE_FAIL_HARD_BEGIN
function Invoke-A8R28CheckedPytest {
  param(
    [string]$Label,
    [string]$PythonExe,
    [object[]]$Targets
  )

  $tmpRoot = "C:\Temp"
  if (-not (Test-Path -LiteralPath $tmpRoot)) {
    New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null
  }

  $captureStamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $captureDir = Join-Path $tmpRoot ("trendify_gate_pytest_capture_{0}_{1}_{2}" -f $PID, $Label, $captureStamp)
  New-Item -ItemType Directory -Path $captureDir -Force | Out-Null

  $stdout = Join-Path $captureDir "$Label.stdout.txt"
  $stderr = Join-Path $captureDir "$Label.stderr.txt"

  Write-Host "A8R28_PYTEST_LABEL=$Label"
  Write-Host "A8R28_PYTEST_STDOUT=$stdout"
  Write-Host "A8R28_PYTEST_STDERR=$stderr"

  & $PythonExe -B -m pytest @($Targets) -q --tb=no > $stdout 2> $stderr
  $rc = $LASTEXITCODE
  if ($null -eq $rc) { $rc = 0 }

  [string]$outText = ""
  [string]$errText = ""

  if (Test-Path $stdout) {
    $rawOut = Get-Content $stdout -Raw
    if ($null -ne $rawOut) { $outText = [string]$rawOut }
  }

  if (Test-Path $stderr) {
    $rawErr = Get-Content $stderr -Raw
    if ($null -ne $rawErr) { $errText = [string]$rawErr }
  }

  $combined = "$outText`n$errText"
  $keyboardCount = ([regex]::Matches($combined, "KeyboardInterrupt")).Count
  $tracebackCount = ([regex]::Matches($combined, "Traceback")).Count
  $failedCount = ([regex]::Matches($combined, "FAILED")).Count

  Write-Host "A8R28_PYTEST_RC=$rc"
  Write-Host "A8R28_PYTEST_KEYBOARD_INTERRUPT_COUNT=$keyboardCount"
  Write-Host "A8R28_PYTEST_TRACEBACK_COUNT=$tracebackCount"
  Write-Host "A8R28_PYTEST_FAILED_TEXT_COUNT=$failedCount"

  Write-Host "A8R28_PYTEST_STDOUT_TAIL_BEGIN"
  if (Test-Path $stdout) { Get-Content $stdout -Tail 120 }
  Write-Host "A8R28_PYTEST_STDOUT_TAIL_END"

  if ((Test-Path $stderr) -and ((Get-Item $stderr).Length -gt 0)) {
    Write-Host "A8R28_PYTEST_STDERR_TAIL_BEGIN"
    Get-Content $stderr -Tail 120
    Write-Host "A8R28_PYTEST_STDERR_TAIL_END"
  }

  if ($keyboardCount -ne 0) {
    Write-Host "A8R28_GATE_FAIL_HARD_REASON=KeyboardInterrupt"
    exit 130
  }

  if ($tracebackCount -ne 0) {
    Write-Host "A8R28_GATE_FAIL_HARD_REASON=Traceback"
    exit 1
  }

  if ($failedCount -ne 0) {
    Write-Host "A8R28_GATE_FAIL_HARD_REASON=FailedText"
    exit 1
  }

  if ($rc -ne 0) {
    Write-Host "A8R28_GATE_FAIL_HARD_REASON=PytestNonZero"
    exit $rc
  }

  return 0
}
# A8-R28_GATE_FAIL_HARD_END

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

function Assert-NoBom([string]$Path) {
  if (-not (Test-Path $Path)) { Fail 16 ("MISSING_FILE={0}" -f $Path) }
  $b = [System.IO.File]::ReadAllBytes($Path)
  if ($b.Length -lt 3) { return }

  $h3 = (($b[0..2] | ForEach-Object { $_.ToString("X2") }) -join " ")
  if ($h3 -eq "EF BB BF") { Fail 17 ("BOM_UTF8_DETECTED file={0} head3={1}" -f $Path,$h3) }

  if ($b.Length -ge 2) {
    $h2 = (($b[0..1] | ForEach-Object { $_.ToString("X2") }) -join " ")
    if ($h2 -eq "FF FE") { Fail 18 ("BOM_UTF16LE_DETECTED file={0} head2={1}" -f $Path,$h2) }
    if ($h2 -eq "FE FF") { Fail 19 ("BOM_UTF16BE_DETECTED file={0} head2={1}" -f $Path,$h2) }
  }

  # Marker para pruebas automatizadas
  Write-Host ("NO_BOM_OK {0} HEAD3={1}" -f $Path,$h3)
}

$script:SynapsePythonVenvDetected = 0

function Resolve-SynapsePython {
  $candidates = @(
    "venv\Scripts\python.exe",
    ".venv\Scripts\python.exe",
    "venv/bin/python",
    ".venv/bin/python"
  )

  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      $script:SynapsePythonVenvDetected = 1
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  $script:SynapsePythonVenvDetected = 0
  return "python"
}

# Root guard
if (-not (Test-Path ".git")) { Fail 10 "NO .git (root incorrecto)" }
if (-not (Test-Path "pyproject.toml")) { Fail 11 "NO pyproject.toml (root incorrecto)" }

$pythonExe = Resolve-SynapsePython
Write-Host ("PYTHON_PATH={0}" -f $pythonExe)
Write-Host ("PYTHON_VENV_DETECTED={0}" -f $script:SynapsePythonVenvDetected)

if ($Mode -in @("hook","precommit","ops","release")) {
  if ($script:SynapsePythonVenvDetected -ne 1) {
    Fail 22 ("PYTHON_VENV_NOT_DETECTED mode={0} python={1}" -f $Mode,$pythonExe)
  }
}

# Guardrail anti-BOM
Assert-NoBom "pytest.ini"

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

# PRE clean: solo en ops/release. En precommit NO.
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
  $out = & $pythonExe -X utf8 -m synapse.infra.doctor 2>&1
  $doctorExit = $LASTEXITCODE
  $ov = ($out | Select-String -Pattern "OVERALL:" -ErrorAction SilentlyContinue | Select-Object -Last 1).Line
  if ($ov) { $doctorOverall = ($ov -replace "^.*OVERALL:\s*","").Trim() }
} catch {
  $doctorExit = 99
  $doctorOverall = "CRASH"
}
Write-Host ("DOCTOR_EXIT={0} DOCTOR_OVERALL={1}" -f $doctorExit,$doctorOverall)

# Doctor HARD en hook/precommit/ops/release.
if ($Mode -in @("hook","precommit","ops","release")) {
  if ($doctorExit -ne 0) { Fail 20 ("DOCTOR_EXIT={0}" -f $doctorExit) }
  if ($doctorOverall -notmatch "^GREEN") { Fail 21 ("DOCTOR_OVERALL={0}" -f $doctorOverall) }
}

# HOOK: rÃ¡pido, determinista, sin full pytest.
# El full gate se ejecuta manualmente antes de commit final en frentes F1.
if ($Mode -eq "hook") {
  $hookTargets = @(
    "tests/meta/test_safe_client_alerts.py::test_no_utf8_bom_in_tracked_policy_files",
    "tests/meta/test_safe_client_alerts.py::test_maybe_autopause_runtime_error_returns_structured_autopause_error",
    "tests/meta/test_safe_client_alerts.py::test_maybe_autopause_assertion_error_propagates_programming_errors",
    "tests/p0/test_eol_lf_gate_p0.py",
    "tests/meta/test_publisher_contracts.py"
  )

  "HOOK_TEST_TARGETS_FOUND={0}" -f $hookTargets.Count | Out-Host
  Invoke-A8R28CheckedPytest -Label "gate_pytest_hook_targets" -PythonExe $pythonExe -Targets @($hookTargets)
  $hookPytestExit = $LASTEXITCODE

  if ($hookPytestExit -ne 0) { Fail 31 ("HOOK_PYTEST_EXIT={0}" -f $hookPytestExit) }

  Write-Host "=== SYNAPSE F1 GATE: PASS ==="
  Write-Host ("ACCEPTANCE: hook_pytest_exit=0 hook_targets={0} doctor_exit={1} doctor_overall={2} python_venv_detected={3} bootstrap_used={4}" -f $hookTargets.Count,$doctorExit,$doctorOverall,$script:SynapsePythonVenvDetected,$bootstrapUsed)
  exit 0
}

# TESTS: HARD siempre (robusto si faltan dirs)
$roots = @("tests","buyer/tests","infra/tests","ops/tests")
$existing = @()
foreach ($r in $roots) { if (Test-Path $r) { $existing += $r } }
"TEST_ROOTS_FOUND={0}" -f $existing.Count | Out-Host
if ($existing.Count -eq 0) { Fail 30 "NO test roots found" }

Invoke-A8R28CheckedPytest -Label "gate_pytest_existing_roots" -PythonExe $pythonExe -Targets @($existing)
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
Write-Host ("ACCEPTANCE: pytest_exit=0 doctor_exit={0} doctor_overall={1} python_venv_detected={2} bootstrap_used={3}" -f $doctorExit,$doctorOverall,$script:SynapsePythonVenvDetected,$bootstrapUsed)
exit 0
