from __future__ import annotations

from hypothesis import HealthCheck, settings

# Hypothesis puede volverse "flaky" por velocidad en Windows/OneDrive/CPU load.
# Esto NO es un bug funcional: es un healthcheck de performance.
# Lo suprimimos para que la suite sea estable.
settings.register_profile(
    "trendify_stable",
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,  # evita timeouts por variación de rendimiento
)

settings.load_profile("trendify_stable")