# A8-R43D High Risk Debt Marker Registry

## Summary

- MODE=LOCAL_ONLY_CODE_HARDENING
- BASE_HEAD=1a062d0
- HIGH_RISK_COUNT=35
- UNMANAGED_HIGH_RISK_COUNT=0
- DECISION=register before editing runtime behavior

## Rule

High-risk debt markers are not allowed to stay invisible. Each current marker is registered with path, line, marker, hash, decision, and action rule.

## Entries

- synapse/forecast/model.py:72 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — # return float to satisfy legacy tests: abs(x - 2.52)
- synapse/forecast/model.py:116 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — # store float-facing values (legacy-friendly), computed via Decimal -> __float__ (gate-safe)
- synapse/infra/schemas.py:38 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — # Alias legacy
- synapse/integration/__init__.py:1 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — """Legacy compatibility exports for synapse.integration."""
- synapse/integration/http_client.py:1 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — """Legacy compatibility wrapper for synapse.integration.http_client.
- synapse/integration/http_client.py:6 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — - Singular path preserves historical defaults for legacy callers.
- synapse/integration/http_client.py:23 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — """Legacy wrapper preserving singular-path defaults.
- synapse/legacy/__init__.py:1 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — # synapse/legacy/__init__.py
- synapse/legacy/__init__.py:3 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — Legacy package.
- synapse/legacy/legacy_cleanup.py:1 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — # synapse/legacy/legacy_cleanup.py
- synapse/legacy/legacy_cleanup.py:3 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — Legacy Cleanup — OLEADA 14
- synapse/legacy/legacy_cleanup.py:7 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — - NO borramos legacy (todavía). Primero: inventario + compat mapping + riesgos.
- synapse/legacy/legacy_cleanup.py:8 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — - Detecta archivos legacy conocidos, verifica import, calcula hash por archivo.
- synapse/legacy/legacy_cleanup.py:10 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — - data/legacy/legacy_report_latest.json
- synapse/legacy/legacy_cleanup.py:11 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — - data/legacy/legacy_report_latest.md
- synapse/legacy/legacy_cleanup.py:12 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — - data/legacy/legacy_state.json  (idempotencia)
- synapse/legacy/legacy_cleanup.py:15 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — - python -m synapse.legacy.legacy_cleanup --dry-run
- synapse/legacy/legacy_cleanup.py:16 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — - python -m synapse.legacy.legacy_cleanup
- synapse/legacy/legacy_cleanup.py:17 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — - python -m synapse.legacy.legacy_cleanup --force
- synapse/legacy/legacy_cleanup.py:82 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — # Config (targets legacy conocidos)
- synapse/legacy/legacy_cleanup.py:89 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — role="Legacy scoring",
- synapse/legacy/legacy_cleanup.py:96 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — role="Legacy forecasting",
- synapse/legacy/legacy_cleanup.py:103 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — role="Legacy product evaluator",
- synapse/legacy/legacy_cleanup.py:110 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — role="Legacy quality gate v1",
- synapse/legacy/legacy_cleanup.py:242 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — out_dir = self.repo_root / "data" / "legacy"
- synapse/legacy/legacy_cleanup.py:292 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — recommendations.append("⚠️ Hay legacy que existe pero NO importa — riesgo de runtime. Arreglar imports o aislar.")
- synapse/legacy/legacy_cleanup.py:294 [DEPRECATED] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — recommendations.append("🧹 V1 puede mantenerse como compat, pero marcar como deprecated y evitar nuevos usos.")
- synapse/legacy/legacy_cleanup.py:333 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — lines.append("# Legacy Cleanup Report (latest)")
- synapse/legacy/legacy_cleanup.py:366 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — lines.append("- Mantener legacy como compat hasta que el repo esté 100% limpio sin romper P0.")
- synapse/meta/publisher_adapter.py:157 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — # Mantiene compat legacy: OFF por default.
- synapse/meta/publisher_contracts.py:99 [DEPRECATED] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — """Emit a best-effort alert for deprecated Meta response drift.
- synapse/meta/safe_client.py:1 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — """Meta Safe Client: canonical idempotency + ndjson ledger with legacy-compatible constructor."""
- synapse/phase1_ready.py:73 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — # contract mínimo: no vacío, JSON parseable, y debe existir ts_utc (o ts legacy) en eventos recientes
- synapse/shopify/creative_kit_builder.py:67 [LEGACY] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — # Last resort (legacy)
- synapse/webhooks/__init__.py:1 [DEPRECATED] JUSTIFIED_COMPATIBILITY_OR_TRANSITIONAL_RUNTIME_MARKER — """Deprecated package. Use synapse.integrations.shopify_webhook.*"""
