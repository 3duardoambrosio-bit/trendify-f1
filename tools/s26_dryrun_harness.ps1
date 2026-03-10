param()

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

$taskName = "SYNAPSE_ops_tick_readonly_q2h"
$artifactDir = Join-Path $env:TEMP ("synapse_s26_dryrun_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null

Write-Host "════════════════════════════════════════════════════════════"
Write-Host "S26 DRY-RUN HARNESS"
Write-Host "════════════════════════════════════════════════════════════"

Write-Host "`n=== 0) BASELINE ==="
$porc0 = @(git status --porcelain)
$norm0 = $porc0 | ForEach-Object { $_.Replace("\","/") }
$norm0 | ForEach-Object { $_ }
"dirty_lines_before=$($norm0.Count)"

$expectedDirty = @(
  "?? docs/RUNBOOK_DRYRUN.md",
  "?? tools/s26_dryrun_harness.ps1"
)
if ($norm0.Count -ne 2) { throw "HARNESS_BASELINE_DIRTY_COUNT" }
foreach ($e in $expectedDirty) {
  if ($norm0 -notcontains $e) { throw "HARNESS_BASELINE_MISSING_$e" }
}

Write-Host "`n=== 1) SCHEDULER EXISTS ==="
& cmd.exe /c "schtasks /Query /TN ""$taskName"" >nul 2>nul"
"scheduler_exists=$([int]($LASTEXITCODE -eq 0))"
if ($LASTEXITCODE -ne 0) { throw "SCHEDULER_NOT_FOUND" }

Write-Host "`n=== 2) TARGETED TESTS ==="
pytest -q `
  tests\infra\test_refund_normalizer.py `
  tests\infra\test_refund_registry.py `
  tests\infra\test_refund_ledger_bridge.py `
  tests\infra\test_shopify_ledger_reconcile.py `
  tests\p0\test_ops_tick_inventory_gate.py `
  tests\p0\test_ops_tick_reconcile_gate.py `
  tests\p0\test_ops_tick_readonly_skip_downstream.py
"targeted_pytest_exit=$LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { throw "TARGETED_TESTS_FAILED" }

Write-Host "`n=== 3) READONLY OPS_TICK ==="
python -m synapse.ops_tick --no-import --readonly
"readonly_exitcode=$LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { throw "READONLY_OPS_TICK_FAILED" }

$report = Join-Path $repo "data\run\ops_tick.json"
if (-not (Test-Path $report)) { throw "OPS_TICK_REPORT_MISSING" }
$reportObj = Get-Content $report -Raw | ConvertFrom-Json
"ops_tick_report_status=$($reportObj.status)"
"ops_tick_report_marker=$($reportObj.marker)"
if ($reportObj.status -ne "OK") { throw "OPS_TICK_REPORT_NOT_OK" }

Write-Host "`n=== 4) MULTI-REFUND SAME ORDER CHECK ==="
python -c "from decimal import Decimal; from synapse.infra.shopify_ledger_reconcile import reconcile_shopify_vs_ledger, ReconcileConfig; shop=[{'id':1,'financial_status':'paid','current_total_price':'70.00','total_price':'100.00','currency':'MXN'}]; led=[{'order_id':'1','amount_mxn':'100.00'},{'event_type':'SHOPIFY_REFUND_RECORDED','payload':{'refund_id':'rf_1','order_id':'1','amount_mxn':'20.00','currency':'MXN'}},{'event_type':'SHOPIFY_REFUND_RECORDED','payload':{'refund_id':'rf_2','order_id':'1','amount_mxn':'10.00','currency':'MXN'}}]; r=reconcile_shopify_vs_ledger(shop,led,ReconcileConfig(tolerance_mxn=Decimal('0.01'),require_shopify_paid_only=True)); print(f'multi_refund_same_order_pass={int(r.ok and (not r.blocked) and r.missing_count==0 and r.mismatch_count==0 and r.extra_count==0)}'); assert r.ok is True and r.blocked is False and r.missing_count==0 and r.mismatch_count==0 and r.extra_count==0"
"multi_refund_script_exitcode=$LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { throw "MULTI_REFUND_CHECK_FAILED" }

Write-Host "`n=== 5) DUPLICATE REFUND BRIDGE CHECK ==="
python -c "from decimal import Decimal; from pathlib import Path; from tempfile import TemporaryDirectory; from synapse.infra.refund_ledger_bridge import record_refund_in_ledger; from synapse.infra.refund_normalizer import RefundEvent; td=TemporaryDirectory(); root=Path(td.name); ledger=root/'refund_ledger.ndjson'; idem=root/'refund_ledger_idempotency.json'; ev=RefundEvent(refund_id='rf_dup_1',order_id='ord_1',amount=Decimal('25.00'),currency='MXN',reason='other',created_at='2026-03-09T00:00:00Z',line_items=('SKU-1',),source='webhook'); r1=record_refund_in_ledger(ledger,idem,ev); r2=record_refund_in_ledger(ledger,idem,ev); lines=[x for x in ledger.read_text(encoding='utf-8').splitlines() if x.strip()]; ok=(r1.recorded is True and r1.duplicate is False and r2.recorded is False and r2.duplicate is True and len(lines)==1); print(f'duplicate_bridge_pass={int(ok)}'); assert ok"
"duplicate_bridge_script_exitcode=$LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { throw "DUPLICATE_BRIDGE_CHECK_FAILED" }

Write-Host "`n=== 6) INVALID REFUND FAIL-CLOSED CHECK ==="
pytest -q tests\integrations\test_shopify_webhook_fixture_refunds_create_invalid.py
"invalid_refund_pytest_exit=$LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { throw "INVALID_REFUND_FAIL_CLOSED_FAILED" }

Write-Host "`n=== 7) FULL SUITE ==="
pytest -q
"full_pytest_exit=$LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { throw "FULL_SUITE_FAILED" }

Write-Host "`n=== 8) FINAL STATUS ==="
$porc1 = @(git status --porcelain)
$norm1 = $porc1 | ForEach-Object { $_.Replace('\','/') }
$norm1 | ForEach-Object { $_ }
"dirty_lines_after=$($norm1.Count)"

if ($norm1.Count -ne 2) { throw "UNEXPECTED_DIRTY_AFTER_COUNT" }
foreach ($e in $expectedDirty) {
  if ($norm1 -notcontains $e) { throw "UNEXPECTED_DIRTY_AFTER_ENTRY_$e" }
}

Write-Host "`n=== 9) ACCEPTANCE SNAPSHOT ==="
"ACCEPT_scheduler_exists=1"
"ACCEPT_targeted_pytest_exit=0"
"ACCEPT_readonly_exitcode=0"
"ACCEPT_ops_tick_report_status=OK"
"ACCEPT_multi_refund_script_exitcode=0"
"ACCEPT_duplicate_bridge_script_exitcode=0"
"ACCEPT_invalid_refund_pytest_exit=0"
"ACCEPT_full_pytest_exit=0"
"ACCEPT_dirty_lines_after=2"