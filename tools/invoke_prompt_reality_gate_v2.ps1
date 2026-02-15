param(
  [string[]]$Needles = @(),
  [string[]]$ExpectedPaths = @(),
  [int]$MinTests = 0,
  [ValidateSet("dev","release")]
  [string]$Mode = "dev"
)

$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

function Need([bool]$cond, [string]$msg){ if(-not $cond){ throw "F1 STOP: $msg" } }

Write-Host "=== F1: PROMPT REALITY GATE v2 ($Mode) (NO CHANGES) ===" -ForegroundColor Cyan

# Snapshot
$branch=(git rev-parse --abbrev-ref HEAD).Trim()
$head=(git rev-parse --short HEAD).Trim()
$dirty=(git status --porcelain | Measure-Object).Count
git fetch origin | Out-Null

"branch=$branch"
"head_short=$head"
"dirty_lines=$dirty"

# Compare HEAD vs origin/main (dev truth)
$lrHead=(git rev-list --left-right --count origin/main...HEAD) -split "\s+"
$behindHead=$lrHead[0]; $aheadHead=$lrHead[1]
"behind_head=$behindHead"
"ahead_head=$aheadHead"

# Compare main vs origin/main (release truth)
$lrMain=(git rev-list --left-right --count origin/main...main) -split "\s+"
$behindMain=$lrMain[0]; $aheadMain=$lrMain[1]
"behind_main=$behindMain"
"ahead_main=$aheadMain"

# Expected paths
Write-Host "`n[1] EXPECTED PATHS" -ForegroundColor Yellow
foreach($p in $ExpectedPaths){
  $exists = [int](Test-Path $p)
  "path=$p exists=$exists"
}

# Needles
Write-Host "`n[2] NEEDLES (git grep)" -ForegroundColor Yellow
foreach($n in $Needles){
  $hits=@(git grep -n $n 2>$null)
  "needle=$n hits=$($hits.Count)"
  if($hits.Count -gt 0){
    "top3_$n="
    ($hits | Select-Object -First 3) | ForEach-Object { "  $_" }
  }
}

# Pytest (parseable)
Write-Host "`n[3] PYTEST (parseable)" -ForegroundColor Yellow
$pytestOut = & python -m pytest 2>&1
$pytestRc=$LASTEXITCODE
"pytest_exit=$pytestRc"

$pytestText = ($pytestOut | Out-String)
$mPassed = [regex]::Match($pytestText,'(?<n>\d+)\s+passed')
$passed = if($mPassed.Success){ [int]$mPassed.Groups['n'].Value } else { -1 }
$mColl = [regex]::Match($pytestText,'collected\s+(?<n>\d+)\s+items')
$collected = if($mColl.Success){ [int]$mColl.Groups['n'].Value } else { -1 }
$nodeidsPath = Join-Path $PWD ".pytest_cache\v\cache\nodeids"
$nodeidsCount = if(Test-Path $nodeidsPath){ (Get-Content $nodeidsPath | Measure-Object).Count } else { -1 }

$testCount=$passed
if($testCount -lt 0 -and $collected -ge 0){ $testCount=$collected }
if($testCount -lt 0 -and $nodeidsCount -ge 0){ $testCount=$nodeidsCount }

"pytest_passed_count=$passed"
"pytest_test_count_final=$testCount"

# Doctor
Write-Host "`n[4] DOCTOR" -ForegroundColor Yellow
$doctorOut = & python -m synapse.infra.doctor 2>&1
$doctorRc=$LASTEXITCODE
$greenHits=([regex]::Matches(($doctorOut|Out-String),'OVERALL:\s+GREEN').Count)
"doctor_exit=$doctorRc"
"doctor_green_hits=$greenHits"

# Control tower
Write-Host "`n[5] CONTROL TOWER" -ForegroundColor Yellow
$ctOut = & powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_f1_control_tower.ps1 2>&1
$ctRc=$LASTEXITCODE
$ctOkHits=([regex]::Matches(($ctOut|Out-String),'ACCEPTANCE_OK=1').Count)
"ct_exit=$ctRc"
"ct_ok_hits=$ctOkHits"

# Acceptance
Write-Host "`n=== ACCEPTANCE (NUMERIC) ===" -ForegroundColor Green
$ok=1
$ok = $ok -band [int]($dirty -eq 0)
$ok = $ok -band [int]($pytestRc -eq 0)
if($MinTests -gt 0){ $ok = $ok -band [int]($testCount -ge $MinTests) }
$ok = $ok -band [int]($doctorRc -eq 0)
$ok = $ok -band [int]($greenHits -ge 1)
$ok = $ok -band [int]($ctRc -eq 0)
$ok = $ok -band [int]($ctOkHits -ge 1)

if($Mode -eq "dev"){
  $ok = $ok -band [int]($behindHead -eq "0")
  "RULE_D1 behind_head==0 => " + [int]($behindHead -eq "0")
} else {
  $ok = $ok -band [int]($branch -eq "main")
  $ok = $ok -band [int]($behindMain -eq "0")
  $ok = $ok -band [int]($aheadMain  -eq "0")
  "RULE_R1 on_main => " + [int]($branch -eq "main")
  "RULE_R2 behind_main==0 => " + [int]($behindMain -eq "0")
  "RULE_R3 ahead_main==0 => " + [int]($aheadMain -eq "0")
}

"RULE_1 dirty==0 => " + [int]($dirty -eq 0)
"RULE_2 pytest_exit==0 => " + [int]($pytestRc -eq 0)
if($MinTests -gt 0){ "RULE_3 tests>=MinTests($MinTests) => " + [int]($testCount -ge $MinTests) }
"RULE_4 doctor_exit==0 => " + [int]($doctorRc -eq 0)
"RULE_5 doctor_green_hit>=1 => " + [int]($greenHits -ge 1)
"RULE_6 ct_exit==0 => " + [int]($ctRc -eq 0)
"RULE_7 ct_ok_hit>=1 => " + [int]($ctOkHits -ge 1)
"ACCEPTANCE_OK=$ok"

Need ($ok -eq 1) "ACCEPTANCE_OK != 1"

Write-Host "`n=== OK: REALITY GATE PASS ($Mode) ===" -ForegroundColor Green

Write-Host "`n=== ESTADO COMPLETO ===" -ForegroundColor Cyan
"repo_root=$PWD"
"branch=$branch"
"head_short=$head"
"dirty_lines=$dirty"
"behind_head=$behindHead"
"ahead_head=$aheadHead"
"behind_main=$behindMain"
"ahead_main=$aheadMain"
"pytest_test_count_final=$testCount"
"doctor_exit=$doctorRc"
"ct_exit=$ctRc"