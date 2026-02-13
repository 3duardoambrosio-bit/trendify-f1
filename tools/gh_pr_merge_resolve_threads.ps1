param(
  [Parameter(Mandatory=$true)][string]$Owner,
  [Parameter(Mandatory=$true)][string]$Repo,
  [Parameter(Mandatory=$true)][int]$Pr,
  [ValidateSet("squash","merge","rebase")][string]$MergeMethod="squash",
  [switch]$Admin,
  [switch]$DeleteBranch
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

Write-Host "`n[0] GH AUTH STATUS" -ForegroundColor Cyan
gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "gh auth status falló (no autenticado)" }

Write-Host "`n[1] REQUIRED CHECKS (must be PASS)" -ForegroundColor Cyan
gh pr checks -R "$Owner/$Repo" $Pr --required | Out-Host
$checksExit=$LASTEXITCODE
"checks_exit=$checksExit"
if ($checksExit -ne 0) { Fail "required checks NO están en PASS" }

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
if ($LASTEXITCODE -ne 0 -or -not $j) { Fail "gh api graphql (query threads) falló" }
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
foreach ($t in $unresolved) {
  "resolving_thread=$($t.id)"
  gh api graphql -f query="$m" -F threadId="$($t.id)" | Out-Null
  if ($LASTEXITCODE -ne 0) { Fail "no pude resolver thread=$($t.id)" }
}

Write-Host "`n[4] RECHECK UNRESOLVED COUNT" -ForegroundColor Cyan
$j2 = gh api graphql -f query="$q" -F owner="$Owner" -F name="$Repo" -F number="$Pr" | ConvertFrom-Json
$threads2 = @($j2.data.repository.pullRequest.reviewThreads.nodes)
$unresolved2 = @($threads2 | Where-Object { -not $_.isResolved })
"threads_unresolved_after=$($unresolved2.Count)"
if ($unresolved2.Count -ne 0) { Fail "todavía hay conversaciones sin resolver" }

Write-Host "`n[5] MERGE PR" -ForegroundColor Yellow
$mergeFlag = if ($MergeMethod -eq "squash") { "--squash" } elseif ($MergeMethod -eq "merge") { "--merge" } else { "--rebase" }
$adminFlag = if ($Admin.IsPresent) { "--admin" } else { "" }
$delFlag   = if ($DeleteBranch.IsPresent) { "--delete-branch" } else { "" }
gh pr merge -R "$Owner/$Repo" $Pr $mergeFlag $adminFlag $delFlag | Out-Host
$mergeExit=$LASTEXITCODE
"merge_exit=$mergeExit"
if ($mergeExit -ne 0) { Fail "merge falló" }

Write-Host "`n[6] VERIFY MERGED (mergedAt != null)" -ForegroundColor Cyan
$prAfter = gh pr view -R "$Owner/$Repo" $Pr --json state,mergedAt,mergeCommit,url | ConvertFrom-Json
$merged = [int]([bool]$prAfter.mergedAt)
"state_after=$($prAfter.state)"
"merged_after=$merged"
"mergedAt_after=$($prAfter.mergedAt)"
if ($merged -ne 1) { Fail "merge no aplicado" }

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
