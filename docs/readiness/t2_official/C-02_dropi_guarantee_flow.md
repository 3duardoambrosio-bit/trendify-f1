V3GAP:C-02_dropi_guarantee_flow
tranche: T2
category: EXTERNAL_STUB
closure_type: runtime_guard_with_external_dependency
implementation_state: code_and_runtime_seam
manual_blocker: false
external_dependency: true
production_release_blocked: true

# T2 Closure Record — C-02_dropi_guarantee_flow

intent:
Formalizar flujo de garantía Dropi con contrato ejecutable y seam runtime ya presentes en el sistema, manteniendo explícita la dependencia externa del proveedor para resolución real.

control:
El sistema no abre automáticamente flujo productivo de garantía sin pasar por el guardrail runtime y sin respetar el estado `supplier_payment_ready`. La resolución final sigue dependiendo del proveedor.

acceptance:
- gap_id=C-02_dropi_guarantee_flow
- tranche=T2
- category=EXTERNAL_STUB
- closure_type=runtime_guard_with_external_dependency
- implementation_state=code_and_runtime_seam
- manual_blocker=false
- external_dependency=true
- production_release_blocked=true

notes:
- Contrato ejecutable presente en `synapse/integrations/dropi/guarantee_flow.py`
- Cobertura dedicada presente en `tests/integrations/dropi/test_guarantee_flow_contract.py`
- Seam runtime confirmado vía `synapse/integrations/dropi/payment_guarantee_bridge.py`
- La dependencia del proveedor sigue viva; el ledger T2 anterior quedó desactualizado respecto al runtime real.