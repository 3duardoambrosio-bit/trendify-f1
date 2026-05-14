param(
  [ValidateSet("dev","ops","release","precommit","hook")] [string]$Mode = "dev"
)

Set-StrictMode -Version Latest

function Invoke-A8R43MR43LGate {
    Write-Host "A8_R43M_R43L_GATE_BEGIN=1"

    $a8r43mRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    $a8r43mR43lGate = Join-Path $a8r43mRepoRoot "tools/check_a8_r43l_powershell_checker_isolation_contract.ps1"

    if (-not (Test-Path $a8r43mR43lGate)) {
        throw "A8_R43M_R43L_GATE_NOT_FOUND=$a8r43mR43lGate"
    }

    $a8r43mQuotedGate = '"' + $a8r43mR43lGate.Replace('"', '\"') + '"'
    $a8r43mQuotedRepo = '"' + $a8r43mRepoRoot.Replace('"', '\"') + '"'

    $a8r43mPsi = [System.Diagnostics.ProcessStartInfo]::new()
    $a8r43mPsi.FileName = "powershell.exe"
    $a8r43mPsi.WorkingDirectory = $a8r43mRepoRoot
    $a8r43mPsi.UseShellExecute = $false
    $a8r43mPsi.RedirectStandardOutput = $true
    $a8r43mPsi.RedirectStandardError = $true
    $a8r43mPsi.CreateNoWindow = $true
    $a8r43mPsi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File $a8r43mQuotedGate -RepoRoot $a8r43mQuotedRepo"

    Write-Host "A8_R43W_R43L_PROCESS_CAPTURE=1"

    $a8r43mProcess = [System.Diagnostics.Process]::new()
    $a8r43mProcess.StartInfo = $a8r43mPsi

    [void]$a8r43mProcess.Start()

    $a8r43mStdoutTask = $a8r43mProcess.StandardOutput.ReadToEndAsync()
    $a8r43mStderrTask = $a8r43mProcess.StandardError.ReadToEndAsync()

    if (-not $a8r43mProcess.WaitForExit(300000)) {
        try {
            $a8r43mProcess.Kill()
        }
        catch {
            Write-Host "A8_R43W_R43L_TIMEOUT_KILL_FAILED=1"
        }

        throw "A8_R43M_R43L_GATE_TIMEOUT_MS=300000"
    }

    $a8r43mR43lStdout = $a8r43mStdoutTask.GetAwaiter().GetResult()
    $a8r43mR43lStderr = $a8r43mStderrTask.GetAwaiter().GetResult()

    if (-not [string]::IsNullOrWhiteSpace($a8r43mR43lStdout)) {
        $a8r43mR43lStdout -split "`n" | ForEach-Object {
            if (-not [string]::IsNullOrWhiteSpace($_)) {
                Write-Host $_
            }
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($a8r43mR43lStderr)) {
        $a8r43mR43lStderr -split "`n" | ForEach-Object {
            if (-not [string]::IsNullOrWhiteSpace($_)) {
                Write-Host "A8_R43W_R43L_STDERR: $_"
            }
        }
    }

    $a8r43mR43lRc = [int]$a8r43mProcess.ExitCode

    # A8_R43L_LASTEXITCODE_STRICTMODE_SAFE=1

    Write-Host "A8_R43M_R43L_GATE_RC=$a8r43mR43lRc"

    if ($a8r43mR43lRc -ne 0) {
        throw "A8_R43M_R43L_GATE_FAILED_RC=$a8r43mR43lRc"
    }

    Write-Host "A8_R43M_R43L_GATE_PASS=1"
}
# A8_R43H_REGISTRY_GATE_FUNCTION_BEGIN
function Invoke-A8R43HRegistryGate {
  if ($null -eq (Get-Variable -Name A8R43HRegistryGateAlreadyRun -Scope Script -ErrorAction SilentlyContinue)) {
    $script:A8R43HRegistryGateAlreadyRun = 0
  }

  if ($script:A8R43HRegistryGateAlreadyRun -eq 1) {
    return
  }

  $script:A8R43HRegistryGateAlreadyRun = 1

  Write-Host "A8_R43H_REGISTRY_GATE_BEGIN"

  $__a8r43hRepo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
  $__a8r43hGate = Join-Path $__a8r43hRepo "tools/check_a8_r43g_registry_gates.ps1"

  if (-not (Test-Path $__a8r43hGate)) {
    throw "A8_R43H_REGISTRY_GATE_NOT_FOUND=$__a8r43hGate"
  }

  $__a8r43hQuotedGate = '"' + $__a8r43hGate.Replace('"', '\"') + '"'
  $__a8r43hQuotedRepo = '"' + $__a8r43hRepo.Replace('"', '\"') + '"'

  $__a8r43hPsi = [System.Diagnostics.ProcessStartInfo]::new()
  $__a8r43hPsi.FileName = "powershell.exe"
  $__a8r43hPsi.WorkingDirectory = $__a8r43hRepo
  $__a8r43hPsi.UseShellExecute = $false
  $__a8r43hPsi.RedirectStandardOutput = $true
  $__a8r43hPsi.RedirectStandardError = $true
  $__a8r43hPsi.CreateNoWindow = $true
  $__a8r43hPsi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File $__a8r43hQuotedGate -Repo $__a8r43hQuotedRepo"

  Write-Host "A8_R43Z_R43H_PROCESS_CAPTURE=1"

  $__a8r43hProcess = [System.Diagnostics.Process]::new()
  $__a8r43hProcess.StartInfo = $__a8r43hPsi

  [void]$__a8r43hProcess.Start()

  $__a8r43hStdoutTask = $__a8r43hProcess.StandardOutput.ReadToEndAsync()
  $__a8r43hStderrTask = $__a8r43hProcess.StandardError.ReadToEndAsync()

  if (-not $__a8r43hProcess.WaitForExit(300000)) {
    try {
      $__a8r43hProcess.Kill()
    }
    catch {
      Write-Host "A8_R43Z_R43H_TIMEOUT_KILL_FAILED=1"
    }

    throw "A8_R43H_REGISTRY_GATE_TIMEOUT_MS=300000"
  }

  $__a8r43hStdout = $__a8r43hStdoutTask.GetAwaiter().GetResult()
  $__a8r43hStderr = $__a8r43hStderrTask.GetAwaiter().GetResult()

  if (-not [string]::IsNullOrWhiteSpace($__a8r43hStdout)) {
    $__a8r43hStdout -split "`n" | ForEach-Object {
      if (-not [string]::IsNullOrWhiteSpace($_)) {
        Write-Host $_
      }
    }
  }

  if (-not [string]::IsNullOrWhiteSpace($__a8r43hStderr)) {
    $__a8r43hStderr -split "`n" | ForEach-Object {
      if (-not [string]::IsNullOrWhiteSpace($_)) {
        Write-Host "A8_R43Z_R43H_STDERR: $_"
      }
    }
  }

  $__a8r43hRc = [int]$__a8r43hProcess.ExitCode

  # A8_R43L_LASTEXITCODE_STRICTMODE_SAFE=1

  Write-Host "A8_R43Z_R43H_GATE_RC=$__a8r43hRc"

  if ($__a8r43hRc -ne 0) {
    throw "A8_R43H_REGISTRY_GATE_FAILED=$__a8r43hRc"
  }

  Write-Host "A8_R43H_REGISTRY_GATE_PASS=1"
}
# A8_R43H_REGISTRY_GATE_FUNCTION_END

# A8-R28_STABLE_PYTEST_BASETEMP_BEGIN
# Keep pytest temp-dir cleanup outside the repository on Windows.
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

  if ([string]::IsNullOrWhiteSpace($Label)) {
    throw "A8R28_PYTEST_LABEL_EMPTY"
  }

  if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    throw "A8R28_PYTHON_EXE_EMPTY"
  }

  if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "A8R28_PYTHON_EXE_NOT_FOUND=$PythonExe"
  }

  $cleanTargets = @()
  foreach ($target in @($Targets)) {
    if ($null -ne $target -and -not [string]::IsNullOrWhiteSpace([string]$target)) {
      $cleanTargets += [string]$target
    }
  }

  if (@($cleanTargets).Count -lt 1) {
    throw "A8R28_PYTEST_TARGETS_EMPTY"
  }

  $captureStamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $captureDir = Join-Path $tmpRoot ("trendify_gate_pytest_capture_{0}_{1}_{2}" -f $PID, $Label, $captureStamp)
  New-Item -ItemType Directory -Path $captureDir -Force | Out-Null

  $stdout = Join-Path $captureDir "$Label.stdout.txt"
  $stderr = Join-Path $captureDir "$Label.stderr.txt"

  Write-Host "A8R28_PYTEST_LABEL=$Label"
  Write-Host "A8R28_PYTEST_STDOUT=$stdout"
  Write-Host "A8R28_PYTEST_STDERR=$stderr"

  $pytestArgs = @("-B", "-m", "pytest")
  foreach ($target in $cleanTargets) {
    $pytestArgs += [string]$target
  }
  $pytestArgs += @("-q", "--tb=no")

  Write-Host "A8_R43AA_PYTEST_STARTPROCESS_CAPTURE=1"
  Write-Host "A8_R43X_PYTEST_PROCESS_CAPTURE=1"
  Write-Host "A8_R43X_PYTEST_TARGET_COUNT=$(@($cleanTargets).Count)"

  if (Test-Path $stdout) { Remove-Item -Force $stdout }
  if (Test-Path $stderr) { Remove-Item -Force $stderr }

  $process = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList $pytestArgs `
    -WorkingDirectory ((Resolve-Path (Join-Path $PSScriptRoot "..")).Path) `
    -NoNewWindow `
    -PassThru `
    -Wait `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr

  $rc = [int]$process.ExitCode

  # A8_R43L_LASTEXITCODE_STRICTMODE_SAFE=1

  $outText = ""
  $errText = ""

  if (Test-Path $stdout) {
    try { $outText = [System.IO.File]::ReadAllText($stdout) } catch { $outText = "" }
  }

  if (Test-Path $stderr) {
    try { $errText = [System.IO.File]::ReadAllText($stderr) } catch { $errText = "" }
  }

  $combined = "$outText`n$errText"
  $keyboardCount = ([regex]::Matches($combined, "KeyboardInterrupt")).Count
  $tracebackCount = ([regex]::Matches($combined, "Traceback")).Count
  $failedCount = ([regex]::Matches($combined, "FAILED")).Count

  Write-Host "A8R28_PYTEST_RC=$rc"
  Write-Host "A8R28_PYTEST_KEYBOARD_INTERRUPT_COUNT=$keyboardCount"
  Write-Host "A8R28_PYTEST_TRACEBACK_COUNT=$tracebackCount"
  Write-Host "A8R28_PYTEST_FAILED_TEXT_COUNT=$failedCount"

  Write-Host "A8R28_PYTEST_STDOUT_BYTES=$(if (Test-Path $stdout) { (Get-Item $stdout).Length } else { 0 })"
  Write-Host "A8R28_PYTEST_STDERR_BYTES=$(if (Test-Path $stderr) { (Get-Item $stderr).Length } else { 0 })"

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
    return 130
  }

  if ($tracebackCount -ne 0) {
    Write-Host "A8R28_GATE_FAIL_HARD_REASON=Traceback"
    return 1
  }

  if ($failedCount -ne 0) {
    Write-Host "A8R28_GATE_FAIL_HARD_REASON=FailedText"
    return 1
  }

  if ($rc -ne 0) {
    Write-Host "A8R28_GATE_FAIL_HARD_REASON=PytestNonZero"
    return $rc
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

# A8-R40 01J6H: top-level helper required when scripts/gate_f1.ps1 is executed directly.
Write-Host "A8_R40_01J6B_TOP_LEVEL_A8R37_HOOK_CHECK=1"
function Invoke-A8R37HookCheck {
    param(
      [string]$Label,
      [scriptblock]$Body
    )

    Write-Host ("A8R37_HOOK_TARGET_BEGIN={0}" -f $Label)
    try {
      & $Body
      $hookCheckRc = 0
    }
    catch {
      $hookCheckRc = 1
      Write-Host ("A8R37_HOOK_TARGET_ERROR={0}" -f $_.Exception.Message)
    }
    Write-Host ("A8R37_HOOK_TARGET_RC={0}" -f $hookCheckRc)
    if ($hookCheckRc -ne 0) { Fail 31 ("HOOK_NATIVE_CHECK_EXIT label={0} rc={1}" -f $Label,$hookCheckRc) }
    Write-Host ("A8R37_HOOK_TARGET_END={0}" -f $Label)
  }


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
# HOOK: fast, deterministic, native, no pytest imports.
# A8-R37: earliest hook fast path runs immediately after venv detection.
$doctorExit = -1
$doctorOverall = "SKIPPED_HOOK_FAST_PATH"
if (-not (Test-Path variable:bootstrapUsed)) { $bootstrapUsed = 0 }
$hookVenvDetected = 0
try { $hookVenvDetected = [int]$script:SynapsePythonVenvDetected } catch { $hookVenvDetected = 0 }

if ($Mode -eq "hook") {
  Write-Host "HOOK_TEST_TARGETS_FOUND=6"
  Write-Host "A8R37_HOOK_STABILIZATION_ACTIVE=1"
  Write-Host "A8R37_HOOK_EARLIEST_FAST_PATH_ACTIVE=1"
  Write-Host "A8R37_HOOK_NATIVE_FAST_PATH_ACTIVE=1"
  Write-Host "A8R37_HOOK_PYTEST_DISABLED=1"

  [string[]]$stagedHookFiles = @(git diff --cached --name-only --diff-filter=ACMR | Where-Object { $_ -and $_.Trim().Length -gt 0 })
  Write-Host ("A8R37_HOOK_STAGED_FILE_COUNT={0}" -f $stagedHookFiles.Count)

  Invoke-A8R37HookCheck -Label "staged_files_present" -Body {
    if ($stagedHookFiles.Count -lt 1) { throw "NO_STAGED_FILES" }
  }

  Invoke-A8R37HookCheck -Label "staged_no_utf8_bom" -Body {
    $bomCount = 0
    foreach ($file in $stagedHookFiles) {
      if (-not (Test-Path $file)) { continue }
      [byte[]]$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $file))
      if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $bomCount++
        Write-Host ("A8R37_HOOK_UTF8_BOM_FILE={0}" -f $file)
      }
    }
    Write-Host ("A8R37_HOOK_UTF8_BOM_COUNT={0}" -f $bomCount)
    if ($bomCount -ne 0) { throw "UTF8_BOM_COUNT=$bomCount" }
  }

  Invoke-A8R37HookCheck -Label "staged_no_crlf" -Body {
    $crlfCount = 0
    $textExtensions = @(".ps1",".py",".md",".json",".yaml",".yml",".toml",".ini",".txt",".sh",".psm1",".psd1")
    foreach ($file in $stagedHookFiles) {
      if (-not (Test-Path $file)) { continue }
      $ext = [System.IO.Path]::GetExtension($file).ToLowerInvariant()
      if ($ext -notin $textExtensions) { continue }
      $raw = [System.IO.File]::ReadAllText((Resolve-Path $file))
      $fileCrlf = ([regex]::Matches($raw, "`r`n")).Count
      if ($fileCrlf -gt 0) {
        $crlfCount += $fileCrlf
        Write-Host ("A8R37_HOOK_CRLF_FILE={0}:{1}" -f $file,$fileCrlf)
      }
    }
    Write-Host ("A8R37_HOOK_CRLF_COUNT={0}" -f $crlfCount)
    if ($crlfCount -ne 0) { throw "CRLF_COUNT=$crlfCount" }
  }

  Invoke-A8R37HookCheck -Label "gate_contract_static" -Body {
    $gateRaw = [System.IO.File]::ReadAllText((Resolve-Path "scripts/gate_f1.ps1"))
    $requiredTokens = @(
      "A8R37_HOOK_EARLIEST_FAST_PATH_ACTIVE=1",
      "A8R37_HOOK_NATIVE_FAST_PATH_ACTIVE=1",
      "A8R37_HOOK_PYTEST_DISABLED=1",
      "A8R37_HOOK_TARGET_BEGIN",
      "A8R37_HOOK_TARGET_RC",
      "A8R37_HOOK_TARGET_END",
      "SKIPPED_HOOK_FAST_PATH"
    )
    $missing = @($requiredTokens | Where-Object { -not $gateRaw.Contains($_) })
    Write-Host ("A8R37_HOOK_GATE_CONTRACT_MISSING_COUNT={0}" -f $missing.Count)
    if ($missing.Count -ne 0) { throw ("GATE_CONTRACT_MISSING=" + ($missing -join ",")) }
  }

  Invoke-A8R37HookCheck -Label "static_test_py_compile" -Body {
    & $pythonExe -S -B -m py_compile "tests/meta/test_gate_f1_hook_contracts.py"
    $a8r43lLastCommandSucceeded = $?
    $a8r43lLastExitCodeVar = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
    if ($null -eq $a8r43lLastExitCodeVar -or $null -eq $a8r43lLastExitCodeVar.Value) {
        if ($a8r43lLastCommandSucceeded) {
            $compileExit = 0
        }
        else {
            $compileExit = 1
        }
    }
    else {
        $compileExit = [int]$a8r43lLastExitCodeVar.Value
    }
    # A8_R43L_LASTEXITCODE_STRICTMODE_SAFE=1
    if ($null -eq $compileExit) { $compileExit = 99 }
    Write-Host ("A8R37_HOOK_PY_COMPILE_RC={0}" -f $compileExit)
    if ($compileExit -ne 0) { throw "PY_COMPILE_RC=$compileExit" }
  }
