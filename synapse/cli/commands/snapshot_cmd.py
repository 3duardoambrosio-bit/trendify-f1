from __future__ import annotations

import argparse
from pathlib import Path

from synapse.infra.contract_snapshot import SnapshotConfig, build_snapshot, compute_hashes, write_snapshot
from synapse.infra.logging_std import configure_logging, get_logger, log_kv


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("snapshot", help="Write a contract snapshot (hashes + schema_version).")
    p.add_argument("--name", default="synapse-contract", help="Snapshot name.")
    p.add_argument("--schema-version", default="v1", help="Schema version label.")
    p.add_argument("--paths", nargs="+", required=True, help="File paths to hash.")
    p.add_argument("--out", default=r"data\ledger\contracts\contract_snapshot.json", help="Output JSON path.")
    p.add_argument("--no-timestamp", action="store_true", help="Deterministic snapshot (no created_at).")
    p.set_defaults(_fn=_run)


def _run(args: argparse.Namespace) -> int:
    configure_logging()
    lg = get_logger("synapse.cli.snapshot")

    paths = [Path(p) for p in args.paths]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        log_kv(lg, "snapshot: missing files", missing=missing)
        return 2

    hashes = compute_hashes(paths, base_dir=Path.cwd())
    cfg = SnapshotConfig(
        name=str(args.name),
        schema_version=str(args.schema_version),
        include_timestamp=not bool(args.no_timestamp),
    )
    payload = build_snapshot(config=cfg, hashes=hashes, meta={"cwd": str(Path.cwd())})

    out = Path(args.out)
    write_snapshot(out, payload)
    log_kv(lg, "snapshot: written", out=str(out), files=len(paths))
    return 0
