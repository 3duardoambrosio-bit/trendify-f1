V3GAP:cod_pre_confirmation
tranche: T2
category: EXTERNAL_STUB
closure_type: ops_stub
implementation_state: non_code
manual_blocker: true
external_dependency: true
production_release_blocked: true

# T2 Closure Record — cod_pre_confirmation

intent:
Fijar pre-confirmación COD como control operativo previo a despacho.

control:
Si no existe confirmación válida previa, el pedido COD no avanza automáticamente.

acceptance:
- gap_id=cod_pre_confirmation
- tranche=T2
- category=EXTERNAL_STUB
- closure_type=ops_stub
- implementation_state=non_code
- production_release_blocked=true

notes:
Stub operativo. Automatización queda diferida.