from __future__ import annotations

import argparse
import os
from typing import Sequence

from synapse.cli.commands import doctor_cmd, learning_cmd, pulse_cmd, snapshot_cmd, triage_cmd, wave_cmd
from synapse.infra.diagnostics import capture_exception, suggest_fix


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="synapse.cli",
        description="SYNAPSE Unified CLI (doctor, wave, learning, pulse, snapshot, triage).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    doctor_cmd.register(sub)
    wave_cmd.register(sub)
    learning_cmd.register(sub)
    pulse_cmd.register(sub)
    snapshot_cmd.register(sub)
    triage_cmd.register(sub)

    if os.getenv("SYNAPSE_DEBUG_CLI") == "1":
        from synapse.cli.commands import debug_crash_cmd  # lazy import

        debug_crash_cmd.register(sub)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    fn = getattr(args, "_fn", None)
    if fn is None:
        parser.print_help()
        return 2

    try:
        rc = fn(args)
        if rc is None:
            return 0
        if isinstance(rc, bool):
            return 0 if rc else 1
        if isinstance(rc, int):
            return rc
        return 0

    except KeyboardInterrupt:
        print("synapse: CANCELLED (KeyboardInterrupt)", flush=True)
        return 130

    except SystemExit as e:
        code = getattr(e, "code", 1)
        return int(code) if isinstance(code, int) else 1

    except Exception as e:
        rep = capture_exception(
            e,
            context={
                "cli": {
                    "command": getattr(args, "command", None),
                    "parsed_args": vars(args),
                    "argv": list(argv) if argv is not None else None,
                }
            },
        )
        print(f"synapse: ERROR — {type(e).__name__}: {e}", flush=True)
        hint = suggest_fix(e)
        if hint:
            print(f"synapse: HINT — {hint}", flush=True)
        print(f"synapse: crash_report={rep.path} fingerprint={rep.fingerprint}", flush=True)
        print(f"synapse: next => python -m synapse.cli triage --path \"{rep.path}\"", flush=True)
        return 3

# --- AUTO-PATCH: import hygiene wrapper (tests expect no heavy modules in sys.modules after dry-run) ---
try:
    from synapse.cli._import_hygiene import wrap_main as _wrap_main  # type: ignore
    main = _wrap_main(main)  # type: ignore
except Exception:
    pass
# --- END AUTO-PATCH ---