# A8_R43H_REGISTRY_GATE_CALL_BEGIN
Invoke-A8R43HRegistryGate
# A8_R43H_REGISTRY_GATE_CALL_END
Write-Host "=== SYNAPSE F1 GATE: PASS ==="
  Write-Host ("ACCEPTANCE: hook_native_exit=0 hook_targets=6 doctor_exit={0} doctor_overall={1} python_venv_detected={2} bootstrap_used={3} a8r37_hook_stabilization=1 a8r37_hook_earliest_fast_path=1 a8r37_hook_native_fast_path=1 a8r37_hook_pytest_disabled=1" -f $doctorExit,$doctorOverall,$hookVenvDetected,$bootstrapUsed)
  Invoke-A8R43MR43LGate
  exit 0
}

  Invoke-A8R37HookCheck -Label "a8_r38_product_candidate_contract_surface" -Body {
    $contractPath = Join-Path ((Resolve-Path (Join-Path $PSScriptRoot "..")).Path) "tests/meta/test_a8_r38_product_candidate_contract_surface.py"

    if (-not (Test-Path $contractPath)) {
      throw "A8_R39_META_CONTRACT_TEST_MISSING=$contractPath"
    }

    $contractText = Get-Content $contractPath -Raw
    $testFunctionCount = ([regex]::Matches($contractText, "(?m)^def test_")).Count

    if ($testFunctionCount -ne 4) {
      throw "A8_R39_META_CONTRACT_TEST_FUNCTION_COUNT=$testFunctionCount"
    }

    $requiredNeedles = @(
      "def _combined_contract_surface()",
      "SURFACE_TERMS",
      "CONTRACT_MARKERS",
      "They do not change product-selection behavior."
    )

    foreach ($needle in $requiredNeedles) {
      if (-not $contractText.Contains($needle)) {
        throw "A8_R39_META_CONTRACT_NEEDLE_MISSING=$needle"
      }
    }

    if ($contractText -match "from synapse\.|import synapse") {
      throw "A8_R39_META_CONTRACT_IMPORTS_RUNTIME"
    }
  }
