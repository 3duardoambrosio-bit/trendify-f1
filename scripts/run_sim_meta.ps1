Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Runbook: simulate pipeline + report
python -m synapse.meta_api_day_meta --mode simulate --status PAUSED `
  --daily-budget 500 `
  --targeting-json @exports/targeting_mx_broad.json `
  --promoted-object-json @exports/promoted_object_purchase.json `
  --page-id 123 `
  --ig-actor-id 123 `
  --pixel-id 123

python -m synapse.meta_run_report

Write-Host "`n✅ Listo. Reporte en:"
Write-Host " - data/run/meta_publish_report.txt"
Write-Host " - data/run/meta_publish_report.json"
