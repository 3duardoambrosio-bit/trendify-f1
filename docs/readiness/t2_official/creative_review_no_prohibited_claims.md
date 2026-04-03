V3GAP:creative_review_no_prohibited_claims
tranche: T2
category: LEGAL_POLICY
closure_type: policy_guardrail
implementation_state: non_code
manual_blocker: false
external_dependency: false
production_release_blocked: true

# T2 Closure Record — creative_review_no_prohibited_claims

intent:
Bloquear creativos con claims prohibidos, absolutos, engañosos o no verificables.

control:
No se autoriza publicación si el creativo no pasa revisión manual contra claims prohibidos.

acceptance:
- gap_id=creative_review_no_prohibited_claims
- tranche=T2
- category=LEGAL_POLICY
- closure_type=policy_guardrail
- implementation_state=non_code
- production_release_blocked=true

notes:
Cobertura documental T2. No habilita auto-approval.