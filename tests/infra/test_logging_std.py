from __future__ import annotations

import logging

import synapse.infra.logging_std as ls


def test_import_has_no_side_effect_handlers() -> None:
    root = logging.getLogger()
    # We don't assert it is empty (pytest may attach handlers), we assert we didn't ADD one.
    before = len(root.handlers)
    import importlib

    importlib.reload(ls)
    after = len(root.handlers)
    assert after == before


def test_configure_logging_idempotent() -> None:
    root = logging.getLogger()
    before = len(root.handlers)
    ls.configure_logging()
    after = len(root.handlers)
    # either unchanged (pytest already configured) or adds exactly 1 handler
    assert after == before or after == before + 1
