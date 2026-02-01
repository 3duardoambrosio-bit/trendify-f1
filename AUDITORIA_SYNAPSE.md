# AUDITORIA SYNAPSE - 2026-01-31

## RESUMEN EJECUTIVO
- Total issues encontrados: 78
- P0 (bloquea dinero): 5
- P1 (riesgo alto): 12
- P2 (higiene): 61
- Tests: 504 pasando / 1 fallando
- Veredicto: **NO-GO para produccion**

Motivo principal: los modulos de seguridad financiera (capital_shield, killswitch, circuit_breaker) no persisten estado. Un restart del proceso pierde TODO el tracking de gasto y permite re-gastar el presupuesto completo. Ademas, el sistema de safety (killswitch, circuit breaker, gate) existe pero NO esta conectado al flujo de negocio real.

---

## P0 - CRITICOS (bloquean dinero real)

### [P0-001] CapitalShield v1 pierde estado en restart
- **Archivo:** ops/capital_shield.py
- **Linea:** ~77
- **Problema:** `_daily_state` es un dict en memoria. Al reiniciar el proceso, todo el tracking de gasto diario se pierde. El sistema permite re-gastar el presupuesto completo.
- **Riesgo:** Doble gasto del presupuesto diario completo ($30 default) en cada restart. En produccion con restarts frecuentes, gasto ilimitado.
- **Fix:** Persistir _daily_state en ledger_v2 o archivo JSON con fsync. Al iniciar, reconstruir estado desde ledger.

### [P0-002] Dos arquitecturas de capital_shield incompatibles coexisten
- **Archivo:** ops/capital_shield.py (v1) + ops/capital_shield_v2.py (v2)
- **Linea:** v1 usado en ops/catalog_pipeline.py:9, v2 usado en ops/autopilot_v2.py:7
- **Problema:** v1 enforcea limites internamente (en memoria), v2 delega a vault externo. Ambas corren en el mismo sistema con tracking independiente. El gasto autorizado por v1 no se refleja en v2 y viceversa.
- **Riesgo:** Un producto puede gastar $30 via v1 Y $30 via v2 en el mismo dia. Presupuesto efectivo = 2x lo configurado.
- **Fix:** Elegir UNA arquitectura (v2 con vault es superior). Migrar catalog_pipeline a v2. Deprecar v1.

### [P0-003] Operaciones de gasto sin idempotencia
- **Archivo:** ops/spend_gateway_v1.py
- **Linea:** ~94-109
- **Problema:** Decisiones de gasto se escriben al ledger sin idempotency key. Si hay retry por timeout de red, el mismo gasto se registra dos veces.
- **Riesgo:** Gasto duplicado en cada retry. Con retry automatico, multiplicador de gasto indefinido.
- **Fix:** Agregar idempotency_key obligatorio en spend_gateway. Usar infra/idempotency_manager.py que ya existe pero no esta integrado.

### [P0-004] LedgerV2 pierde hasta 10 eventos en crash
- **Archivo:** infra/ledger_v2.py
- **Linea:** ~95-97
- **Problema:** Batch buffer de 10 eventos. Solo se hace fsync cuando el buffer esta lleno. No hay flush por timeout. En crash del proceso, hasta 10 eventos financieros se pierden silenciosamente.
- **Riesgo:** Eventos de gasto perdidos = tracking incompleto = decisiones de presupuesto con datos faltantes. Pueden autorizar gasto ya realizado.
- **Fix:** Agregar flush por timeout (ej: cada 1s) ademas del flush por batch_size. Para eventos financieros, hacer flush inmediato (batch_size=1).

### [P0-005] Sistema de safety completamente desconectado
- **Archivo:** synapse/safety/ (killswitch.py, circuit.py, gate.py, safe_execute.py)
- **Linea:** Todo el directorio
- **Problema:** KillSwitch, CircuitBreaker, SafetyGate y safe_execute existen como codigo pero NO estan integrados en ningun flujo de negocio. Solo se usan en tests. El killswitch no puede matar nada. El circuit breaker no protege nada.
- **Riesgo:** En una cascada de fallos o gasto descontrolado, no hay mecanismo automatico de parada. Se requiere intervencion manual para detener el sistema.
- **Fix:** Integrar SafetyGate como middleware obligatorio antes de cada operacion de gasto. Conectar KillSwitch a un archivo de estado persistente que se lea antes de cada operacion.

