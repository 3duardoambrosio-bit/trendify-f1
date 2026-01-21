from __future__ import annotations

# Auto-load .env.local when running from repo root.
# Safe: no imprime secretos, no truena si falta el archivo.

try:
    from synapse.infra.envfile import load_env_file
    load_env_file(".env.local", override=False)
except Exception:
    pass
