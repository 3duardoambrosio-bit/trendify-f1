# synapse/pulse/__init__.py
"""
Pulse package.

No importamos market_pulse aquí para evitar warnings estilo runpy en ejecuciones -m.
"""

__all__ = [
    "PulseSignal",
    "MarketPulseMemo",
    "MarketPulseRunner",
    "PulseValidationError",
    "validate_signal",
]
