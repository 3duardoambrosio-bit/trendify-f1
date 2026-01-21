# tests/infra/test_init_hygiene.py
import sys

def test_import_infra_does_not_preload_doctor_and_does_not_error():
    sys.modules.pop("synapse.infra.doctor", None)
    import synapse.infra  # noqa: F401

    # La regla clave:
    assert "synapse.infra.doctor" not in sys.modules

    # Debe exponer Ledger sí o sí
    from synapse.infra import Ledger  # noqa: F401
