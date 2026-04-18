param(
  [int]$Iterations = 1,
  [string]$Secret = "shpss_test_secret",
  [string]$OutputRoot = "C:\Temp\synapse_burnin",
  [string[]]$IncludeSteps = @(),
  [switch]$StopOnFirstFailure
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function New-Dir([string]$Path) {
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Write-SummaryFile {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][int]$Iterations,
    [Parameter(Mandatory=$true)][object[]]$Results
  )

  $totalSteps = $Results.Count
  $failedSteps = @($Results | Where-Object { -not $_.ok }).Count
  $passedSteps = $totalSteps - $failedSteps
  $overall = if ($failedSteps -eq 0) { "PASS" } else { "FAIL" }

  $summary = [pscustomobject]@{
    iterations   = $Iterations
    total_steps  = $totalSteps
    passed_steps = $passedSteps
    failed_steps = $failedSteps
    overall      = $overall
    results      = $Results
  }

  $summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Invoke-Step {
  param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][scriptblock]$Action,
    [Parameter(Mandatory=$true)][string]$LogPath
  )

  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $ok = $true
  $err = ""

  try {
    [object[]]$captured = @(& $Action *>&1)
    $commandExit = $LASTEXITCODE

    if ($captured.Count -gt 0) {
      $captured | Tee-Object -FilePath $LogPath | Out-Host
    }
    else {
      "" | Set-Content -LiteralPath $LogPath -Encoding UTF8
    }

    if ($commandExit -ne 0) {
      throw "EXITCODE=$commandExit"
    }
  }
  catch {
    $ok = $false
    $err = $_.Exception.Message
  }
  finally {
    $sw.Stop()
  }

  return [pscustomobject]@{
    name    = $Name
    ok      = $ok
    seconds = [math]::Round($sw.Elapsed.TotalSeconds, 2)
    log     = $LogPath
    error   = $err
  }
}

function Invoke-WebhookFixtureSweep {
  param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$Secret
  )

  $fixtureRoot = Join-Path $Repo "fixtures\shopify_webhooks"
  $runner = Join-Path $Repo "tools\run_shopify_webhook_fixture.ps1"
  $targets = @("orders_cancelled", "orders_create", "orders_paid", "refunds_create")

  if (-not (Test-Path -LiteralPath $fixtureRoot)) { throw "FIXTURE_ROOT_NOT_FOUND=$fixtureRoot" }
  if (-not (Test-Path -LiteralPath $runner)) { throw "RUNNER_NOT_FOUND=$runner" }

  foreach ($name in $targets) {
    $fx = Join-Path $fixtureRoot $name
    $outDir = Join-Path $fx "out"
    $statusFile = Join-Path $outDir "status_code.txt"
    $log200 = Join-Path $outDir "burnin_200.log"
    $log409 = Join-Path $outDir "burnin_409.log"

    if (-not (Test-Path -LiteralPath $fx)) { throw "FIXTURE_NOT_FOUND=$fx" }

    if (Test-Path -LiteralPath $outDir) {
      Remove-Item -LiteralPath $outDir -Recurse -Force
    }
    New-Dir $outDir

    $cmd200 = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -FixtureDir "{1}" -Secret "{2}" -ExpectStatus 200 1> "{3}" 2>&1' -f $runner, $fx, $Secret, $log200
    cmd.exe /d /c $cmd200 | Out-Null
    $rc200 = $LASTEXITCODE
    $status200 = if (Test-Path -LiteralPath $statusFile) { [int]((Get-Content -LiteralPath $statusFile -Raw).Trim()) } else { -1 }

    $cmd409 = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -FixtureDir "{1}" -Secret "{2}" -ExpectStatus 409 1> "{3}" 2>&1' -f $runner, $fx, $Secret, $log409
    cmd.exe /d /c $cmd409 | Out-Null
    $rc409 = $LASTEXITCODE
    $status409 = if (Test-Path -LiteralPath $statusFile) { [int]((Get-Content -LiteralPath $statusFile -Raw).Trim()) } else { -1 }

    $ok200 = [int](($status200 -eq 200) -and ($rc200 -eq 0))
    $ok409 = [int](($status409 -eq 409) -and (($rc409 -eq 3) -or ($rc409 -eq 0)))
    $fixtureOk = [int](($ok200 -eq 1) -and ($ok409 -eq 1))

    Write-Host ("FIXTURE={0} OK={1} STATUS200={2} RC200={3} STATUS409={4} RC409={5}" -f $name, $fixtureOk, $status200, $rc200, $status409, $rc409)

    if ($fixtureOk -ne 1) {
      if (Test-Path -LiteralPath $log200) {
        Write-Host "FIXTURE_LOG_200_TAIL_BEGIN"
        Get-Content -LiteralPath $log200 -Tail 80
        Write-Host "FIXTURE_LOG_200_TAIL_END"
      }
      if (Test-Path -LiteralPath $log409) {
        Write-Host "FIXTURE_LOG_409_TAIL_BEGIN"
        Get-Content -LiteralPath $log409 -Tail 80
        Write-Host "FIXTURE_LOG_409_TAIL_END"
      }
      throw "FIXTURE_SWEEP_FAILED=$name"
    }
  }

  $global:LASTEXITCODE = 0
}

