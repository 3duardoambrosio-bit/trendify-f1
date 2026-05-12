# A8-R43E Medium Risk Debt Marker Registry

## Summary

- MODE=LOCAL_ONLY_CODE_HARDENING
- BASE_HEAD=928ce16
- MEDIUM_RISK_COUNT=90
- UNMANAGED_MEDIUM_RISK_COUNT=0
- HIGH_RISK_COUNT=35
- DECISION=register before reducing medium-risk noise

## Rule

Medium-risk debt markers remain allowed only when registered. Reduction must be behavior-preserving and covered by checks.

## Entries

- assets/_text/Hh9_Adolor_Fhands_V1.txt:1 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — Si te duele tu producto y ya probaste de todo… ve esto.
- AUDITORIA_SYNAPSE.md:11 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — Motivo principal: los modulos de seguridad financiera (capital_shield, killswitch, circuit_breaker) no persisten estado. Un restart del proceso pierde TODO el tracking de gasto y permite re-gastar el presupuesto completo. Ademas, el sistema
- AUDITORIA_SYNAPSE.md:20 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - **Problema:** `_daily_state` es un dict en memoria. Al reiniciar el proceso, todo el tracking de gasto diario se pierde. El sistema permite re-gastar el presupuesto completo.
- AUDITORIA_SYNAPSE.md:47 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - **Linea:** Todo el directorio
- AUDITORIA_SYNAPSE.md:102 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - **Riesgo:** Configuracion enganiosa. Operador cree que hay limites learning/testing pero no se aplican. Todo el gasto va contra el cap unico.
- AUDITORIA_SYNAPSE.md:130 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - **Riesgo:** Vault caido = todo gasto bloqueado sin diagnostico. No se puede distinguir "sin presupuesto" de "vault roto".
- AUDITORIA_SYNAPSE.md:147 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - **Problema:** `except:` sin tipo especifico. Atrapa SystemExit, KeyboardInterrupt y todo.
- AUDITORIA_SYNAPSE.md:207 [DEPRECATED] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - **Problema:** `datetime.utcnow()` esta deprecated desde Python 3.12. No genera timezone-aware datetimes.
- AUDITORIA_SYNAPSE.md:208 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - **Fix:** Reemplazar por `datetime.now(timezone.utc)` en todo el codebase.
- AUDITORIA_SYNAPSE.md:262 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - **Veredicto:** Migrar todo a v2, deprecar v1.
- AUDITORIA_SYNAPSE.md:286 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — | scripts/build_canonical_from_dropi.py | scripts/build_canonical_from_dropi_v2.py, v3.py | v3 es el activo | v1/v2 son legacy |
- AUDITORIA_SYNAPSE.md:312 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - tests/legacy/ (1 test) - legacy cleanup
- config/revenue_engineering/modules.json:15 [HACK] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — {"id":"M07","name":"COD Risk Scoring Gate","status":"INJECT","inject_session":"S11+S15b","reason":"Mitiga pérdidas COD; implementar elegibilidad clara (no CSS hack)."},
- dash/control_tower.html:214 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — <div class="small mut">Fuente principal: <span class="mono">control_tower_snapshot.json</span> (fallback a JSONs legacy)</div>
- dash/control_tower.html:382 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — // fallback mínimo para que no muera todo si no hay snapshot
- dash/control_tower.html:521 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — setText("rawHint", "Snapshot no cargó; usando fallback legacy.");
- data/launch/r003/02_shopify_copy.md:17 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — Tu compu suena como avión y tu teclado ya parece alfombra. Este soplador recargable avienta aire con potencia seria para limpiar donde el trapo y la aspiradora no llegan. Es la herramienta que todo setup necesita para durar más y verse limp
- data/launch/r003/03_creatives.md:9 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — 6) La herramienta que todo PC gamer necesita y nadie compra.
- data/launch/r003/03_creatives.md:36 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - Close: boquillas + “sirve para TODO”
- data/launch/r003/03_creatives.md:56 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - Mantén todo igual excepto hook/video.
- infra/bitacora_auto.py:72 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — """Recarga todo desde disco a memoria."""
- infra/bitacora_auto.py:159 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — # Singleton de conveniencia para código legacy
- infra/config_loader.py:23 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — Todo lo que afecte decisiones de aprobación/rechazo de productos
- infra/feature_flags.py:3 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — """Compatibility shim for legacy infra.feature_flags imports."""
- infra/vault.py:91 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - Todo dinero se maneja con Decimal.
- marketing_os/test_interrogation_engine.py:395 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — name="Pastilla Cura Todo FDA",
- marketing_os/test_quality_filter.py:95 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — """Todo mayúsculas debe detectarse."""
- marketing_os/test_quality_filter.py:276 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — """Reset debe limpiar todo."""
- ops/capital_shield_v1_DEPRECATED.py:1 [DEPRECATED] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — # DEPRECATED: No usar. Migrar a capital_shield_v2.py
- ops/capital_shield_v1_DEPRECATED.py:6 [DEPRECATED] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — warnings.warn("capital_shield v1 is deprecated, use capital_shield_v2", DeprecationWarning, stacklevel=2)
- ops/dropi_dump_ingest.py:221 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — # Normaliza todo
- ops/exit_criteria.py:26 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — - Todo es a nivel agregado (producto completo, no campañas).
- ops/tests/test_capital_shield.py:5 [DEPRECATED] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — message=r"^capital_shield v1 is deprecated, use capital_shield_v2$",
- pytest.ini:6 [DEPRECATED] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — ignore:capital_shield v1 is deprecated, use capital_shield_v2:DeprecationWarning
- scripts/gate_f1.ps1:7 [TEMPORARY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — # Keep pytest temporary cleanup outside the repository on Windows.
- scripts/run_pytest_stable.ps1:11 [TEMPORARY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — # Keep pytest temporary cleanup outside the repository on Windows.
- synapse/creative_briefs.py:72 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — "h9": "Si te duele tu producto y ya probaste de todo… ve esto.",
- synapse/infra/doctor.py:8 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — GREEN: Todo OK
- synapse/infra/doctor.py.bak_20260103_233128:9 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — GREEN: Todo OK
- synapse/marketing_os/creative_factory.py:14 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — Quality Filter aplicado a TODO.
- synapse/marketing_os/creative_factory.py:75 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — "El detalle perfecto para quien tiene todo",
- synapse/marketing_os/creative_factory.py:417 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — "response": "Envío express 3-5 días a todo México.",
- synapse_app.html:791 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — setCrumb("SYNAPSE / Bitácora", "Todo queda registrado. Nada de ‘yo juraba que…’.");
- synapse_console.html:357 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — <button class="btn" id="btnDemo" title="Carga data de demo (para ver todo funcionando)">✨ Demo</button>
- synapse_console.html:654 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — <div class="s">Mientras tanto, <b>simulate</b> funciona como “modo avión”: todo fluye sin tocar Meta.</div>
- synapse_console.html:965 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — "Conversion tracking: si no hay pixel bien, todo es teatro.",
- synapse_console.html:992 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — "Todo queda en run history NDJSON/JSON para auditar.",
- tools/check_a8_r43d_debt_marker_registry.ps1:40 [HACK] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — if ($lower -match "bypass|skip|unsafe|disable|temporary|workaround|hack") {
- tools/check_a8_r43d_debt_marker_registry.ps1:40 [TEMPORARY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — if ($lower -match "bypass|skip|unsafe|disable|temporary|workaround|hack") {
- tools/check_a8_r43d_debt_marker_registry.ps1:40 [WORKAROUND] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — if ($lower -match "bypass|skip|unsafe|disable|temporary|workaround|hack") {
- tools/check_a8_r43d_debt_marker_registry.ps1:47 [FIXME] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — if ($Marker -in @("FIXME", "HACK", "XXX")) {
- tools/check_a8_r43d_debt_marker_registry.ps1:47 [HACK] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — if ($Marker -in @("FIXME", "HACK", "XXX")) {
- tools/check_a8_r43d_debt_marker_registry.ps1:47 [XXX] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — if ($Marker -in @("FIXME", "HACK", "XXX")) {
- tools/check_a8_r43d_debt_marker_registry.ps1:51 [DEPRECATED] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — if ($lower -match "temporary|workaround|deprecated|legacy") {
- tools/check_a8_r43d_debt_marker_registry.ps1:51 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — if ($lower -match "temporary|workaround|deprecated|legacy") {
- tools/check_a8_r43d_debt_marker_registry.ps1:51 [TEMPORARY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — if ($lower -match "temporary|workaround|deprecated|legacy") {
- tools/check_a8_r43d_debt_marker_registry.ps1:51 [WORKAROUND] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — if ($lower -match "temporary|workaround|deprecated|legacy") {
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [DEBT] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [DEPRECATED] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [FIXME] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [HACK] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [TBD] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [TECH_DEBT] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [TEMPORARY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [WORKAROUND] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:73 [XXX] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [DEBT] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [DEPRECATED] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [FIXME] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [HACK] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [TBD] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [TECH_DEBT] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [TEMPORARY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [TODO] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [WORKAROUND] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- tools/check_a8_r43d_debt_marker_registry.ps1:88 [XXX] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
- vault/cashflow_v1.py:47 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — This structure is reporting-oriented and does NOT mutate the legacy global
- vault/cashflow_v1.py:97 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — legacy buffer (compat). Se usa en State.can_spend / net_available.
- vault/cashflow_v1.py:116 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — safety_buffer_cash: Decimal = D0  # legacy compat
- vault/cashflow_v1.py:133 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — # legacy behavior:
- vault/cashflow_v1.py:145 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — # legacy alias
- vault/cashflow_v1.py:211 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — Uses config.safety_buffer if set, else falls back to state.safety_buffer_cash (legacy).
- vault/cashflow_v1.py:221 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — legacy = _d(self.state.safety_buffer_cash)
- vault/cashflow_v1.py:222 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — return legacy if legacy > D0 else D0
- vault/cashflow_v1.py:233 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — # legacy alias
- vault/cashflow_v1.py:245 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — # legacy alias
- vault/cashflow_v1.py:262 [LEGACY] REGISTERED_MEDIUM_RISK_REVIEW_REQUIRED_BEFORE_EDIT — # --- Legacy exports (older modules/tests) ---
