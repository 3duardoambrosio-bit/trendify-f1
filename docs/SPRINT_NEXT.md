# SPRINT NEXT - SYNAPSE / TrendifyHub

> Fecha: 2026-02-16
> Baseline: commit 6545ba9 | 636/636 tests | doctor GREEN | snapshot 5/5
> Objetivo: cerrar los 3 P0 de mayor riesgo financiero antes de habilitar feature flags en staging.

---

## Entregable 1 (S10): Spend Pipeline idempotente

### Problema
`ops/spend_gateway_v1.py` registra decisiones de gasto sin idempotency key (P0-003).
Un retry de red duplica el gasto en el ledger. `synapse/infra/idempotency_store.py` ya existe
pero NO est integrado en el gateway de gasto.

### Archivos a tocar
| Archivo | Cambio |
|---|---|
| `ops/spend_gateway_v1.py` | Agregar parmetro `idempotency_key: str` obligatorio en `authorize_spend()`. Rechazar si key ya existe en store. |
| `synapse/infra/idempotency_store.py` | Agregar mtodo `exists(key) -> bool` si no lo tiene. |
| `tests/p0/test_spend_gateway_v1.py` | Nuevos tests: retry con misma key  mismo resultado, key distinta  gasto independiente. |
| `tests/p0/test_spend_idempotency_contract.py` | (nuevo) Test de contrato: 100 calls con misma key = exactamente 1 registro en ledger. |

### Criterios de aceptacin numricos
| # | Criterio | Comando de verificacin |
|---|---|---|
| 1 | 0 lneas dirty | `git status --porcelain \| Measure-Object -Line \| Select -Expand Lines` debe ser `0` |
| 2 | pytest exit 0 | `python -m pytest -q; echo "EXIT=$LASTEXITCODE"` debe mostrar `EXIT=0` |
| 3 | Test especfico pasa | `python -m pytest tests/p0/test_spend_idempotency_contract.py -v; echo "EXIT=$LASTEXITCODE"` debe mostrar `EXIT=0` |
| 4 | Cobertura spend_gateway  90% | `python -m pytest --cov=ops.spend_gateway_v1 tests/p0/test_spend_gateway_v1.py -q \| Select-String "TOTAL"` debe mostrar  90% |
| 5 | Snapshot 5/5 GREEN | `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\evidence_snapshot.ps1` |

---

## Entregable 2 (S11): Safety Gate integrado en flujo de gasto real

### Problema
`synapse/safety/` (killswitch, circuit breaker, gate) existe pero NO est conectado
al flujo de negocio (P0-005). El Meta Safe Client (`synapse/meta/safe_client.py`) usa
un `_StubVault` y un `_check_safety_middleware` que falla silenciosamente si el mdulo
no est disponible. KillSwitch no persiste estado (P1-001).

### Archivos a tocar
| Archivo | Cambio |
|---|---|
| `synapse/safety/killswitch.py` | Persistir estado en archivo JSON (`data/safety/killswitch_state.json`) con fsync. Leer al instanciar. Corregir `activated_at` default (P1-003). |
| `synapse/safety/gate.py` | Exponer `pre_spend_check(amount, correlation_id) -> SafetyGateDecision` que orqueste killswitch + circuit breaker + risk limits en una sola llamada. |
| `synapse/meta/safe_client.py` | Reemplazar `_check_safety_middleware` stub por llamada real a `gate.pre_spend_check()`. Fallar si gate rechaza (no passthrough). |
| `tests/safety/test_killswitch_persistence.py` | (nuevo) Test: activar killswitch  reiniciar instancia  estado sigue activo. |
| `tests/safety/test_gate_spend_integration.py` | (nuevo) Test: gate rechaza  Meta Safe Client NO enva campaa. Gate permite  campaa se enva. |
| `tests/safety/test_safety_gate_contract_resilience.py` | Agregar caso: killswitch activo  gate SIEMPRE rechaza sin importar risk snapshot. |

