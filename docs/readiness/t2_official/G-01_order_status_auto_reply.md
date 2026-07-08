V3GAP:G-01_order_status_auto_reply
tranche: T2
category: EXTERNAL_STUB
closure_type: customer_comms_stub
implementation_state: non_code
manual_blocker: true
external_dependency: true
production_release_blocked: true

# T2 Closure Record — G-01_order_status_auto_reply

intent:
Registrar respuesta automática de status de pedido como capacidad aún no implementada.

control:
Toda respuesta de estado cae a fallback manual/documentado.

acceptance:
- gap_id=G-01_order_status_auto_reply
- tranche=T2
- category=EXTERNAL_STUB
- closure_type=customer_comms_stub
- implementation_state=non_code
- production_release_blocked=true

notes:
Stub operativo. No se promete auto-reply live.