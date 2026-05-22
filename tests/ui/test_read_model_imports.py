"""Import smoke test for the read-only Streamlit model."""

from synapse.ui import read_model


def test_read_model_imports_without_error() -> None:
    assert read_model.REQUIRED_FILES == (
        "scenario.json",
        "decision.json",
        "safety_posture.json",
        "creative_pack.json",
        "ledger_sandbox.ndjson",
    )


def test_read_model_npc_template_flag_detects_known_patterns() -> None:
    assert read_model.matches_npc_template("Dile adiós al desorden operativo")
    assert not read_model.matches_npc_template("Análisis operativo con evidencia visible")
