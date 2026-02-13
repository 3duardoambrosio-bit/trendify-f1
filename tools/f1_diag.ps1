$ErrorActionPreference="Stop"
Write-Host "=== F1 DIAG: START ===" -ForegroundColor Cyan

$root  = (git rev-parse --show-toplevel).Trim()
$branch= (git rev-parse --abbrev-ref HEAD).Trim()
$head  = (git rev-parse --short HEAD).Trim()
$dirty = (git status --porcelain | Measure-Object).Count
$hooksPath = (git config --get core.hooksPath)

"root=$root"
"branch=$branch"
"head_short=$head"
"dirty_lines=$dirty"
"hooksPath_effective=$((if ($hooksPath) { $hooksPath.Trim() } else { "" }))"

$prePushTracked = (git ls-files .githooks/pre-push | Measure-Object).Count
"pre_push_tracked_hits=$prePushTracked"

$gitignoreArtifacts = (Select-String -Path .gitignore -Pattern '^artifacts/$' | Measure-Object).Count
"gitignore_artifacts_hits=$gitignoreArtifacts"

$gitignoreHooksIgnore = (Select-String -Path .gitignore -Pattern '^\Q.githooks/*\E$' | Measure-Object).Count
$gitignoreHooksAllow1 = (Select-String -Path .gitignore -Pattern '^!\.githooks/pre-commit$' | Measure-Object).Count
$gitignoreHooksAllow2 = (Select-String -Path .gitignore -Pattern '^!\.githooks/pre-push$' | Measure-Object).Count
"gitignore_githooks_ignore_hits=$gitignoreHooksIgnore"
"gitignore_githooks_allow_precommit_hits=$gitignoreHooksAllow1"
"gitignore_githooks_allow_prepush_hits=$gitignoreHooksAllow2"

Write-Host "`n=== RUN verify_local_hooks_f1.ps1 ===" -ForegroundColor Cyan
powershell -NoProfile -ExecutionPolicy Bypass -File tools/verify_local_hooks_f1.ps1 | Out-Host
"verify_exit=$LASTEXITCODE"

Write-Host "`n=== RUN control tower ===" -ForegroundColor Cyan
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_f1_control_tower.ps1 | Out-Host
"control_tower_exit=$LASTEXITCODE"

Write-Host "`n=== ACCEPTANCE (NUMERIC) ===" -ForegroundColor Green
$ok=1
$ok = $ok -band [int]($dirty -eq 0)
$ok = $ok -band [int]($prePushTracked -eq 1)
$ok = $ok -band [int]($gitignoreArtifacts -ge 1)
$ok = $ok -band [int]($gitignoreHooksIgnore -ge 1)
$ok = $ok -band [int]($gitignoreHooksAllow1 -ge 1)
$ok = $ok -band [int]($gitignoreHooksAllow2 -ge 1)
$ok = $ok -band [int]($LASTEXITCODE -eq 0)

"RULE_1 dirty_lines == 0 => " + [int]($dirty -eq 0)
"RULE_2 pre_push_tracked_hits == 1 => " + [int]($prePushTracked -eq 1)
"RULE_3 gitignore_artifacts_hits >= 1 => " + [int]($gitignoreArtifacts -ge 1)
"RULE_4 gitignore_githooks_ignore_hits >= 1 => " + [int]($gitignoreHooksIgnore -ge 1)
"RULE_5 gitignore_githooks_allow_precommit_hits >= 1 => " + [int]($gitignoreHooksAllow1 -ge 1)
"RULE_6 gitignore_githooks_allow_prepush_hits >= 1 => " + [int]($gitignoreHooksAllow2 -ge 1)
"RULE_7 last_exit_is_0 => " + [int]($LASTEXITCODE -eq 0)

"ACCEPTANCE_OK=$ok"
if ($ok -ne 1) { throw "F1 STOP: ACCEPTANCE_OK != 1" }

Write-Host "`n=== F1 DIAG: END ===" -ForegroundColor Cyan