---

## P1 - RIESGO ALTO

### [P1-001] KillSwitch sin persistencia
- **Archivo:** synapse/safety/killswitch.py
- **Linea:** ~27
- **Problema:** Estado almacenado solo en memoria. Comentario en codigo: "Storage-backed integration comes later; v1 gives deterministic control."
- **Riesgo:** Kill switch activado se pierde en restart. No hay forma de mantener una parada de emergencia entre restarts.
- **Fix:** Persistir estado en archivo JSON con fsync. Leer al iniciar.

### [P1-002] CircuitBreaker sin persistencia ni backoff exponencial
- **Archivo:** synapse/safety/circuit.py
- **Linea:** ~24-27
- **Problema:** Estado en memoria (failure_count, state). Backoff es fijo (1h cooldown), no exponencial. En HALF_OPEN, un solo exito cierra el circuito inmediatamente.
- **Riesgo:** Despues de restart, circuito en CLOSED permite avalancha de requests a servicio caido. Recovery demasiado agresivo en HALF_OPEN.
- **Fix:** Persistir estado. Implementar backoff exponencial. Requerir N exitos consecutivos para cerrar desde HALF_OPEN.

### [P1-003] KillSwitch timestamp evaluado en definicion, no en instanciacion
- **Archivo:** synapse/safety/killswitch.py
- **Linea:** ~21
- **Problema:** `activated_at: datetime = datetime.utcnow()` como default de dataclass. Se evalua UNA vez al importar el modulo, no al crear cada instancia.
- **Riesgo:** Todas las activaciones reportan el mismo timestamp. Audit trail inutil.
- **Fix:** Usar `field(default_factory=datetime.utcnow)` o mejor: `field(default_factory=lambda: datetime.now(timezone.utc))`.

### [P1-004] audit.py sin fsync
- **Archivo:** synapse/safety/audit.py
- **Linea:** ~74
- **Problema:** Hash-chain audit trail escribe sin fsync. El ultimo evento (y por tanto el enlace de la cadena) puede perderse en crash.
- **Riesgo:** Cadena de hash rota permanentemente despues de crash. Toda verificacion futura de integridad falla.
- **Fix:** Agregar os.fsync() despues de cada write.

### [P1-005] ledger_ndjson.py sin fsync
- **Archivo:** infra/ledger_ndjson.py
- **Linea:** ~67
- **Problema:** Solo hace f.flush() pero no os.fsync(). flush() mueve datos al buffer del OS, no garantiza escritura a disco.
- **Riesgo:** Perdida de eventos en crash del sistema operativo.
- **Fix:** Agregar os.fsync(f.fileno()) despues de flush.

### [P1-006] CapitalShield v1 usa date.today() sin timezone
- **Archivo:** ops/capital_shield.py
- **Linea:** ~99
- **Problema:** `date.today()` usa timezone local del servidor. En deployment distribuido, diferentes nodos pueden tener diferente "hoy".
- **Riesgo:** Inconsistencia de enforcement entre replicas. Un nodo puede resetear el presupuesto antes que otro.
- **Fix:** Usar `datetime.now(timezone.utc).date()` para consistencia.

### [P1-007] CapitalShield v1 campos learning/testing nunca se enforcean
- **Archivo:** ops/capital_shield.py
- **Linea:** ~20-21
- **Problema:** `daily_learning_cap: 15.0` y `daily_testing_cap: 15.0` estan configurados pero nunca se verifican en el codigo.
- **Riesgo:** Configuracion enganiosa. Operador cree que hay limites learning/testing pero no se aplican. Todo el gasto va contra el cap unico.
- **Fix:** Implementar enforcement o remover los campos para no confundir.

### [P1-008] Dependencias no declaradas: pandas y hypothesis
- **Archivo:** pyproject.toml
- **Linea:** dependencies section
- **Problema:** `pandas` se importa en el codebase pero no esta en pyproject.toml. `hypothesis` se usa en tests pero no esta en dev dependencies.
- **Riesgo:** `pip install` del proyecto falla en entorno limpio. CI/CD puede romper.
- **Fix:** Agregar `pandas` a dependencies y `hypothesis` a dev dependencies.

