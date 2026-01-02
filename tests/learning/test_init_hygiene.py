# tests/learning/test_init_hygiene.py
import sys

def test_import_learning_does_not_preload_learning_loop():
    sys.modules.pop("synapse.learning.learning_loop", None)
    import synapse.learning  # noqa: F401
    assert "synapse.learning.learning_loop" not in sys.modules
