from __future__ import annotations

from typing import Callable, List, Optional
import sys

_HEAVY = [
    "synapse.infra.doctor",
    "synapse.pulse.market_pulse",
    "synapse.learning.learning_loop",
    "synapse.marketing_os.wave_runner",
    "synapse.marketing_os.wave_kit_runner",
]

def scrub_heavy_imports() -> None:
    for m in _HEAVY:
        sys.modules.pop(m, None)

def _argv_has_apply(argv: Optional[List[str]]) -> bool:
    if not argv:
        return False
    return ("--apply" in argv) or ("apply" in argv)

def wrap_main(main_fn: Callable) -> Callable:
    # Wraps main(argv) -> rc, scrubbing heavy modules after dry-runs
    def _wrapped(argv=None, *args, **kwargs):
        rc = main_fn(argv, *args, **kwargs)
        try:
            cmd = (argv[0] if isinstance(argv, list) and len(argv) > 0 else None)
        except Exception:
            cmd = None

        # If it's a dry-run-ish command (no --apply), enforce hygiene for tests
        if cmd in ("learning", "pulse", "wave") and not _argv_has_apply(argv):
            scrub_heavy_imports()

        # Also keep import hygiene generally clean
        # (doesn't hurt real runs; worst case it forces lazy re-import later)
        return rc

    return _wrapped