### [P1-009] RiskLimits.max_single_campaign_share nunca se usa
- **Archivo:** synapse/safety/limits.py
- **Linea:** ~11
- **Problema:** Campo definido pero evaluate_risk() nunca lo verifica. Codigo muerto que da falsa sensacion de seguridad.
- **Riesgo:** Concentracion de 100% de presupuesto en una sola campania es posible sin alerta.
- **Fix:** Implementar la verificacion en evaluate_risk() o eliminar el campo.

### [P1-010] Pipeline orchestrator modifica config compartida
- **Archivo:** synapse/discovery/pipeline_orchestrator.py
- **Linea:** ~145-150
- **Problema:** `setattr(cfg, k, v)` modifica instancia compartida de PipelineConfig. Llamadas concurrentes interfieren.
- **Riesgo:** Race condition en config. Una ejecucion puede heredar overrides de otra.
- **Fix:** Crear copia del config antes de aplicar overrides: `cfg = replace(cfg, **config_override)`.

### [P1-011] Vault exceptions silenciadas en CapitalShield v2
- **Archivo:** ops/capital_shield_v2.py
- **Linea:** ~99-104
- **Problema:** Si vault.request_spend() lanza excepcion (red, DB), se convierte silenciosamente a "insufficient_budget". Sin logging.
- **Riesgo:** Vault caido = todo gasto bloqueado sin diagnostico. No se puede distinguir "sin presupuesto" de "vault roto".
- **Fix:** Logear la excepcion. Retornar error diferenciado (vault_error vs insufficient_budget).

### [P1-012] Test falla: ledger timestamp contract
- **Archivo:** tests/p1/test_ledger_timestamp_contract.py
- **Linea:** ~19
- **Problema:** Test espera archivo `data/ledger/events.ndjson` que no existe. Usa path relativo sin fixture.
- **Riesgo:** Test P1 permanentemente roto. No valida contrato de timestamps en CI.
- **Fix:** Agregar pytest.mark.skipif cuando archivo no existe, o crear fixture que genere datos de test.

---

## P2 - HIGIENE

### [P2-001] Bare except en enrich_candidates_f1_v2.py (2 instancias)
- **Archivo:** ops/enrich_candidates_f1_v2.py
- **Linea:** ~104, ~133
- **Problema:** `except:` sin tipo especifico. Atrapa SystemExit, KeyboardInterrupt y todo.
- **Fix:** Cambiar a `except (ValueError, TypeError):` o `except Exception:` como minimo.

### [P2-002] Bare except en enrich_candidates_f1.py
- **Archivo:** ops/enrich_candidates_f1.py
- **Linea:** ~51
- **Problema:** `except: pass` en infer_prices(). Fallo silencioso total.
- **Fix:** Capturar excepcion especifica y logear.

### [P2-003] Bare except en catalog_scanner.py (2 instancias)
- **Archivo:** synapse/discovery/catalog_scanner.py
- **Linea:** ~164, ~200
- **Problema:** `except:` en _load_csv() y _match_keywords().
- **Fix:** Usar excepciones especificas.

### [P2-004] Bare except en niche_selector.py
- **Archivo:** synapse/discovery/niche_selector.py
- **Linea:** ~290
- **Problema:** `except:` en _load_selection().
- **Fix:** Usar excepcion especifica.

### [P2-005] Bare except en synapse/infra/ledger.py (4 instancias)
- **Archivo:** synapse/infra/ledger.py
- **Linea:** ~175, ~180, ~246, ~250
- **Problema:** Multiples `except:` en query() y count_events(). Errores de parseo JSON se tragan silenciosamente.
- **Fix:** Capturar json.JSONDecodeError explicita mente.

### [P2-006] Bare except en scripts (2 instancias)
- **Archivo:** scripts/run_product_finder_dropi_dump.py:16, scripts/normalize_dropi_pack_to_candidates_csv.py:38,47
- **Problema:** `except:` en funciones de conversion numerica.
- **Fix:** Usar `except (ValueError, TypeError):`.

### [P2-007] Bare except en wave_runner.py (2 instancias)
- **Archivo:** synapse/marketing_os/wave_runner.py
- **Linea:** ~181, ~243
- **Problema:** `except:` en _dedup_check() y _log_event().
- **Fix:** Usar excepciones especificas.

