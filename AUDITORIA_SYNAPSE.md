# AUDITORIA SYNAPSE - 2026-02-01

## RESUMEN EJECUTIVO
- Total issues: 5
- P0: 4
- P1: 1
- P2: 0
- Tests: 0 passing / 1 failing
- Veredicto: **NO-GO**
- Riesgo principal: Hay rutas de gasto que pueden ejecutar `vault.request_spend(...)` sin pasar por `check_safety_before_spend()` y además hay estado crítico de presupuesto/idempotencia que vive solo en memoria. Un restart puede permitir doble gasto sin protección ni kill switch persistente.

---

## MAPEO RAPIDO (alto nivel)
- ops/: SpendGateway, CapitalShield, Autopilot, SafetyMiddleware.
- infra/: ledger_v2, vault (budget), idempotency.
- vault/: implementaciones v1/v0 de vault.
- synapse/safety/: KillSwitch, CircuitBreaker, SafetyGate.
- tests/: contract tests y safety tests.

## VERIFICACION CHOKE POINT (SafetyMiddleware)
- Único lugar explícito que llama `check_safety_before_spend()` es `ops/spend_gateway_v1.py`.
- `CapitalShieldV2` y `AutopilotV2` llaman `vault.request_spend(...)` sin pasar por `check_safety_before_spend()`. Esto es un bypass si esos flujos se usan en producción.

---

## P0 - CRITICOS

### [P0-001] Bypass de SafetyMiddleware via CapitalShieldV2/AutopilotV2
- **Archivo:** ops/autopilot_v2.py + ops/capital_shield_v2.py
- **Línea:** ~89-158 (autopilot) / ~99-100 (capital_shield_v2)
- **Problema:** AutopilotV2 delega gasto a CapitalShieldV2, y CapitalShieldV2 llama directo a `vault.request_spend(...)` sin pasar por `check_safety_before_spend()`.
- **Riesgo:** Si AutopilotV2 se usa en producción, el gasto puede ejecutarse sin killswitch/circuit breaker, violando la regla de oro del flujo de dinero.
- **Evidencia (snippet):**
  ```py
  # ops/autopilot_v2.py
  self._shield = CapitalShieldV2(vault=vault, default_budget_type=default_budget_type)
  capital_decision = self._shield.decide_for_product(...)
  
  # ops/capital_shield_v2.py
  result = self._vault.request_spend(amount, btype)
  ```
- **Fix (exacto):** En `ops/capital_shield_v2.py`, envolver la llamada a `vault.request_spend(...)` con `check_safety_before_spend()` (de `ops/safety_middleware.py`) y bloquear si falla. Alternativa: forzar que AutopilotV2 use SpendGateway (que ya invoca SafetyMiddleware) antes de tocar el vault.

### [P0-002] Caps de learning en memoria (reinicio = presupuesto reseteado)
- **Archivo:** ops/spend_gateway_v1.py
- **Línea:** ~60-74, ~208-266
- **Problema:** Los acumulados `_learn_total_by_product` y `_learn_day1_by_product` viven en memoria. Un restart borra el tracking y permite re-gastar el cap diario/total.
- **Riesgo:** Doble gasto inmediato después de restart, especialmente en “day 1” donde los caps son más agresivos.
- **Evidencia (snippet):**
  ```py
  self._learn_total_by_product: Dict[str, Decimal] = {}
  self._learn_day1_by_product: Dict[str, Decimal] = {}
  ...
  total_so_far = self._learn_total_by_product.get(product_id, Decimal("0"))
  day1_so_far = self._learn_day1_by_product.get(product_id, Decimal("0"))
  ...
  self._learn_total_by_product[product_id] = ...
  self._learn_day1_by_product[product_id] = ...
  ```
- **Fix (exacto):** Persistir estos acumulados en `infra/ledger_v2.py` (o storage durable) y reconstruirlos al iniciar SpendGateway. Guardar por `product_id + day` y usar `fsync` en eventos críticos.

### [P0-003] Idempotencia no obligatoria + almacenamiento sólo en memoria
- **Archivo:** ops/spend_gateway_v1.py + infra/idempotency_manager.py
- **Línea:** ~60-73, ~160-171 (gateway) / ~7-39 (idempotency)
- **Problema:** El gateway acepta `idempotency_manager` opcional y si no se pasa, no hay deduplicación real. Además, `IdempotencyManager` guarda en dict en memoria.
- **Riesgo:** Reintentos de red pueden duplicar gasto; un restart elimina histórico de idempotencia.
- **Evidencia (snippet):**
  ```py
  # ops/spend_gateway_v1.py
  idempotency_manager: Optional[IdempotencyManager] = None
  if self._idempotency is not None and self._idempotency.is_processed(idem_key):
      ...
  
  # infra/idempotency_manager.py
  self._storage: Dict[str, Dict[str, Any]] = {}
  ```
