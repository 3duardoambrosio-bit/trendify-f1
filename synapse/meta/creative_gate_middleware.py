"""
Creative Gate Middleware — S14: Pipeline integration for creative validation.

Bridges PipelineE2E products with CreativePackGate.
If a product has a kit_dir, validates it BEFORE publishing.

FAIL-CLOSED:
  - kit_dir missing → blocked
  - gate fails → blocked
  - Pillow missing → blocked
  - Exception in gate → blocked

Backward compatible: if creative_gate_enabled=False in config,
the gate is skipped (for tests or migration).

__MARKER__ embedded in module constant below.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

__MARKER__ = "SESSION_S14_creative_gate_middleware_2026-03-03"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CreativeGateCheckResult:
    """Result of creative gate check for a single product."""
    allowed: bool
    reason: str
    kit_dir: str
    errors: list
    warnings: list


def check_creative_gate(product: Any, kit_dir: Optional[str] = None) -> CreativeGateCheckResult:
    """
    Validate a product's creative kit through the creative gate.

    Resolves kit_dir from:
      1. Explicit kit_dir parameter
      2. product.kit_dir attribute
      3. product.product.kit_dir attribute

    If no kit_dir found → FAIL-CLOSED.
    """
    # Resolve kit_dir
    resolved_dir = kit_dir
    if resolved_dir is None:
        resolved_dir = getattr(product, "kit_dir", None)
    if resolved_dir is None:
        inner = getattr(product, "product", None)
        if inner is not None:
            resolved_dir = getattr(inner, "kit_dir", None)

    if not resolved_dir:
        return CreativeGateCheckResult(
            allowed=False,
            reason="kit_dir_missing",
            kit_dir="",
            errors=["no_kit_dir_on_product"],
            warnings=[],
        )

    try:
        from synapse.shopify.creative_pack_gate import (
            CreativeGateConfig,
            validate_kit_dir,
        )
    except ImportError as e:
        log.critical("CREATIVE_GATE_IMPORT_FAILED: %s — blocking publish", e)
        return CreativeGateCheckResult(
            allowed=False,
            reason="gate_module_unavailable",
            kit_dir=str(resolved_dir),
            errors=[f"import_error:{e}"],
            warnings=[],
        )

    try:
        gate_result = validate_kit_dir(str(resolved_dir), CreativeGateConfig())
    except Exception as e:
        log.error("CREATIVE_GATE_EXCEPTION: %s — blocking publish", e)
        return CreativeGateCheckResult(
            allowed=False,
            reason="gate_exception",
            kit_dir=str(resolved_dir),
            errors=[f"exception:{type(e).__name__}:{e}"],
            warnings=[],
        )

    return CreativeGateCheckResult(
        allowed=gate_result.allowed,
        reason="gate_passed" if gate_result.allowed else "gate_failed",
        kit_dir=str(resolved_dir),
        errors=list(gate_result.errors),
        warnings=list(gate_result.warnings),
    )
