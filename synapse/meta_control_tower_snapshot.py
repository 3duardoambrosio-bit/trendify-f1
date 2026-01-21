# synapse/meta_control_tower_snapshot.py
"""
Thin wrapper para permitir:
  python -m synapse.meta_control_tower_snapshot --repo ... --out ...

Internamente ejecuta:
  synapse.meta.meta_control_tower_snapshot
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("synapse.meta.meta_control_tower_snapshot", run_name="__main__")
