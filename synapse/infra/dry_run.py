from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DryRunDecision:
    dry_run: bool
    reason: str


def resolve_dry_run(
    *,
    apply: bool = False,
    dry_run_flag: bool = False,
    default_dry_run: bool = True,
) -> DryRunDecision:
    """
    Standard decision function for 'dry-run vs apply'.

    Rules:
    - If --apply: dry_run=False
    - Else if --dry-run: dry_run=True
    - Else: dry_run=default_dry_run
    """
    if apply:
        return DryRunDecision(dry_run=False, reason="apply")
    if dry_run_flag:
        return DryRunDecision(dry_run=True, reason="explicit_dry_run")
    return DryRunDecision(dry_run=default_dry_run, reason="default")


def format_dry_run_banner(decision: DryRunDecision, label: str) -> str:
    mode = "DRY-RUN" if decision.dry_run else "APPLY"
    return f"{label}: {mode} (reason={decision.reason})"


def ensure_apply_allowed(decision: DryRunDecision, *, require: bool, error_msg: str) -> int:
    """
    Small helper: if apply is required but we're dry-run, return nonzero.
    """
    if require and decision.dry_run:
        return 2
    return 0