### [P2-008 a P2-034] datetime.utcnow() sin timezone (27 instancias)
- **Archivos afectados:**
  - ops/enrich_candidates_f1_v2.py:174,180,198
  - ops/enrich_candidates_f1.py:91
  - synapse/pulse/market_pulse.py:100
  - synapse/learning/learning_loop.py:47
  - tests/learning/learning_loop.py:47
  - ops/dropi_product_finder.py:52,55
  - synapse/safety/audit.py:48
  - synapse/safety/circuit.py:32,59
  - synapse/safety/killswitch.py:21
  - scripts/dropi_enrich_dump_with_catalog.py:54
  - scripts/dropi_catalog_ingest.py:52
  - ops/spend_gateway_v1.py:94
  - ops/systems/tribunal.py:77-79
  - ops/systems/hypothesis_tracker.py:127
  - infra/bitacora_auto.py:93,95
  - buyer/buyer_block.py:91,96,109,147
  - synapse/meta_publish_execute.py:458,496,737
  - synapse/marketing_os/campaign_blueprint.py:179,233
  - ops/dropi_dump_ingest.py:26,247
  - ops/integrate_f1_zip.py:8
- **Problema:** `datetime.utcnow()` esta deprecated desde Python 3.12. No genera timezone-aware datetimes.
- **Fix:** Reemplazar por `datetime.now(timezone.utc)` en todo el codebase.

### [P2-035] Writes sin error handling (6 instancias)
- **Archivos:**
  - ops/enrich_candidates_f1_v2.py:193,208
  - synapse/marketing_os/wave_runner.py:201,230
  - synapse/discovery/niche_selector.py:295-298
  - ops/spend_gateway_v1.py:89-90
- **Problema:** Escrituras a disco sin try/except ni rollback.
- **Fix:** Wrap en try/except, escribir a .tmp y renombrar atomicamente.

### [P2-036 a P2-050] Thresholds hardcodeados (15+ instancias)
- **Archivos principales:**
  - ops/enrich_candidates_f1_v2.py:38-42,59-67,72,76,88-92 (pesos de scoring, confidence)
  - synapse/discovery/catalog_scanner.py:93-97 (filtros de scan)
  - synapse/meta_publish_execute.py:115,151 (timeouts HTTP)
  - _meta_me_check.py:7, synapse/meta_auth_check.py:20 (timeouts)
- **Problema:** Magic numbers dispersos en el codigo, no centralizados en config.
- **Fix:** Mover a config/default.yml o dataclass de configuracion.

### [P2-051] Versions no pinneadas exactamente
- **Archivo:** pyproject.toml
- **Problema:** Todas las dependencias usan `>=` sin upper bound. No hay lockfile.
- **Fix:** Generar requirements.lock con versiones exactas para builds reproducibles.

---

## MODULOS CRITICOS - ESTADO ACTUAL

### killswitch.py
- **Archivo:** synapse/safety/killswitch.py (55 lineas)
- **Persiste estado:** NO. 100% en memoria.
- **Funciona recovery:** NO. No hay recovery. Restart = estado limpio.
- **Integrado en produccion:** NO. Solo se usa en tests.
- **Veredicto:** Decorativo. No protege nada.

### circuit_breaker.py (circuit.py)
- **Archivo:** synapse/safety/circuit.py (59 lineas)
- **Persiste:** NO. En memoria.
- **Backoff correcto:** NO. Cooldown fijo de 1h, no exponencial. HALF_OPEN cierra con 1 exito.
- **Integrado:** NO. Solo tests.
- **Veredicto:** Implementacion correcta como pattern, pero no esta conectado a ningun servicio.

### ledger.py
- **Archivos:** core/ledger.py (v1), infra/ledger_v2.py (v2), infra/ledger_ndjson.py, synapse/infra/ledger.py
- **Append-only:** SI en todas las versiones.
- **Integridad:** Solo v2 tiene checksums SHA256. v1 y ndjson no.
- **fsync:** v1 SI, v2 SI (en flush), ndjson NO.
- **Veredicto:** v2 es el unico apto para produccion pero tiene ventana de perdida de datos (buffer de 10).

