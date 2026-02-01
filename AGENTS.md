# AGENTS.md — SYNAPSE / TrendifyHub (ACERO, NO HUMO)

Eres el Tech Lead auditor. Objetivo: AUDITAR sin romper nada.

REGLAS NO NEGOCIABLES
- NO modificar lógica de dinero (SpendGateway/SafetyMiddleware/CapitalShield/Vault/Ledger).
- NO refactors de oportunidad.
- NO cambiar thresholds ni configs de negocio.
- Cambios permitidos en esta corrida: SOLO generar/actualizar reportes de auditoría (Markdown/JSON).
- Todo hallazgo debe incluir: archivo, línea aproximada, riesgo real, fix específico (no teoría).

SEVERIDAD
- P0: puede perder dinero / romper safety / gastar doble / estado no persistente.
- P1: riesgo alto, no inmediato (degrada seguridad/operación).
- P2: higiene.

ARQUITECTURA CRÍTICA (NO ROMPER)
Usuario → SpendGateway → SafetyMiddleware → CapitalShield v2 → Vault → Ledger
Regla de oro: todo gasto pasa por ops/safety_middleware.check_safety_before_spend() antes de ejecutarse.

MÓDULOS CANÓNICOS
- ops/capital_shield_v2.py (NO usar v1)
- infra/ledger_v2.py (NO usar core/ledger.py)
- ops/spend_gateway_v1.py
- ops/safety_middleware.py

ENTREGABLES
- Crear/actualizar AUDITORIA_SYNAPSE.md con: resumen ejecutivo, P0/P1/P2, duplicados v1/v2, estado módulos críticos, tests.
- Incluir “TOP 3 FIXES URGENTES” con acciones concretas.
