# tests/infra/test_lazy_exports.py
import sys

def test_lazy_schema_exports_do_not_import_doctor():
    sys.modules.pop("synapse.infra.doctor", None)

    # Debe existir y NO disparar import de doctor
    from synapse.infra import SchemaVersionError, validate  # noqa: F401

    assert "synapse.infra.doctor" not in sys.modules