- **Fix (exacto):** Hacer `idempotency_key` obligatorio en `SpendGateway.request(...)` y usar un backend durable (LedgerV2 o DB) para guardar resultados con TTL.

### [P0-004] Vault (infra) sin persistencia de estado
- **Archivo:** infra/vault.py
- **Línea:** ~138-175
- **Problema:** `Vault` muta `spent_learning`/`spent_operational` en memoria y no persiste a disco ni ledger.
- **Riesgo:** Restart = saldo gastado vuelve a cero → permite gastar doble sobre el mismo presupuesto.
- **Evidencia (snippet):**
  ```py
  if bucket == "learning":
      self.spent_learning = _q2(self.spent_learning + amt)
  else:
      self.spent_operational = _q2(self.spent_operational + amt)
  ```
- **Fix (exacto):** Persistir el estado del vault (o los eventos de gasto) en `infra/ledger_v2.py` con reconstrucción al iniciar. Requiere fsync en cada gasto crítico.

---

## P1 - RIESGO ALTO

### [P1-001] Eventos de ledger en SpendGateway sin fsync
- **Archivo:** ops/spend_gateway_v1.py
- **Línea:** ~103-110
- **Problema:** `_append_ndjson` escribe al ledger con `f.write(...)` sin `flush`+`fsync`.
- **Riesgo:** En crash del proceso/OS, se pierde el evento más reciente → auditoría incompleta.
- **Evidencia (snippet):**
  ```py
  with path.open("a", encoding="utf-8") as f:
      f.write(line + "\n")
  ```
- **Fix (exacto):** Agregar `f.flush()` y `os.fsync(f.fileno())`, o delegar al `LedgerV2.write(..., critical=True)` para eventos de gasto.

---

## P2 - HIGIENE
- Sin hallazgos P2 relevantes mientras existan P0/P1.

---

## MÓDULOS CRÍTICOS - ESTADO
- **killswitch.py:** OK (tiene persistencia opcional con escritura atómica y fsync cuando `state_file` está configurado). Evidencia: `KillSwitch.__init__` y `_atomic_write`. 
- **circuit.py:** OK (persistencia opcional y backoff exponencial). Evidencia: `CircuitBreaker.__init__`, `_atomic_write`, `_current_cooldown`. 
- **ledger_v2.py:** OK (fsync y flush periódicos). Evidencia: `_flush_unlocked` y `_periodic_flush`.
- **capital_shield_v2.py:** NO (gasta sin SafetyMiddleware). Evidencia: llamada directa a `vault.request_spend(...)`.
- **spend_gateway_v1.py:** PARCIAL (sí usa SafetyMiddleware, pero caps e idempotencia no son durables). Evidencia: `_learn_total_by_product` y `_idempotency` opcional.
- **safety_middleware.py:** OK (choke point implementado, pero no se usa en todos los flows). Evidencia: `check_safety_before_spend(...)`.

---

## DUPLICADOS V1/V2
- **capital_shield:** `ops/capital_shield.py` (v1, deprecated) vs `ops/capital_shield_v2.py` (v2). **Riesgo:** coexistencia puede causar tracking doble si ambos se usan. **Acción:** deprecación total de v1 y migrar call sites.
- **ledger:** `core/ledger.py` (v1) vs `infra/ledger_v2.py` (v2). **Riesgo:** eventos en formatos distintos; pérdida de trazabilidad. **Acción:** consolidar en ledger_v2.
- **vault:** `vault/vault_v1.py`, `vault/v1.py`, `infra/vault.py`. **Riesgo:** múltiples interfaces de gasto pueden saltar controles. **Acción:** definir un único vault canónico y eliminar rutas antiguas.

---

## TESTS
- **Comando:** `pytest -q`
- **Resultado:** FAIL (dependencia faltante en entorno actual)
- **Output relevante (resumido):**
  ```
  ImportError while loading conftest '/workspace/trendify-f1/tests/conftest.py'.
  ModuleNotFoundError: No module named 'hypothesis'
  ```
- **Nota:** Se intentó instalar deps con `pip install -e .[dev]`, pero falló por restricción de red/proxy (403) al resolver build deps.

---

## TOP 3 FIXES URGENTES
1) Envolver TODO gasto en `check_safety_before_spend()` (prioridad: `CapitalShieldV2`/`AutopilotV2`).
2) Persistir estado crítico de presupuesto: caps de SpendGateway y estado del Vault en ledger durable.
3) Idempotencia obligatoria y persistente para cualquier gasto (no sólo in-memory).