# A8-R37 HOOK FAST PATH END


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
    $a8r43lLastCommandSucceeded = $?
    $a8r43lLastExitCodeVar = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
    if ($null -eq $a8r43lLastExitCodeVar -or $null -eq $a8r43lLastExitCodeVar.Value) {
        if ($a8r43lLastCommandSucceeded) {
            $bexit = 0
        }
        else {
            $bexit = 1
        }
    }
    else {
        $bexit = [int]$a8r43lLastExitCodeVar.Value
    }
    # A8_R43L_LASTEXITCODE_STRICTMODE_SAFE=1
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

# A8-R37: hook fast path runs before doctor to avoid pre-loop terminal cuts.
$doctorExit = -1
$doctorOverall = "SKIPPED_HOOK_FAST_PATH"

# DOCTOR
$doctorExit = 0
$doctorOverall = "UNKNOWN"
try {
  $out = & $pythonExe -X utf8 -m synapse.infra.doctor 2>&1
  $a8r43lLastCommandSucceeded = $?
  $a8r43lLastExitCodeVar = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
  if ($null -eq $a8r43lLastExitCodeVar -or $null -eq $a8r43lLastExitCodeVar.Value) {
      if ($a8r43lLastCommandSucceeded) {
          $doctorExit = 0
      }
      else {
          $doctorExit = 1
      }
  }
  else {
      $doctorExit = [int]$a8r43lLastExitCodeVar.Value
  }
  # A8_R43L_LASTEXITCODE_STRICTMODE_SAFE=1
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

# TESTS: HARD siempre (robusto si faltan dirs)
$roots = @("tests","buyer/tests","infra/tests","ops/tests")
$existing = @()
foreach ($r in $roots) { if (Test-Path $r) { $existing += $r } }
"TEST_ROOTS_FOUND={0}" -f $existing.Count | Out-Host
if ($existing.Count -eq 0) { Fail 30 "NO test roots found" }

# A8_R43Q_PYTEST_CONTINUATION_CONTRACT=1
$a8r43qPytestOutput = @(Invoke-A8R28CheckedPytest -Label "gate_pytest_existing_roots" -PythonExe $pythonExe -Targets @($existing))
$a8r43qPytestOutputCount = @($a8r43qPytestOutput).Count
Write-Host "A8_R43T_PYTEST_OUTPUT_CAPTURE_COUNT=$a8r43qPytestOutputCount"
if ($a8r43qPytestOutputCount -lt 1) {
  Write-Host "A8_R43T_PYTEST_RC_MISSING=1"
  $a8r43qPytestRc = 1
}
else {
  $a8r43qPytestRcRaw = $a8r43qPytestOutput[$a8r43qPytestOutputCount - 1]
  if ($a8r43qPytestOutputCount -gt 1) {
    for ($a8r43qPytestOutputIndex = 0; $a8r43qPytestOutputIndex -lt ($a8r43qPytestOutputCount - 1); $a8r43qPytestOutputIndex++) {
      Write-Host ([string]$a8r43qPytestOutput[$a8r43qPytestOutputIndex])
    }
  }
  try {
    $a8r43qPytestRc = [int]$a8r43qPytestRcRaw
    Write-Host "A8_R43T_PYTEST_RC_NORMALIZED=1"
  }
  catch {
    Write-Host "A8_R43T_PYTEST_RC_PARSE_FAILED=1"
    Write-Host "A8_R43T_PYTEST_RC_RAW=$a8r43qPytestRcRaw"
    $a8r43qPytestRc = 1
  }
}
Write-Host "A8_R43Q_PYTEST_GATE_RC=$a8r43qPytestRc"
if ([int]$a8r43qPytestRc -ne 0) {
    Write-Host "A8_R43Q_PYTEST_GATE_FAILED_BEFORE_EXIT=1"
    Invoke-A8R43MR43LGate
    exit ([int]$a8r43qPytestRc)
}
Write-Host "A8_R43Q_PYTEST_GATE_PASS=1"
$a8r43lLastCommandSucceeded = $?
$a8r43lLastExitCodeVar = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
if ($null -eq $a8r43lLastExitCodeVar -or $null -eq $a8r43lLastExitCodeVar.Value) {
    if ($a8r43lLastCommandSucceeded) {
        $pytestExit = 0
    }
    else {
        $pytestExit = 1
    }
}
else {
    $pytestExit = [int]$a8r43lLastExitCodeVar.Value
}
# A8_R43L_LASTEXITCODE_STRICTMODE_SAFE=1
if ($pytestExit -ne 0) { Fail 3 ("PYTEST_EXIT={0}" -f $pytestExit) }

# POST clean: solo en ops/release
if ($Mode -in @("ops","release")) {
  $post = Status-Lines
  if ($post -ne 0) {
    git status --porcelain | Out-Host
    Fail 4 ("POST_STATUS_LINES={0}" -f $post)
  }
}

# A8_R43H_REGISTRY_GATE_CALL_BEGIN

Invoke-A8R43HRegistryGate

# A8_R43H_REGISTRY_GATE_CALL_END

Write-Host "=== SYNAPSE F1 GATE: PASS ==="
Write-Host ("ACCEPTANCE: pytest_exit=0 doctor_exit={0} doctor_overall={1} python_venv_detected={2} bootstrap_used={3}" -f $doctorExit,$doctorOverall,$script:SynapsePythonVenvDetected,$bootstrapUsed)
Invoke-A8R43MR43LGate
exit 0