$ErrorActionPreference="Stop"

Write-Host "=== F1: VERIFY LOCAL HOOKS (AUTO hooksPath + DIRTY ALLOWLIST) ===" -ForegroundColor Cyan

$root  = (git rev-parse --show-toplevel).Trim()
$head  = (git rev-parse --short HEAD).Trim()
$dirtyLines = @(git status --porcelain)

$hooksPath = (git config --get core.hooksPath)
$hooksPathEff = if ([string]::IsNullOrWhiteSpace($hooksPath)) { "" } else { $hooksPath.Trim() }

$hooksDirMode = if ([string]::IsNullOrWhiteSpace($hooksPathEff)) { ".git/hooks" } else { "core.hooksPath" }
$hooksDirEff  = if ($hooksDirMode -eq "core.hooksPath") { Join-Path $root $hooksPathEff } else { Join-Path $root ".git/hooks" }

"root=$root"
"head_short=$head"
"dirty_lines=$($dirtyLines.Count)"
"hooksPath_effective=$hooksPathEff"
"hooks_dir_mode=$hooksDirMode"
"hooks_dir_effective=$hooksDirEff"

# Allowlist dirty paths (during hook development only)
$allow = @(
  ".githooks/pre-push",
  "tools/verify_local_hooks_f1.ps1"
)

# Extract paths from porcelain
$paths=@()
foreach ($l in $dirtyLines) {
  $line="$l"
  if ($line -match '^[ MADRCU\?]{2}\s+(?<p>.+)$') { $p=$Matches.p } else { $p=$line }
  $p=($p -replace "\\","/").Trim()
  if ($p -match "->") { $p = ($p -split "->")[-1].Trim() }
  $paths += $p
}

$bad=@($paths | Where-Object { $_ -notin $allow })
"dirty_allowlist_bad=$($bad.Count)"
$bad | ForEach-Object { "  bad_dirty_path=$_" }

# Rule: clean OR only allowlist dirty (<=2)
$dirtyOk = [int]( ($dirtyLines.Count -eq 0) -or ( ($bad.Count -eq 0) -and ($dirtyLines.Count -le 2) ) )
"dirty_allowlist_ok=$dirtyOk"

function Check-Hook {
  param(
    [string]$HookName,
    [string]$Marker
  )
  $p = Join-Path $hooksDirEff $HookName
  $exists = [int](Test-Path $p)
  $bytes  = if ($exists -eq 1) { (Get-Item $p).Length } else { 0 }
  $hits   = 0
  if ($exists -eq 1) {
    $raw = Get-Content $p -Raw -ErrorAction Stop
    $hits = ([regex]::Matches($raw, [regex]::Escape($Marker))).Count
  }
  return [ordered]@{
    path = $p
    exists = $exists
    bytes = $bytes
    marker = $Marker
    marker_hits = $hits
  }
}

$preCommit = Check-Hook -HookName "pre-commit" -Marker "gate_f1.ps1"
$prePush   = Check-Hook -HookName "pre-push"   -Marker "run_f1_control_tower.ps1"

"pre_commit_exists=$($preCommit.exists)"
"pre_commit_bytes=$($preCommit.bytes)"
"pre_commit_marker_hits=$($preCommit.marker_hits)"

"pre_push_exists=$($prePush.exists)"
"pre_push_bytes=$($prePush.bytes)"
"pre_push_marker_hits=$($prePush.marker_hits)"

Write-Host "`n=== ACCEPTANCE (NUMERIC) ===" -ForegroundColor Green

$ok=1
$ok = $ok -band $dirtyOk

$ok = $ok -band [int]($preCommit.exists -eq 1)
$ok = $ok -band [int]($preCommit.bytes -ge 20)
$ok = $ok -band [int]($preCommit.marker_hits -ge 1)

$ok = $ok -band [int]($prePush.exists -eq 1)
$ok = $ok -band [int]($prePush.bytes -ge 20)
$ok = $ok -band [int]($prePush.marker_hits -ge 1)

"RULE_0 dirty_allowlist_ok => " + $dirtyOk
"RULE_1 pre_commit_exists == 1 => " + [int]($preCommit.exists -eq 1)
"RULE_2 pre_commit_bytes >= 20 => " + [int]($preCommit.bytes -ge 20)
"RULE_3 pre_commit_marker_hits >= 1 => " + [int]($preCommit.marker_hits -ge 1)
"RULE_4 pre_push_exists == 1 => " + [int]($prePush.exists -eq 1)
"RULE_5 pre_push_bytes >= 20 => " + [int]($prePush.bytes -ge 20)
"RULE_6 pre_push_marker_hits >= 1 => " + [int]($prePush.marker_hits -ge 1)

"ACCEPTANCE_OK=$ok"
if ($ok -ne 1) { throw "F1 STOP: ACCEPTANCE_OK != 1" }

Write-Host "`n=== ESTADO COMPLETO ===" -ForegroundColor Cyan
"hook_pre_commit_path=$($preCommit.path)"
"hook_pre_push_path=$($prePush.path)"
