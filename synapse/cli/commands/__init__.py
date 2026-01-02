"""
synapse.cli.commands

Command modules must stay import-light.
No heavy synapse subsystem imports at module import time.
"""
__all__ = [
    "doctor_cmd",
    "wave_cmd",
    "learning_cmd",
    "pulse_cmd",
    "snapshot_cmd",
    "triage_cmd",
    "debug_crash_cmd",
]
