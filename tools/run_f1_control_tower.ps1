param(
  [string]$Owner = "3duardoambrosio-bit",
  [string]$Repo  = "trendify-f1",
  [string]$RulesetName = "F1 Main: PR + Checks",
  [string]$RequiredContext = "f1",
  [string]$OutJson = "artifacts/f1_control_tower_report.json"
)

$ErrorActionPreference="Stop"

Write-Host "=== SYNAPSE F1 CONTROL TOWER: START ===" -ForegroundColor Cyan

# ----------------
# [0] SNAPSHOT
# ----------------
Write-Host "`n[0] SNAPSHOT" -ForegroundColor Cyan
$root  = (git rev-parse --show-toplevel).Trim()
$branch= (git rev-parse --abbrev-ref HEAD).Trim()
$head  = (git rev-parse --short HEAD).Trim()
$dirty = (git status --porcelain | Measure-Object).Count

"root=$root"
"branch=$branch"
"head_short=$head"
"dirty_lines=$dirty"

# Hard gate: must be clean
if ($dirty -ne 0) { git status --porcelain; throw "F1 STOP: dirty_lines must be 0" }

# Report object
$r = [ordered]@{
  meta = [ordered]@{
    ts_utc = (Get-Date).ToUniversalTime().ToString("o")
    root = $root
    branch = $branch
    head_short = $head
  }
  gates = [ordered]@{}
  accept = [ordered]@{}
  errors = @()
}

function Run-Step {
  param(
    [string]$Name,
    [scriptblock]$Cmd
  )
  Write-Host "`n=== STEP: $Name ===" -ForegroundColor Cyan
  $old = $ErrorActionPreference
  $ErrorActionPreference="Continue"
  $out = @(& $Cmd 2>&1)
  $exit = $LASTEXITCODE
  $ErrorActionPreference=$old

  # store truncated output for json readability
  $outShort = @($out | Select-Object -First 120 | ForEach-Object { "$_" })
  $r.gates[$Name] = [ordered]@{
    exit = $exit
    lines = $out.Count
    head = $outShort
  }

  "step_exit=$exit"
  if ($exit -ne 0) {
    $r.errors += "step_failed=$Name exit=$exit"
    $outShort | Out-Host
    throw "F1 STOP: step failed => $Name (exit=$exit)"
  }
}

# ----------------
# [1] LOCAL HOOKS VERIFY
# ----------------
if (Test-Path "tools/verify_local_hooks_f1.ps1") {
  Run-Step -Name "local_hooks_verify" -Cmd { powershell -NoProfile -ExecutionPolicy Bypass -File tools/verify_local_hooks_f1.ps1 }
} else {
  $r.gates["local_hooks_verify"] = [ordered]@{ exit = 2; lines = 0; head = @("MISSING: tools/verify_local_hooks_f1.ps1") }
  throw "F1 STOP: missing tools/verify_local_hooks_f1.ps1"
}

# ----------------
# [2] F1 GATE RUNNER (repo)
# ----------------
if (Test-Path "scripts/gate_f1.ps1") {
  Run-Step -Name "gate_f1_precommit" -Cmd { powershell -NoProfile -ExecutionPolicy Bypass -File scripts/gate_f1.ps1 precommit }
} else {
  $r.gates["gate_f1_precommit"] = [ordered]@{ exit = 2; lines = 0; head = @("MISSING: scripts/gate_f1.ps1") }
  throw "F1 STOP: missing scripts/gate_f1.ps1"
}

# ----------------
# [3] DOCTOR
# ----------------
Run-Step -Name "doctor" -Cmd { python -m synapse.infra.doctor }

# ----------------
# [4] PYTEST
# ----------------
Run-Step -Name "pytest" -Cmd { python -m pytest -q }

# ----------------
# [5] RULESET AUDIT (READ-ONLY)
# ----------------
Write-Host "`n=== STEP: ruleset_audit ===" -ForegroundColor Cyan
$rsList = gh api -H "Accept: application/vnd.github+json" "/repos/$Owner/$Repo/rulesets?per_page=100" | ConvertFrom-Json
$rulesetsCount = @($rsList).Count

$target = $rsList | Where-Object { $_.name -eq $RulesetName } | Select-Object -First 1
$rulesetId = if ($null -ne $target) { [int]$target.id } else { 0 }
$enforcement = if ($null -ne $target) { "$($target.enforcement)" } else { "" }

$full = $null
if ($rulesetId -gt 0) {
  $full = gh api -H "Accept: application/vnd.github+json" "/repos/$Owner/$Repo/rulesets/$rulesetId" | ConvertFrom-Json
}