### capital_shield.py
- **Archivos:** ops/capital_shield.py (v1), ops/capital_shield_v2.py (v2)
- **Limites funcionan:** v1 SI enforcea hard cap pero pierde estado en restart. v2 delega a vault (correcto).
- **Problema critico:** Ambos coexisten con tracking independiente.
- **Veredicto:** Migrar todo a v2, deprecar v1.

### synapse_core.py (orquestacion)
- **No existe como archivo unico.** La orquestacion esta distribuida en:
  - synapse/runner.py - runner principal
  - synapse/infra/run.py - run infrastructure
  - synapse/cli/main.py - entry point CLI
  - synapse/discovery/pipeline_orchestrator.py - pipeline discovery
- **Orquestacion correcta:** Parcialmente. pipeline_orchestrator tiene buena estructura de 3 fases pero no persiste estado intermedio y modifica config compartida (race condition).

---

## DUPLICADOS V1/V2

| Modulo v1 | Modulo v2/v3 | Cual se usa realmente | Imports mezclados |
|-----------|-------------|----------------------|-------------------|
| ops/capital_shield.py | ops/capital_shield_v2.py | AMBOS (v1 en catalog_pipeline, v2 en autopilot_v2) | SI - riesgo de doble tracking |
| core/ledger.py | infra/ledger_v2.py | v1 en scripts, v2 en ops/build_candidates_f1_pack | NO - pero deberia migrar |
| core/ledger_analyzer_v1.py | (no hay v2) | v1 en tests | N/A |
| ops/spend_gateway_v1.py | (no hay v2) | v1 activo | N/A |
| ops/spend_policy_v1.py | (no hay v2) | v1 activo | N/A |
| ops/enrich_candidates_f1.py | ops/enrich_candidates_f1_v2.py | Ambos existen | Independientes |
| ops/exit_criteria.py | ops/exit_criteria_v2.py | Ambos existen | Independientes |
| synapse/quality_gate.py | synapse/quality_gate_v2.py | Ambos existen | Independientes |
| scripts/build_canonical_from_dropi.py | scripts/build_canonical_from_dropi_v2.py, v3.py | v3 es el activo | v1/v2 son legacy |
| vault/v1.py | vault/vault.py | Coexisten | A verificar |
| vault/cashflow_v1.py | (no hay v2) | v1 activo | N/A |
| infra/ledger_ndjson.py | synapse/ledger_ndjson.py | Duplicados | Dos copias del mismo concepto |

**Total modulos duplicados:** 12 pares v1/v2+ identificados.

---

## TESTS

### Tests pasando (504):
Todos los tests de los siguientes directorios pasan:
- tests/p0/ (11 tests) - ledger, vault, spend, cashflow, evidence
- tests/p1/ (2 de 3) - ledger analyzer, cashflow state
- tests/safety/ (5 tests) - safe_execute, safety core, gate, vault gate
- tests/infra/ (23 tests) - CLI, config, diagnostics, dry_run, logging
- tests/marketing_os/ (15 tests) - campaign, creative, experiment, stoploss, wave
- tests/discovery/ (4 tests) - catalog, niche, pipeline, ranker
- tests/integration/ (3 tests) - http_client, secrets, webhooks
- tests/ads/ (1 test) - ads_intelligence
- tests/shopify/ (4 tests) - import, export, enrichment
- tests/meta/ (2 tests) - payloads, control tower
- tests/webhooks/ (1 test) - webhook router
- tests/reporting/ (1 test) - audit viewer
- tests/pulse/ (1 test) - market pulse
- tests/legacy/ (1 test) - legacy cleanup
- tests/learning/ (1 test) - learning loop
- tests/property/ (3 tests) - exit criteria, scoring, vault
- tests/dropi/ (3 tests) - canonical, quality gate, autopick
- buyer/tests/ (4 tests) - buyer block, catalog, schemas, scoring
- ops/tests/ (10 tests) - autopilot, capital shield, exit criteria, feedback, hypothesis, overfitting, tribunal
- infra/tests/ (5 tests) - blindaje, health, idempotency, result monad, vault properties
- intelligence/tests/ (3 tests) - early warning, factors, forecasting
- docs/tests/ (3 tests) - infra, interrogation, quality filter

