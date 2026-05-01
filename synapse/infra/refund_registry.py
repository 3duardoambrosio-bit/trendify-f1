from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Union

from infra.idempotency import execute_once
from synapse.infra.refund_normalizer import RefundEvent, refund_event_from_dict, refund_event_to_dict


class RefundRegistryError(RuntimeError):
    """Raised when refund registry recording cannot be completed safely."""


@dataclass(frozen=True)
class RefundRegistryResult:
    recorded: bool
    duplicate: bool
    refund_id: str
    path: str
    line_count: int


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _registry_db_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_idempotency.sqlite3")


def _append_registry_row(path: Path, event: RefundEvent) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = refund_event_to_dict(event)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return _count_lines(path)


def _build_result(
    *,
    recorded: bool,
    duplicate: bool,
    refund_id: str,
    path: Path,
    response: Dict[str, object] | None,
) -> RefundRegistryResult:
    response = response or {}
    line_count_raw = response.get("line_count", _count_lines(path))
    try:
        line_count = int(line_count_raw)
    except (TypeError, ValueError):
        line_count = _count_lines(path)

    return RefundRegistryResult(
        recorded=recorded,
        duplicate=duplicate,
        refund_id=refund_id,
        path=str(response.get("path") or path),
        line_count=line_count,
    )


def record_refund_event(path: Union[str, Path], event: RefundEvent) -> RefundRegistryResult:
    p = Path(path)
    refund_id = str(event.refund_id).strip()
    if refund_id == "":
        raise RefundRegistryError("empty_refund_id")

    payload = refund_event_to_dict(event)
    db_path = _registry_db_path(p)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    def _operation(_: Dict[str, object]) -> Dict[str, object]:
        line_count = _append_registry_row(p, event)
        return {
            "path": str(p),
            "line_count": line_count,
        }

    idem_result = execute_once(
        key=f"refund_registry:{refund_id}",
        payload=payload,
        operation=_operation,
        db_path=db_path,
    )

    status = str(idem_result.get("status") or "").strip().lower()
    response = idem_result.get("response")
    if not isinstance(response, dict):
        response = {}

    if status == "completed":
        return _build_result(
            recorded=True,
            duplicate=False,
            refund_id=refund_id,
            path=p,
            response=response,
        )

    if status == "duplicate":
        return _build_result(
            recorded=False,
            duplicate=True,
            refund_id=refund_id,
            path=p,
            response=response,
        )

    if status == "conflict":
        raise RefundRegistryError("idempotency_conflict")

    if status == "in_flight":
        raise RefundRegistryError("idempotency_in_flight")

    raise RefundRegistryError(f"unexpected_idempotency_status:{status or '<empty>'}")