$enfOk = [int]($null -ne $full -and $full.enforcement -eq "active")
$includes = @()
if ($null -ne $full -and $null -ne $full.conditions -and $null -ne $full.conditions.ref_name) {
  $includes = @($full.conditions.ref_name.include)
}
$incHits = @($includes | Where-Object { $_ -eq "refs/heads/main" }).Count

$types = @()
if ($null -ne $full -and $null -ne $full.rules) { $types = @($full.rules | ForEach-Object { $_.type }) }

$hasPR  = @($types | Where-Object { $_ -eq "pull_request" }).Count
$hasNFF = @($types | Where-Object { $_ -eq "non_fast_forward" }).Count
$hasRSC = @($types | Where-Object { $_ -eq "required_status_checks" }).Count

$ctxHits = 0
if ($null -ne $full -and $null -ne $full.rules) {
  $ctxHits = @(
    $full.rules |
      Where-Object { $_.type -eq "required_status_checks" } |
      ForEach-Object { $_.parameters.required_status_checks } |
      Where-Object { $_.context -eq $RequiredContext }
  ).Count
}

$r.gates["ruleset_audit"] = [ordered]@{
  exit = 0
  rulesets_count = $rulesetsCount
  ruleset_id = $rulesetId
  enforcement = $enforcement
  gate_enforcement_active = $enfOk
  include_main_hits = $incHits
  rule_pull_request_count = $hasPR
  rule_required_status_checks_count = $hasRSC
  required_context_hits = $ctxHits
  rule_non_fast_forward_count = $hasNFF
}

"rulesets_count=$rulesetsCount"
"ruleset_id=$rulesetId"
"gate_enforcement_active=$enfOk"
"include_main_hits=$incHits"
"rule_pull_request_count=$hasPR"
"rule_required_status_checks_count=$hasRSC"
"required_context_hits=$ctxHits"
"rule_non_fast_forward_count=$hasNFF"

# ----------------
# [6] FINAL ACCEPTANCE (NUMERIC HARD)
# ----------------
Write-Host "`n=== ACCEPTANCE (NUMERIC) ===" -ForegroundColor Green
$ok = 1

$ok = $ok -band [int](((git status --porcelain | Measure-Object).Count) -eq 0)
$r.accept["repo_clean"] = $ok

$ok = $ok -band [int]($enfOk -eq 1)
$r.accept["ruleset_enforcement_active"] = [int]($enfOk -eq 1)

$ok = $ok -band [int]($incHits -eq 1)
$r.accept["ruleset_include_main_hits_eq_1"] = [int]($incHits -eq 1)

$ok = $ok -band [int]($hasPR -eq 1)
$r.accept["ruleset_pull_request_rule_eq_1"] = [int]($hasPR -eq 1)

$ok = $ok -band [int]($hasRSC -eq 1)
$r.accept["ruleset_required_status_checks_rule_eq_1"] = [int]($hasRSC -eq 1)

$ok = $ok -band [int]($ctxHits -eq 1)
$r.accept["ruleset_required_context_hits_eq_1"] = [int]($ctxHits -eq 1)

$ok = $ok -band [int]($hasNFF -eq 1)
$r.accept["ruleset_non_fast_forward_rule_eq_1"] = [int]($hasNFF -eq 1)

"RULE_1 repo_clean => " + [int](((git status --porcelain | Measure-Object).Count) -eq 0)
"RULE_2 ruleset_enforcement_active => " + [int]($enfOk -eq 1)
"RULE_3 include_main_hits_eq_1 => " + [int]($incHits -eq 1)
"RULE_4 pull_request_rule_eq_1 => " + [int]($hasPR -eq 1)
"RULE_5 required_status_checks_rule_eq_1 => " + [int]($hasRSC -eq 1)
"RULE_6 required_context_hits_eq_1 => " + [int]($ctxHits -eq 1)
"RULE_7 non_fast_forward_rule_eq_1 => " + [int]($hasNFF -eq 1)

"ACCEPTANCE_OK=$ok"
if ($ok -ne 1) { throw "F1 STOP: acceptance != 1" }

# ----------------
# [7] WRITE JSON REPORT
# ----------------
$r.meta["acceptance_ok"] = $ok
$json = ($r | ConvertTo-Json -Depth 8)
[System.IO.File]::WriteAllText((Join-Path $root $OutJson), $json, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "`n=== SYNAPSE F1 CONTROL TOWER: PASS ===" -ForegroundColor Green
Write-Host "report_json=$OutJson" -ForegroundColor Green

Write-Host "`n=== ESTADO COMPLETO ===" -ForegroundColor Cyan
"root=$root"
"branch=" + (git rev-parse --abbrev-ref HEAD).Trim()
"head_short=" + (git rev-parse --short HEAD).Trim()
"dirty_lines=" + ((git status --porcelain | Measure-Object).Count)
"hooksPath_effective=" + ((git config --get core.hooksPath) | ForEach-Object { $_.Trim() })