### Tests fallando (1):
| Test | Archivo | Razon |
|------|---------|-------|
| test_ledger_events_have_ts_utc_parseable | tests/p1/test_ledger_timestamp_contract.py:19 | Espera archivo `data/ledger/events.ndjson` que no existe. Test de contrato sobre artefacto de runtime, no sobre codigo. Necesita skipif o fixture. |

### Cobertura aproximada de modulos criticos:
| Modulo | Tests dedicados | Cobertura estimada |
|--------|----------------|-------------------|
| killswitch.py | test_safety_core_v1.py (parcial) | ~60% |
| circuit.py | test_safety_core_v1.py (parcial) | ~60% |
| core/ledger.py | test_ledger_v1.py | ~80% |
| infra/ledger_v2.py | (ninguno dedicado) | ~20% (indirecto) |
| capital_shield.py | test_capital_shield.py | ~75% |
| capital_shield_v2.py | test_capital_shield_v2.py | ~75% |
| spend_gateway_v1.py | test_spend_gateway_v1.py | ~70% |
| safety/gate.py | test_safety_gate_*.py (2 tests) | ~70% |
| audit.py | test_safety_core_v1.py (parcial) | ~50% |

---

## PROBLEMAS ESPECIFICOS

### 1. Bare except (15 instancias)
| # | Archivo | Linea |
|---|---------|-------|
| 1 | ops/enrich_candidates_f1_v2.py | ~104 |
| 2 | ops/enrich_candidates_f1_v2.py | ~133 |
| 3 | ops/enrich_candidates_f1.py | ~51 |
| 4 | synapse/discovery/catalog_scanner.py | ~164 |
| 5 | synapse/discovery/catalog_scanner.py | ~200 |
| 6 | synapse/discovery/niche_selector.py | ~290 |
| 7 | synapse/infra/ledger.py | ~175 |
| 8 | synapse/infra/ledger.py | ~180 |
| 9 | synapse/infra/ledger.py | ~246 |
| 10 | synapse/infra/ledger.py | ~250 |
| 11 | scripts/run_product_finder_dropi_dump.py | ~16 |
| 12 | scripts/normalize_dropi_pack_to_candidates_csv.py | ~38 |
| 13 | scripts/normalize_dropi_pack_to_candidates_csv.py | ~47 |
| 14 | synapse/marketing_os/wave_runner.py | ~181 |
| 15 | synapse/marketing_os/wave_runner.py | ~243 |

### 2. datetime.utcnow() sin timezone (27+ instancias)
Ver seccion P2-008 a P2-034 arriba para lista completa.

### 3. Operaciones de dinero sin idempotencia
| Archivo | Detalle |
|---------|---------|
| ops/spend_gateway_v1.py:94-109 | Gasto a ledger sin idempotency key |
| vault/cashflow_v1.py | Autorizacion de gasto sin idempotency check |
| synapse/meta_publish_execute.py:115-152 | Interacciones Meta API sin idempotency context |

### 4. Writes sin retry/rollback
| Archivo | Linea |
|---------|-------|
| ops/enrich_candidates_f1_v2.py | ~193, ~208 |
| synapse/marketing_os/wave_runner.py | ~201, ~230 |
| synapse/discovery/niche_selector.py | ~295-298 |
| ops/spend_gateway_v1.py | ~89-90 |

### 5. Logs que exponen secrets/keys
| Archivo | Riesgo |
|---------|--------|
| ops/spend_gateway_v1.py:88 | json.dumps(row) puede incluir payload sensible |
| synapse/meta_publish_execute.py | Operaciones con Meta API token pueden leakear en logs de error |

### 6. Imports circulares
No se detectaron imports circulares directos confirmados. Riesgo estructural bajo en vault/ y synapse/ por import patterns complejos, pero no hay evidencia de fallo en runtime.

### 7. Thresholds/limites hardcodeados sin config
| Archivo | Valores |
|---------|---------|
| ops/enrich_candidates_f1_v2.py:38-92 | Pesos de scoring: 0.28, 0.22, 0.20, etc. Thresholds: 0.75, 0.65, 0.68, 0.60 |
| synapse/discovery/catalog_scanner.py:93-97 | Filtros: 40.0, 100.0, 2000.0, 3.5, 100 |
| synapse/meta_publish_execute.py:115,151 | Timeouts HTTP: 60s, 120s |
| synapse/safety/circuit.py | failure_threshold=3, cooldown=3600 |
| synapse/safety/limits.py | daily_loss_limit=0.05, spend_rate_anomaly_mult=3.0 |

