param(
  [Parameter(Mandatory=$false)][switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Die([string]$Msg){ throw $Msg }

"=== F1+ START ==="

"=== [1/3] Core F1 Gate ==="
$cmd1 = @("powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",".\tools\invoke_synapse_f1.ps1")
$out1 = & $cmd1[0] $cmd1[1..($cmd1.Count-1)] 2>&1
$rc1 = $LASTEXITCODE
$out1 | Out-Host
"invoke_f1_exit=$rc1"
if($rc1 -ne 0){ Die "FAIL: invoke_f1_exit_expected_0 got=$rc1" }

"=== [2/3] Webhook Fixtures Batch (200 then 409) ==="
$cmd2 = @("powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",".\tools\run_all_webhook_fixtures.ps1")
if($Quiet){ $cmd2 += "-Quiet" }
$out2 = & $cmd2[0] $cmd2[1..($cmd2.Count-1)] 2>&1
$rc2 = $LASTEXITCODE
$out2 | Out-Host
"batch_exit=$rc2"
if($rc2 -ne 0){ Die "FAIL: batch_exit_expected_0 got=$rc2" }

"=== [3/3] Git clean (MUST BE 0) ==="
$dirty = (git status --porcelain | Measure-Object).Count
"dirty_lines=$dirty"
if($dirty -ne 0){ Die "FAIL: dirty_lines_expected_0 got=$dirty" }

"OK: F1+ completo"
exit 0
