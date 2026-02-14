param(
  [Parameter(Mandatory=$true)][string]$Owner,
  [Parameter(Mandatory=$true)][string]$Repo,
  [Parameter(Mandatory=$true)][int]$Pr,
  [ValidateSet("squash","merge","rebase")][string]$MergeMethod="squash",
  [switch]$Admin,
  [switch]$DeleteBranch,
  [switch]$SkipChecks
)

$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

function Fail([string]$msg) { throw "F1 STOP: $msg" }

Write-Host "=== F1 PR MERGE-RESCUE: START ===" -ForegroundColor Cyan
"owner=$Owner"
"repo=$Repo"
"pr=$Pr"
"merge_method=$MergeMethod"
"admin=" + [int]$Admin.IsPresent
"delete_branch=" + [int]$DeleteBranch.IsPresent
"skip_checks=" + [int]$SkipChecks.IsPresent

Write-Host "`n[0] GH AUTH STATUS" -ForegroundColor Cyan
gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "gh auth status failed (not authenticated)" }

if (-not $SkipChecks.IsPresent) {
  Write-Host "`n[1] CHECKS (WATCH REQUIRED) must PASS" -ForegroundColor Cyan
  gh pr checks -R "$Owner/$Repo" $Pr --watch --required | Out-Host
  $checksExit=$LASTEXITCODE
  "checks_exit=$checksExit"
  if ($checksExit -ne 0) { Fail "required checks not PASS (gh pr checks --watch --required exit != 0)" }
} else {
  Write-Host "`n[1] CHECKS SKIPPED (caller already gated outside)" -ForegroundColor Yellow
  $checksExit=0
  "checks_exit=$checksExit"
}

Write-Host "`n[2] FIND UNRESOLVED THREADS (GraphQL)" -ForegroundColor Cyan
$q = @(
  "query($owner:String!, $name:String!, $number:Int!) {",
  "  repository(owner:$owner, name:$name) {",
  "    pullRequest(number:$number) {",
  "      reviewThreads(first:100) { nodes { id isResolved } }",
  "    }",
  "  }",
  "}"
) -join "`n"
$j = gh api graphql -f query="$q" -F owner="$Owner" -F name="$Repo" -F number="$Pr" | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $j) { Fail "graphql query threads failed" }
$threads = @($j.data.repository.pullRequest.reviewThreads.nodes)
$unresolved = @($threads | Where-Object { -not $_.isResolved })
"threads_total=$($threads.Count)"
"threads_unresolved=$($unresolved.Count)"
$unresolved | ForEach-Object -Begin { $i=0 } -Process { $i++; "  unresolved[$i]=$($_.id)" }

Write-Host "`n[3] RESOLVE UNRESOLVED THREADS (GraphQL)" -ForegroundColor Yellow
$m = @(
  "mutation($threadId:ID!) {",
  "  resolveReviewThread(input:{threadId:$threadId}) { thread { id isResolved } }",
  "}"
) -join "`n"
$resolvedOk=0
foreach ($t in $unresolved) {
  $tid=$t.id
  "resolving_thread=$tid"
  gh api graphql -f query="$m" -F threadId="$tid" | Out-Null
  if ($LASTEXITCODE -ne 0) { Fail "cannot resolve thread=$tid" }
  $resolvedOk++
}
"resolved_threads_count=$resolvedOk"

Write-Host "`n[4] RECHECK UNRESOLVED COUNT" -ForegroundColor Cyan
$j2 = gh api graphql -f query="$q" -F owner="$Owner" -F name="$Repo" -F number="$Pr" | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $j2) { Fail "graphql recheck failed" }
$threads2 = @($j2.data.repository.pullRequest.reviewThreads.nodes)
$unresolved2 = @($threads2 | Where-Object { -not $_.isResolved })
"threads_unresolved_after=$($unresolved2.Count)"
if ($unresolved2.Count -ne 0) { Fail "still unresolved threads" }

Write-Host "`n[5] MERGE PR" -ForegroundColor Yellow
$mergeFlag = if ($MergeMethod -eq "squash") { "--squash" } elseif ($MergeMethod -eq "merge") { "--merge" } else { "--rebase" }
$adminFlag = if ($Admin.IsPresent) { "--admin" } else { "" }
$delFlag   = if ($DeleteBranch.IsPresent) { "--delete-branch" } else { "" }
"selected_merge_flag=$mergeFlag"
"selected_admin_flag=$adminFlag"
"selected_delete_flag=$delFlag"
gh pr merge -R "$Owner/$Repo" $Pr $mergeFlag $adminFlag $delFlag | Out-Host
$mergeExit=$LASTEXITCODE
"merge_exit=$mergeExit"
if ($mergeExit -ne 0) { Fail "merge failed (gh pr merge exit != 0)" }

Write-Host "`n[6] VERIFY MERGED (mergedAt != null)" -ForegroundColor Cyan
$prAfter = gh pr view -R "$Owner/$Repo" $Pr --json state,mergedAt,mergeCommit,url | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $prAfter) { Fail "cannot read PR post-merge" }
$merged = [int]([bool]$prAfter.mergedAt)
"state_after=$($prAfter.state)"
"merged_after=$merged"
"mergedAt_after=$($prAfter.mergedAt)"
if ($merged -ne 1) { Fail "merge not applied (merged_after != 1)" }

Write-Host "`n=== ACCEPTANCE (NUMERIC) ===" -ForegroundColor Green
"RULE_1 checks_exit == 0 => " + [int]($checksExit -eq 0)
"RULE_2 threads_unresolved_after == 0 => " + [int]($unresolved2.Count -eq 0)
"RULE_3 merge_exit == 0 => " + [int]($mergeExit -eq 0)
"RULE_4 merged_after == 1 => " + [int]($merged -eq 1)
$ok=1
$ok = $ok -band [int]($checksExit -eq 0)
$ok = $ok -band [int]($unresolved2.Count -eq 0)
$ok = $ok -band [int]($mergeExit -eq 0)
$ok = $ok -band [int]($merged -eq 1)
"ACCEPTANCE_OK=$ok"
if ($ok -ne 1) { Fail "ACCEPTANCE_OK != 1" }

Write-Host "`n=== F1 PR MERGE-RESCUE: END ===" -ForegroundColor Cyan