### 8. TODOs o FIXMEs abandonados
Solo 1 encontrado:
| Archivo | Contenido |
|---------|-----------|
| synapse/safety/killswitch.py:27 | `# Storage-backed integration comes later; v1 gives deterministic control.` |

Nota: el codebase esta limpio de TODOs/FIXMEs, lo cual puede significar que se resolvieron o que nunca se documentaron deudas tecnicas.

---

## ARCHIVOS MODIFICADOS RECIENTEMENTE

| # | Archivo | Ultimo commit |
|---|---------|---------------|
| 1 | scripts/canonical_quality_gate.py | 9c6d555 - CLI compat: quality gate --mode/--soft-fail |
| 2 | scripts/image_backlog_from_canon_report.py | 9c6d555 - CLI compat |
| 3 | scripts/build_canonical_from_dropi_v3.py | 7ce5f57 - accept --mode + placeholder-aware metrics |
| 4 | scripts/dropi_catalog_ingest.py | 3a340a3 - Update dropi ingest + batch release |
| 5 | scripts/dropi_enrich_dump_with_catalog.py | 3a340a3 - Update dropi ingest |
| 6 | scripts/release_wavekits_batch.ps1 | 8d27459 - Batch release |
| 7 | scripts/run_release_offline.ps1 | 0ef366b - Add demo/prod mode |
| 8 | scripts/shopify_contract_gate.py | 0ef366b - Add demo/prod mode |

Observacion: todos los cambios recientes estan concentrados en scripts/. Los modulos criticos de safety y capital no se han tocado recientemente.

---

## DEPENDENCIAS

### pyproject.toml (no hay requirements.txt)
```
dependencies:
  pydantic>=2.0.0        - USADO - OK
  pyyaml>=6.0            - USADO - OK
  python-dotenv>=1.0.0   - USADO - OK
  click>=8.0.0           - USADO - OK

dev:
  pytest>=7.0.0          - USADO - OK
  pytest-mock>=3.10.0    - USADO - OK
```

### Problemas:
| Issue | Detalle |
|-------|---------|
| **pandas no declarado** | Se importa en el codebase pero no esta en pyproject.toml. Install limpio falla. |
| **hypothesis no declarado** | Se usa en tests (tests/property/) pero no esta en dev dependencies. |
| **Sin lockfile** | No hay requirements.lock ni pip freeze. Builds no reproducibles. |
| **Solo >= pins** | Sin upper bound. Vulnerable a breaking changes de dependencias. |
| **Sin dependencias no usadas** | Todas las declaradas se importan. Limpio. |

---

## RECOMENDACION DE SIGUIENTE PASO

Los 3 fixes mas urgentes, en orden:

### 1. Unificar CapitalShield en v2 + persistir estado (P0-001 + P0-002)
**Que hacer:** Migrar catalog_pipeline.py de CapitalShield v1 a v2. Conectar v2 con vault persistente. Eliminar v1. Esto cierra los dos P0 mas criticos de un golpe: ya no hay doble tracking ni estado volatil.

### 2. Agregar idempotencia a spend_gateway (P0-003)
**Que hacer:** Integrar infra/idempotency_manager.py (que ya existe) en spend_gateway_v1.py. Cada operacion de gasto debe tener un idempotency_key obligatorio. Rechazar duplicados. Esto previene doble-gasto en retries.

### 3. Flush inmediato en LedgerV2 para eventos financieros (P0-004)
**Que hacer:** Agregar parametro `critical=True` al metodo append() de LedgerV2. Cuando critical=True, hacer flush+fsync inmediato ignorando batch_size. Usar critical=True para todos los eventos de gasto/presupuesto. Agregar flush por timeout (1s) para eventos normales.

---

*Auditoria generada el 2026-01-31. Auditor: Claude Opus 4.5.*
*504 tests pasando, 1 fallando. 78 issues identificados. Veredicto: NO-GO.*
