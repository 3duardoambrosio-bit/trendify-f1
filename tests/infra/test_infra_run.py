# tests/infra/test_infra_run.py
import importlib

def test_infra_run_module_imports():
    m = importlib.import_module("synapse.infra.run")
    assert hasattr(m, "main")
