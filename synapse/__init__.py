import logging
logger = logging.getLogger(__name__)
# synapse/__init__.py
"""
SYNAPSE - Sistema de automatización para TrendifyHub.

Módulos:
- marketing_os: Sistema de marketing automatizado
- core: Funcionalidad core (quality gate, exit criteria)
- vault: Control de capital
- infra: Infraestructura (ledger, etc)
"""

__version__ = "1.0.0"

# --- SYNAPSE_AUTOENV_HOOK_2026-01-15_V1 ---
# Auto-load .env.local when importing synapse (covers python -m synapse.*).
# Safe: no prints, no crash, no override.
try:
    from synapse.infra.bootstrap import bootstrap_env as _bootstrap_env
    _bootstrap_env()
except Exception as e:
    logger.debug("suppressed exception", exc_info=True)

# --- /SYNAPSE_AUTOENV_HOOK_2026-01-15_V1 ---
