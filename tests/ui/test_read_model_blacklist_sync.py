from __future__ import annotations

from synapse.cli._blacklist import GENERIC_BLACKLIST
from synapse.ui.read_model import NPC_BLACKLIST_PATTERNS


def test_read_model_uses_canonical_engine_blacklist_object() -> None:
    assert NPC_BLACKLIST_PATTERNS is GENERIC_BLACKLIST


def test_read_model_blacklist_has_no_visual_false_negative_gap() -> None:
    assert set(NPC_BLACKLIST_PATTERNS) == set(GENERIC_BLACKLIST)
    assert len(NPC_BLACKLIST_PATTERNS) == 28
    assert len(set(NPC_BLACKLIST_PATTERNS)) == 28
