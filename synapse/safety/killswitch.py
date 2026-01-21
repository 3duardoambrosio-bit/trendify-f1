from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict
from datetime import datetime


class KillSwitchLevel(str, Enum):
    CAMPAIGN = "campaign"
    CHANNEL = "channel"
    PORTFOLIO = "portfolio"
    SYSTEM = "system"


@dataclass(frozen=True)
class KillSwitchActivation:
    level: KillSwitchLevel
    reason: str
    triggered_by: str = "system"
    target_id: Optional[str] = None
    activated_at: datetime = datetime.utcnow()


class KillSwitch:
    """
    Simple, in-memory kill switch state.
    (Storage-backed integration comes later; v1 gives deterministic control.)
    """
    def __init__(self) -> None:
        self._active: Dict[str, KillSwitchActivation] = {}

    def activate(self, activation: KillSwitchActivation) -> None:
        key = self._key(activation.level, activation.target_id)
        self._active[key] = activation

    def is_active(self, level: KillSwitchLevel, target_id: Optional[str] = None) -> bool:
        return self._key(level, target_id) in self._active

    def clear(self, level: KillSwitchLevel, target_id: Optional[str] = None) -> None:
        key = self._key(level, target_id)
        if key in self._active:
            del self._active[key]

    def snapshot(self) -> Dict[str, dict]:
        return {k: {
            "level": v.level.value,
            "reason": v.reason,
            "triggered_by": v.triggered_by,
            "target_id": v.target_id,
            "activated_at": v.activated_at.isoformat(),
        } for k, v in self._active.items()}

    @staticmethod
    def _key(level: KillSwitchLevel, target_id: Optional[str]) -> str:
        return f"{level.value}:{target_id or '*'}"
