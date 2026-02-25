from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import deal

logger = logging.getLogger(__name__)


class KillSwitchLevel(str, Enum):
    CAMPAIGN = "campaign"
    CHANNEL = "channel"
    PORTFOLIO = "portfolio"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class KillSwitchActivation:
    level: KillSwitchLevel
    reason: str
    triggered_by: str = "system"
    target_id: Optional[str] = None
    activated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class KillSwitch:
    """
    Kill switch with optional file-backed persistence.

    Without state_file: in-memory only.
    With state_file: survives restarts via atomic JSON writes.

    Safety rule: loader FAIL-CLOSED on corrupted/unreadable state file (SYSTEM kill activated).
    Persistence rule: writer never crashes the caller; it logs errors and keeps in-memory state.
    """

    @deal.pre(lambda self, state_file=None: True, message="KillSwitch.__init__ contract")
    @deal.post(lambda result: result is None, message="KillSwitch.__init__ returns None")
    @deal.raises(deal.RaisesContractError)
    def __init__(self, *, state_file: Optional[Path] = None) -> None:
        self._active: Dict[str, KillSwitchActivation] = {}
        self._state_file: Optional[Path] = Path(state_file) if state_file else None
        if self._state_file is not None:
            self._load_state()

    @deal.pre(lambda self, activation: True, message="KillSwitch.activate contract")
    @deal.post(lambda result: result is None, message="KillSwitch.activate returns None")
    @deal.raises(deal.RaisesContractError)
    def activate(self, activation: KillSwitchActivation) -> None:
        key = self._key(activation.level, activation.target_id)
        self._active[key] = activation
        self._persist()

    @deal.pre(lambda self, level, target_id=None: True, message="KillSwitch.is_active contract")
    @deal.post(lambda result: isinstance(result, bool), message="KillSwitch.is_active must return bool")
    @deal.raises(deal.RaisesContractError)
    def is_active(self, level: KillSwitchLevel, target_id: Optional[str] = None) -> bool:
        return self._key(level, target_id) in self._active

    @deal.pre(lambda self, level, target_id=None: True, message="KillSwitch.clear contract")
    @deal.post(lambda result: result is None, message="KillSwitch.clear returns None")
    @deal.raises(deal.RaisesContractError)
    def clear(self, level: KillSwitchLevel, target_id: Optional[str] = None) -> None:
        key = self._key(level, target_id)
        if key in self._active:
            del self._active[key]
        self._persist()

    @deal.pre(lambda self: True, message="KillSwitch.snapshot contract")
    @deal.post(lambda result: isinstance(result, dict), message="KillSwitch.snapshot must return dict")
    @deal.raises(deal.RaisesContractError)
    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in self._active.items():
            out[k] = {
                "level": v.level.value,
                "reason": v.reason,
                "triggered_by": v.triggered_by,
                "target_id": v.target_id,
                "activated_at": v.activated_at.isoformat(),
            }
        return out

    @staticmethod
    def _key(level: KillSwitchLevel, target_id: Optional[str]) -> str:
        return f"{level.value}:{target_id or '*'}"

    # --- Persistence (private) ---

    def _persist(self) -> None:
        if self._state_file is None:
            return

        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.error("killswitch persist mkdir failed for %s", self._state_file, exc_info=True)
            return

        if not self._active:
            try:
                self._state_file.unlink(missing_ok=True)
            except OSError:
                logger.debug("killswitch unlink suppressed", exc_info=True)
            return

        data: Dict[str, Dict[str, Any]] = self.snapshot()
        try:
            self._atomic_write(data)
        except OSError:
            logger.error("killswitch atomic write failed for %s", self._state_file, exc_info=True)

    def _atomic_write(self, data: Dict[str, Dict[str, Any]]) -> None:
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
            raw_any = json.loads(self._state_file.read_text(encoding="utf-8"))
            if not isinstance(raw_any, dict):
                raise ValueError("state must be a dict")

            raw: Dict[str, Any] = raw_any
            for key, entry_any in raw.items():
                if not isinstance(key, str) or not isinstance(entry_any, dict):
                    raise ValueError("invalid entry shape")

                entry: Dict[str, Any] = entry_any
                tid_any = entry.get("target_id")
                if tid_any is None:
                    tid: Optional[str] = None
                elif isinstance(tid_any, str):
                    tid = tid_any
                else:
                    raise ValueError("target_id must be str|None")

                act = KillSwitchActivation(
                    level=KillSwitchLevel(str(entry["level"])),
                    reason=str(entry["reason"]),
                    triggered_by=str(entry.get("triggered_by", "system")),
                    target_id=tid,
                    activated_at=datetime.fromisoformat(str(entry["activated_at"])),
                )
                self._active[key] = act

        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError, TypeError):
            self._active = {}
            sys_key = self._key(KillSwitchLevel.SYSTEM, None)
            self._active[sys_key] = KillSwitchActivation(
                level=KillSwitchLevel.SYSTEM,
                reason="KILLSWITCH_STATE_CORRUPTED",
                triggered_by="killswitch_loader",
                target_id=None,
            )
            logger.error(
                "killswitch state corrupted at %s; FAIL-CLOSED SYSTEM kill activated",
                self._state_file,
                exc_info=True,
            )