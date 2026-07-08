V3GAP:F-03_nom_verification_flag
tranche: T2
category: LEGAL_POLICY
closure_type: compliance_flag_policy
implementation_state: non_code
manual_blocker: false
external_dependency: false
production_release_blocked: true

# T2 Closure Record — F-03_nom_verification_flag

intent:
Exigir validación NOM para productos/categorías que lo requieran.

control:
Si no existe verificación documental NOM, el producto no se publica.

acceptance:
- gap_id=F-03_nom_verification_flag
- tranche=T2
- category=LEGAL_POLICY
- closure_type=compliance_flag_policy
- implementation_state=non_code
- production_release_blocked=true

notes:
Cobertura documental T2. No es motor por SKU.