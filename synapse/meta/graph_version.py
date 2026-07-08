"""Canonical Meta Graph API version resolution.

A8-R3 invariant:
- default Graph/Marketing API version is v25.0
- environment override remains explicit through META_GRAPH_VERSION
- callers must not hardcode stale v22.0 fallbacks in write paths
"""

from __future__ import annotations

import os
from typing import Optional


DEFAULT_META_GRAPH_VERSION = "v25.0"


def resolve_meta_graph_version(value: Optional[str] = None) -> str:
    """Return the explicit graph version or the canonical safe default."""

    raw = os.getenv("META_GRAPH_VERSION", "") if value is None else value
    resolved = str(raw or "").strip()
    return resolved or DEFAULT_META_GRAPH_VERSION
