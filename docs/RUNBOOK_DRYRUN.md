# RUNBOOK DRY-RUN  SYNAPSE

## Objetivo
Certificar el sistema en modo simulación controlada, sin dinero real, validando que:
- el scheduler readonly existe
- ops_tick --no-import --readonly termina en OK
- el pipeline de refunds funciona end-to-end
- el reconcile refund-aware netea correctamente múltiples refunds
- la idempotencia del refund ledger bridge se mantiene
- el repo permanece limpio durante la corrida

## Alcance
Este runbook NO lanza campañas reales.
Este runbook NO mueve dinero real.
Este runbook NO requiere listener HTTP público.
Este runbook sí valida la coherencia operativa del sistema actual.

## Regla operativa crítica
Si existe un refund en Shopify y todavía no ha sido procesado por SYNAPSE, el reconcile puede bloquear falsamente.
Orden correcto:
1. procesar refund fixture / refund input
2. verificar refund_event + refund_registry + refund_ledger
3. correr reconcile refund-aware

## Stop Conditions
Detener la corrida si pasa cualquiera de estas:
- dirty_lines_before != 0
- scheduler_exists != 1
- readonly_exitcode != 0
- ops_tick_report_status != OK
- multi_refund_script_exitcode != 0
- duplicate_bridge_script_exitcode != 0
- invalid_refund_pytest_exit != 0
- full_pytest_exit != 0

## Comando canónico
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\s26_dryrun_harness.ps1

## Aceptación
La corrida se considera PASS solo si:
- scheduler_exists=1
- targeted_pytest_exit=0
- readonly_exitcode=0
- ops_tick_report_status=OK
- multi_refund_script_exitcode=0
- duplicate_bridge_script_exitcode=0
- invalid_refund_pytest_exit=0
- full_pytest_exit=0

## Evidencia mínima
- output completo de terminal
- head_short
- ops_tick_report_marker
- acceptance snapshot final

## Estado esperado al final
- corrida PASS
- repo limpio excepto docs/RUNBOOK_DRYRUN.md y tools/s26_dryrun_harness.ps1 antes del commit
- sistema listo para dry-run funcional simulado