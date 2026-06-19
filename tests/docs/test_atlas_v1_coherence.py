from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
ATLAS = REPO / "docs/phase1/A8_R85_ATLAS_V1.md"

EXPECTED_BASE_HEAD = "8529d58dd69337df1dc27c6f72fba1ef5fdf094d"

REQUIRED_STRINGS = [
    "Status: ATLAS_V1",
    "Base HEAD: 8529d58dd69337df1dc27c6f72fba1ef5fdf094d",
    "Release 1 is closed with notes",
    "operator-in-control",
    "no live writes",
    "no automatic spend",
    "no automatic fulfillment",
    "Marketing Expert Foundation is not certified",
    "A8-R86 Marketing Expert Foundation",
    "Atlas must not",
    "Release 2",
    "Release 3",
]

REQUIRED_REAL_PATHS = [
    "docs/phase1/A8_R84_RELEASE_1_CLOSE_RECORD.md",
    "docs/phase1/A8_R84_RELEASE_BOUNDARY.md",
    "docs/phase1/A8_R83_METHOD_FOUNDATION_DECISION.md",
    "synapse/product_evaluator.py",
    "ops/catalog_pipeline.py",
    "synapse/financial/evaluation.py",
    "synapse/financial/adapters.py",
    "synapse/integrations/dropi/order_forwarder.py",
    "tests/ops/test_a8_r82_money_path_unification.py",
    "tests/integration/test_a8_r70_smoke.py",
    "tests/integrations/test_dropi_order_forwarder.py",
    "tests/integrations/test_write_path_network_guard.py",
]


def test_atlas_exists_and_is_bounded():
    assert ATLAS.exists(), "Atlas document missing"
    text = ATLAS.read_text(encoding="utf-8")
    line_count = len(text.splitlines())

    assert line_count <= 220, f"Atlas is too large for V1: {line_count} lines"
    assert "live write authorized" not in text.lower()
    assert "--no-verify" in text

    for required in REQUIRED_STRINGS:
        assert required in text

    assert re.search(r"Base HEAD: [0-9a-f]{40}", text), "Atlas must cite a full 40-char base HEAD"


def test_atlas_references_real_artifacts():
    for rel in REQUIRED_REAL_PATHS:
        assert (REPO / rel).exists(), f"Referenced artifact does not exist: {rel}"


def test_atlas_keeps_release_boundaries_clear():
    text = ATLAS.read_text(encoding="utf-8")

    release_1 = text.index("Release 1")
    release_2 = text.index("Release 2")
    release_3 = text.index("Release 3")

    assert release_1 < release_2 < release_3
    assert "A8-R86 Marketing Expert Foundation" in text
    assert "reopen Release 1" in text