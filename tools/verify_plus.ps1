param(
  [Parameter(Position=0)]
  [ValidateSet("manual","ci")]
  [string]$Mode = "manual"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Msg) {
  Write-Host "FAIL: $Msg"
  exit 2
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
  $enc = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

Write-Host "== SYNAPSE VERIFY+ =="
Write-Host "Mode=$Mode"

Write-Host "`n[1/6] Doctor"
python -m synapse.infra.doctor
if ($LASTEXITCODE -ne 0) { Fail "doctor_exit=$LASTEXITCODE" }

Write-Host "`n[2/6] Pytest"
pytest -q
if ($LASTEXITCODE -ne 0) { Fail "pytest_exit=$LASTEXITCODE" }

Write-Host "`n[3/6] Compileall"
python -m compileall synapse infra ops buyer core config -q
if ($LASTEXITCODE -ne 0) { Fail "compileall_exit=$LASTEXITCODE" }

Write-Host "`n[4/6] Audit F1 (JSON)"
if (-not (Test-Path .\tools\audit_f1.py)) { Fail "missing tools\audit_f1.py" }

# Captura JSON aunque el script salga con exit=2 (FAIL esperado mientras haya prints)
$jsonLines = & python .\tools\audit_f1.py
$auditExit = $LASTEXITCODE
$jsonText = ($jsonLines -join "`n")
Write-Utf8NoBom -Path ".\tools\_audit_f1_last.json" -Content $jsonText

# Parsear en UTF-8 (ya garantizado)
python -c "import json,sys; j=json.load(open(r'.\tools\_audit_f1_last.json','r',encoding='utf-8')); print(j['overall']); sys.exit(0 if j['overall']=='PASS' else 2)"
if ($LASTEXITCODE -ne 0) { Fail "audit_f1_overall=FAIL (see tools\_audit_f1_last.json)" }

Write-Host "`n[5/6] Git clean"
$dirty = @(git status --porcelain)
$dirty_lines = $dirty.Count
Write-Host "dirty_lines=$dirty_lines"
if ($Mode -eq "ci" -and $dirty_lines -ne 0) { Fail "repo_dirty_lines=$dirty_lines (ci mode requires clean)" }

Write-Host "`n[6/6] Canonicals untouched (staged+unstaged)"
$canon = @(
  "ops/capital_shield_v2.py","infra/ledger_v2.py","ops/spend_gateway_v1.py","ops/safety_middleware.py",
  "synapse/safety/killswitch.py","synapse/safety/circuit.py","infra/atomic_io.py","infra/idempotency_manager.py"
)
$changed = @()
$changed += @(git diff --name-only)
$changed += @(git diff --name-only --cached)
$touched = @()
foreach ($c in $canon) { if ($changed -contains $c) { $touched += $c } }
if ($touched.Count -ne 0) { Fail ("canonical_touched=" + ($touched -join ",")) }

Write-Host "`nOK: verify_plus completo"
exit 0