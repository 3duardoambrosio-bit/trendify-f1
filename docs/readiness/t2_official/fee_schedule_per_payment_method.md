V3GAP:fee_schedule_per_payment_method
tranche: T2
category: EXTERNAL_STUB
closure_type: external_fee_stub
implementation_state: non_code
manual_blocker: true
external_dependency: true
production_release_blocked: true

# T2 Closure Record — fee_schedule_per_payment_method

intent:
Formalizar tabla de fees por método de pago como input externo variable.

control:
No se congela pricing final sin fee schedule real por método.

acceptance:
- gap_id=fee_schedule_per_payment_method
- tranche=T2
- category=EXTERNAL_STUB
- closure_type=external_fee_stub
- implementation_state=non_code
- production_release_blocked=true

notes:
Stub operativo. Fuente real pendiente.