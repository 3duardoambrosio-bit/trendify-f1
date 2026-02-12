from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timezone
import logging
logger = logging.getLogger(__name__)


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
    activated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class KillSwitch:
    """
    Kill switch with optional file-backed persistence.

    Without state_file: pure in-memory (backwards compatible).
    With state_file: survives process restarts via atomic JSON writes.
    """
    def __init__(self, *, state_file: Optional[Path] = None) -> None:
        self._active: Dict[str, KillSwitchActivation] = {}
        self._state_file = Path(state_file) if state_file else None
        if self._state_file is not None:
            self._load_state()

    def activate(self, activation: KillSwitchActivation) -> None:
        key = self._key(activation.level, activation.target_id)
        self._active[key] = activation
        self._persist()

    def is_active(self, level: KillSwitchLevel, target_id: Optional[str] = None) -> bool:
        return self._key(level, target_id) in self._active

    def clear(self, level: KillSwitchLevel, target_id: Optional[str] = None) -> None:
        key = self._key(level, target_id)
        if key in self._active:
            del self._active[key]
        self._persist()

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

    # --- Persistence ---

    def _persist(self) -> None:
        if self._state_file is None:
            return
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        if not self._active:
            # No active switches: remove state file
            try:
                self._state_file.unlink(missing_ok=True)
            except OSError:
                logger.debug("suppressed exception", exc_info=True)
            return

        data = {}
        for key, act in self._active.items():
            data[key] = {
                "level": act.level.value,
                "reason": act.reason,
                "triggered_by": act.triggered_by,
                "target_id": act.target_id,
                "activated_at": act.activated_at.isoformat(),
            }
        self._atomic_write(data)

    def _atomic_write(self, data: dict) -> None:
        """Write JSON atomically: write to .tmp, fsync, then os.replace."""
        assert self._state_file is not None
        tmp_path = self._state_file.with_suffix(".tmp")
        content = json.dumps(data, ensure_ascii=False, indent=2)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(self._state_file))

    def _load_state(self) -> None:
        if self._state_file is None or not self._state_file.exists():
            return
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            for key, entry in raw.items():
                act = KillSwitchActivation(
                    level=KillSwitchLevel(entry["level"]),
                    reason=entry["reason"],
                    triggered_by=entry.get("triggered_by", "system"),
                    target_id=entry.get("target_id"),
                    activated_at=datetime.fromisoformat(entry["activated_at"]),
                )
                self._active[key] = act
        except (json.JSONDecodeError, KeyError, ValueError):
            # Corrupted state file — FAIL CLOSED (SYSTEM kill), never fail-open.
            self._active = {}
            sys_key = self._key(KillSwitchLevel.SYSTEM, None)
            self._active[sys_key] = KillSwitchActivation(
                level=KillSwitchLevel.SYSTEM,
                reason="KILLSWITCH_STATE_CORRUPTED",
                triggered_by="killswitch_loader",
                target_id=None,
            )
            logger.error("killswitch state corrupted at %s; FAIL-CLOSED SYSTEM kill activated", self._state_file)