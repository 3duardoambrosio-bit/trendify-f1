from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from infra.ledger_v2 import LedgerV2
from ops.dropi_incident_runtime import DropiIncidentContext, DropiIncidentRuntime


def _parse_dt(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError(f"datetime must be timezone-aware: {raw}")
    return dt


def _resolve_ledger_path(raw: str) -> Path:
    base = Path(raw)
    if base.suffix.lower() == ".ndjson":
        return base
    return base / "ledger_dropi_incident_runtime.ndjson"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run Dropi incident runtime bridge and emit a ledger event."
    )
    p.add_argument("--order-id", required=True)
    p.add_argument("--payment-method", required=True)
    p.add_argument("--issue-type", required=True)
    p.add_argument("--order-created-at", required=True, help="ISO datetime with timezone")
    p.add_argument("--customer-paid-at", default=None, help="ISO datetime with timezone")
    p.add_argument("--supplier-payment-delay-hours", type=int, default=24)
    p.add_argument("--resolution-preference", default="replacement")
    p.add_argument("--channel", default="ops_runtime")
    p.add_argument("--metadata-json", default="{}")
    p.add_argument("--ledger-dir", default=r"data\ledger")
    return p


def main() -> None:
    args = build_parser().parse_args()
    metadata = json.loads(args.metadata_json)

    ledger_path = _resolve_ledger_path(args.ledger_dir)
    ledger = LedgerV2(path=ledger_path)
    try:
        runtime = DropiIncidentRuntime(ledger=ledger)
        decision = runtime.decide(
            DropiIncidentContext(
                order_id=args.order_id,
                payment_method=args.payment_method,
                issue_type=args.issue_type,
                order_created_at=_parse_dt(args.order_created_at),
                customer_paid_at=_parse_dt(args.customer_paid_at),
                supplier_payment_delay_hours=args.supplier_payment_delay_hours,
                resolution_preference=args.resolution_preference,
                channel=args.channel,
                metadata=metadata,
            )
        )
        print(json.dumps(asdict(decision), ensure_ascii=False, indent=2, default=str))
    finally:
        close = getattr(ledger, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()