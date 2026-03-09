from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from synapse.infra.refund_normalizer import RefundEvent, refund_event_from_dict, refund_event_to_dict


@dataclass(frozen=True)
class RefundRegistryResult:
    recorded: bool
    duplicate: bool
    refund_id: str
    path: str
    line_count: int


def record_refund_event(path: Union[str, Path], event: RefundEvent) -> RefundRegistryResult:
    p = Path(path)
    existing_ids = set()
    line_count = 0

    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                existing = refund_event_from_dict(obj)
                existing_ids.add(existing.refund_id)
                line_count += 1

    if event.refund_id in existing_ids:
        return RefundRegistryResult(
            recorded=False,
            duplicate=True,
            refund_id=event.refund_id,
            path=str(p),
            line_count=line_count,
        )

    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(refund_event_to_dict(event), ensure_ascii=False) + "\n")

    return RefundRegistryResult(
        recorded=True,
        duplicate=False,
        refund_id=event.refund_id,
        path=str(p),
        line_count=line_count + 1,
    )