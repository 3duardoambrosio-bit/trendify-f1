# synapse/marketing_os/brief_schema.py
"""Structured Marketing Brief schema for SYNAPSE A8-R66.

This module is intentionally pure:
- no network;
- no filesystem writes;
- no runtime spend;
- no UI coupling;
- deterministic serialization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SCHEMA_VERSION = "a8-r66.marketing_brief.v1"


@dataclass(frozen=True)
class BriefItem:
    """Atomic persuasive item with rationale."""

    text: str
    rationale: str
    safety_note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "text": self.text,
            "rationale": self.rationale,
            "safety_note": self.safety_note,
        }


@dataclass(frozen=True)
class ScriptVariant:
    """Script skeleton. Textual only. No visual asset generation."""

    duration: str
    format: str
    beats: tuple[str, ...]
    cta: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration": self.duration,
            "format": self.format,
            "beats": list(self.beats),
            "cta": self.cta,
        }


@dataclass(frozen=True)
class ClaimSafetyNotes:
    """Claim posture and restricted language notes."""

    posture: str
    notes: tuple[str, ...] = field(default_factory=tuple)
    detected_risk_terms: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "posture": self.posture,
            "notes": list(self.notes),
            "detected_risk_terms": list(self.detected_risk_terms),
        }


@dataclass(frozen=True)
class AntiNpcChecks:
    """Anti-generic contract for marketing outputs."""

    passed: bool
    checked_sections: tuple[str, ...] = field(default_factory=tuple)
    banned_matches: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checked_sections": list(self.checked_sections),
            "banned_matches": list(self.banned_matches),
        }


@dataclass(frozen=True)
class PermissionDecision:
    """Marketing permission state inherited from evaluation output."""

    status: str
    score: float | None = None
    threshold: float | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": self.score,
            "threshold": self.threshold,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class MarketingBrief:
    """Auditable structured brief for one product decision."""

    schema_version: str
    brief_id: str
    product_id: str
    product_name: str
    product_summary: str
    audience: str
    core_angle: str
    pain_points: tuple[BriefItem, ...]
    objections: tuple[BriefItem, ...]
    hooks: tuple[BriefItem, ...]
    scripts: tuple[ScriptVariant, ...]
    ctas: tuple[str, ...]
    claims_safety_notes: ClaimSafetyNotes
    anti_npc_checks: AntiNpcChecks
    permission: PermissionDecision
    blocked_reasoning: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pain_points"] = [item.to_dict() for item in self.pain_points]
        data["objections"] = [item.to_dict() for item in self.objections]
        data["hooks"] = [item.to_dict() for item in self.hooks]
        data["scripts"] = [script.to_dict() for script in self.scripts]
        data["claims_safety_notes"] = self.claims_safety_notes.to_dict()
        data["anti_npc_checks"] = self.anti_npc_checks.to_dict()
        data["permission"] = self.permission.to_dict()
        data["blocked_reasoning"] = list(self.blocked_reasoning)
        return data

    def validate_contract(self) -> tuple[bool, tuple[str, ...]]:
        issues: list[str] = []

        if self.schema_version != SCHEMA_VERSION:
            issues.append("SCHEMA_VERSION_MISMATCH")
        if not self.brief_id:
            issues.append("EMPTY_BRIEF_ID")
        if not self.product_id:
            issues.append("EMPTY_PRODUCT_ID")
        if not self.product_name:
            issues.append("EMPTY_PRODUCT_NAME")
        if len(self.pain_points) < 3:
            issues.append("PAIN_POINTS_LT_3")
        if len(self.objections) < 3:
            issues.append("OBJECTIONS_LT_3")
        if len(self.hooks) < 4:
            issues.append("HOOKS_LT_4")
        if len(self.scripts) < 2:
            issues.append("SCRIPTS_LT_2")
        if len(self.ctas) < 2:
            issues.append("CTAS_LT_2")
        if not self.claims_safety_notes.notes:
            issues.append("CLAIM_SAFETY_NOTES_EMPTY")
        if not self.anti_npc_checks.checked_sections:
            issues.append("ANTI_NPC_NOT_EXECUTED")
        if not self.anti_npc_checks.passed:
            issues.append("ANTI_NPC_FAILED")
        if self.permission.status == "blocked" and not self.blocked_reasoning:
            issues.append("BLOCKED_WITHOUT_REASONING")

        return (len(issues) == 0, tuple(issues))


__all__ = [
    "SCHEMA_VERSION",
    "AntiNpcChecks",
    "BriefItem",
    "ClaimSafetyNotes",
    "MarketingBrief",
    "PermissionDecision",
    "ScriptVariant",
]