$repo = (Resolve-Path ".").Path
$pythonExe = Join-Path $repo "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
  $pythonExe = "python"
}

$env:SYNAPSE_FLAG_META_LIVE_API = "0"
$env:PYTHONDONTWRITEBYTECODE = "1"

Remove-Item -LiteralPath $OutputRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Dir $OutputRoot

Write-Host "BURNIN_START=1"
Write-Host "ITERATIONS=$Iterations"
Write-Host "PYTHON_EXE=$pythonExe"
Write-Host "OUTPUT_ROOT=$OutputRoot"

$allResults = New-Object System.Collections.Generic.List[object]
$summaryPath = Join-Path $OutputRoot "summary.json"

for ($i = 1; $i -le $Iterations; $i++) {
  $iterRoot = Join-Path $OutputRoot ("iter_" + $i.ToString("00"))
  New-Dir $iterRoot

  Write-Host ""
  Write-Host "════════════════════════════════════════════════════════════"
  Write-Host ("ITERATION_START={0}" -f $i)
  Write-Host "════════════════════════════════════════════════════════════"

  $steps = @(
    @{
      Name = "01_meta_pipeline_safe_client"
      Action = {
        & $pythonExe -m pytest `
          tests\meta\test_meta_safe_client.py `
          tests\meta\test_safe_client_alerts.py `
          tests\meta\test_pipeline_e2e.py `
          tests\meta\test_pipeline_e2e_feature_flags_contract.py
      }
    },
    @{
      Name = "02_buyer"
      Action = {
        & $pythonExe -m pytest `
          buyer\tests\test_buyer_block.py `
          buyer\tests\test_catalog_normalizer.py `
          buyer\tests\test_schemas.py `
          buyer\tests\test_scoring_rules.py
      }
    },
    @{
      Name = "03_ops_tick"
      Action = {
        & $pythonExe -m pytest `
          tests\p0\test_ops_tick_inventory_gate.py `
          tests\p0\test_ops_tick_l4.py `
          tests\p0\test_ops_tick_readonly_skip_downstream.py `
          tests\p0\test_ops_tick_reconcile_gate.py
      }
    },
    @{
      Name = "04_shopify_writer"
      Action = {
        & $pythonExe -m pytest `
          tests\shopify\test_shopify_writer.py `
          tests\shopify\test_shopify_writer_coerce_http_response.py `
          tests\shopify\test_shopify_writer_live_http_contract.py `
          tests\shopify\test_shopify_writer_run_graphql_contract.py
      }
    },
    @{
      Name = "05_webhook_fixture_runner"
      Action = {
        Invoke-WebhookFixtureSweep -Repo $repo -Secret $Secret
      }
    },
    @{
      Name = "06_webhook_pytests"
      Action = {
        & $pythonExe -m pytest `
          tests\integrations\test_shopify_webhook.py `
          tests\integrations\test_shopify_webhook_adapter.py `
          tests\integrations\test_shopify_webhook_cli.py `
          tests\integrations\test_shopify_webhook_fixtures_repo.py `
          tests\integrations\test_shopify_webhook_fixture_orders_cancelled.py `
          tests\integrations\test_shopify_webhook_fixture_refunds_create.py `
          tests\integrations\test_shopify_webhook_fixture_refunds_create_invalid.py
      }
    },
    @{
      Name = "07_refund_paths"
      Action = {
        & $pythonExe -m pytest `
          tests\infra\test_refund_ledger_bridge.py `
          tests\infra\test_refund_normalizer.py `
          tests\infra\test_refund_registry.py
      }
    }
  )

  [string[]]$normalizedIncludeSteps = @()

  if ($IncludeSteps.Count -gt 0) {
    foreach ($entry in $IncludeSteps) {
      if ($null -eq $entry) { continue }

      $parts = @(
        ($entry.ToString() -split '[,\s]+' | Where-Object { $_ -and $_.Trim().Length -gt 0 })
      )

      foreach ($part in $parts) {
        $normalizedIncludeSteps += $part.Trim()
      }
    }

    $normalizedIncludeSteps = @($normalizedIncludeSteps | Select-Object -Unique)

    Write-Host ("INCLUDE_STEPS_NORMALIZED={0}" -f ($normalizedIncludeSteps -join ','))

    $steps = @($steps | Where-Object { $_.Name -in $normalizedIncludeSteps })
  }

  if ($steps.Count -eq 0) {
    throw "NO_STEPS_SELECTED"
  }

  foreach ($step in $steps) {
    $logPath = Join-Path $iterRoot ($step.Name + ".log")

    Write-Host ""
    Write-Host ("STEP_START={0}" -f $step.Name)
    Write-Host ("LOG_PATH={0}" -f $logPath)

    $result = Invoke-Step -Name $step.Name -Action $step.Action -LogPath $logPath
    $result | Add-Member -NotePropertyName iteration -NotePropertyValue $i
    $allResults.Add($result) | Out-Null

    Write-Host ("STEP_DONE={0}" -f $step.Name)
    Write-Host ("STEP_OK={0}" -f ([int]$result.ok))
    Write-Host ("STEP_SECONDS={0}" -f $result.seconds)
    if (-not $result.ok) {
      Write-Host ("STEP_ERROR={0}" -f $result.error)
    }

    Write-SummaryFile -Path $summaryPath -Iterations $Iterations -Results $allResults.ToArray()

    if ($StopOnFirstFailure -and -not $result.ok) {
      break
    }
  }

  if ($StopOnFirstFailure -and @($allResults | Where-Object { $_.iteration -eq $i -and -not $_.ok }).Count -gt 0) {
    break
  }
}

Write-SummaryFile -Path $summaryPath -Iterations $Iterations -Results $allResults.ToArray()

$summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════"
Write-Host "BURN-IN SUMMARY"
Write-Host "════════════════════════════════════════════════════════════"
Write-Host "ITERATIONS=$($summary.iterations)"
Write-Host "TOTAL_STEPS=$($summary.total_steps)"
Write-Host "PASSED_STEPS=$($summary.passed_steps)"
Write-Host "FAILED_STEPS=$($summary.failed_steps)"
Write-Host "OVERALL=$($summary.overall)"
Write-Host "SUMMARY_PATH=$summaryPath"

if ([int]$summary.failed_steps -ne 0) {
  exit 1
}

exit 0


