V3GAP:C-01_dropi_payment_timing
tranche: T2
category: EXTERNAL_STUB
closure_type: runtime_guard_with_external_dependency
implementation_state: code_and_runtime_seam
manual_blocker: false
external_dependency: true
production_release_blocked: true

# T2 Closure Record — C-01_dropi_payment_timing

intent:
Formalizar timing de pago Dropi con contrato ejecutable y seam runtime ya presentes en el sistema, manteniendo explícita la dependencia externa del proveedor.

control:
El sistema no habilita pago a proveedor hasta que el contrato marque `supplier_payment_ready=true`. La automatización end-to-end con proveedor sigue siendo dependencia externa.

acceptance:
- gap_id=C-01_dropi_payment_timing
- tranche=T2
- category=EXTERNAL_STUB
- closure_type=runtime_guard_with_external_dependency
- implementation_state=code_and_runtime_seam
- manual_blocker=false
- external_dependency=true
- production_release_blocked=true

notes:
- Contrato ejecutable presente en `synapse/integrations/dropi/payment_timing.py`
- Cobertura dedicada presente en `tests/integrations/dropi/test_payment_timing_contract.py`
- Seam runtime confirmado vía `synapse/integrations/dropi/payment_guarantee_bridge.py`
- La dependencia del proveedor sigue viva; el ledger T2 anterior quedó desactualizado respecto al runtime real.