### Criterios de aceptacin numricos
| # | Criterio | Comando de verificacin |
|---|---|---|
| 1 | 0 lneas dirty | `git status --porcelain \| Measure-Object -Line \| Select -Expand Lines` debe ser `0` |
| 2 | pytest exit 0 | `python -m pytest -q; echo "EXIT=$LASTEXITCODE"` debe mostrar `EXIT=0` |
| 3 | Tests killswitch persistence pasan | `python -m pytest tests/safety/test_killswitch_persistence.py -v; echo "EXIT=$LASTEXITCODE"` debe mostrar `EXIT=0` |
| 4 | Tests gate-spend integration pasan | `python -m pytest tests/safety/test_gate_spend_integration.py -v; echo "EXIT=$LASTEXITCODE"` debe mostrar `EXIT=0` |
| 5 | 0 passthrough/stub en safe_client.py | `Select-String -Path synapse\meta\safe_client.py -Pattern "passthrough\|StubVault" \| Measure-Object -Line \| Select -Expand Lines` debe ser `0` |
| 6 | Snapshot 5/5 GREEN | `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\evidence_snapshot.ps1` |

---

## Entregable 3 (S12): CapitalShield v1  v2 migracin completa

### Problema
Coexisten dos arquitecturas de capital shield (P0-002): v1 (en memoria, sin persistencia)
y v2 (vault-backed). Ambas corren con tracking independiente, duplicando efectivamente
el presupuesto a 2x. `ops/catalog_pipeline.py` todava importa v1.

### Archivos a tocar
| Archivo | Cambio |
|---|---|
| `ops/catalog_pipeline.py` | Reemplazar `from ops.capital_shield import ...` por `from ops.capital_shield_v2 import CapitalShieldV2`. Adaptar llamadas. |
| `ops/capital_shield.py` | Agregar `DeprecationWarning` en `__init__` de la clase v1. Documentar en docstring que v2 es el reemplazo. |
| `ops/capital_shield_v2.py` | Agregar mtodo `daily_remaining() -> Decimal` para que cockpit pueda mostrar presupuesto restante. |
| `synapse/cli/commands/status_cmd.py` | Mostrar `daily_remaining` de v2 en output de `cockpit status`. |
| `tests/p0/test_capital_shield_v2_migration.py` | (nuevo) Test: catalog_pipeline usa v2 exclusivamente. v1 lanza DeprecationWarning. Single-vault tracking: gasto va v1 + gasto va v2 = total correcto en vault. |
| `tests/infra/test_cockpit_status_budget.py` | (nuevo) Test: `cockpit status` incluye campo `daily_remaining` con valor numrico. |

### Criterios de aceptacin numricos
| # | Criterio | Comando de verificacin |
|---|---|---|
| 1 | 0 lneas dirty | `git status --porcelain \| Measure-Object -Line \| Select -Expand Lines` debe ser `0` |
| 2 | pytest exit 0 | `python -m pytest -q; echo "EXIT=$LASTEXITCODE"` debe mostrar `EXIT=0` |
| 3 | 0 imports de v1 en pipeline | `Select-String -Path ops\catalog_pipeline.py -Pattern "from ops.capital_shield import" \| Measure-Object -Line \| Select -Expand Lines` debe ser `0` |
| 4 | v1 emite DeprecationWarning | `python -W all -c "from ops.capital_shield import CapitalShield" 2>&1 \| Select-String "DeprecationWarning" \| Measure-Object -Line \| Select -Expand Lines` debe ser `1` |
| 5 | Test migracin pasa | `python -m pytest tests/p0/test_capital_shield_v2_migration.py -v; echo "EXIT=$LASTEXITCODE"` debe mostrar `EXIT=0` |
| 6 | Snapshot 5/5 GREEN | `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\evidence_snapshot.ps1` |

---

## Orden de ejecucin recomendado

```
S10 (idempotencia) --> S11 (safety gate) --> S12 (v1->v2 migracin)
```

S10 es prerequisito de S11 porque el safety gate debe proteger un spend gateway
que ya sea idempotente. S12 puede hacerse en paralelo con S11 pero se recomienda
despus para reducir conflictos de merge.

## Definicin de DONE del sprint

```powershell
# Todos estos deben ser TRUE simultneamente:
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\evidence_snapshot.ps1
# => dirty_lines=0, pytest_exit=0, doctor_exit=0, doctor_overall=GREEN, canonical_rows>=1

# + los tests especficos de cada entregable pasan individualmente (ver arriba)
# + 0 imports de capital_shield v1 en catalog_pipeline
# + 0 stubs/passthrough en safe_client.py
```
