

# SYNAPSE A8-R53 VISIBLE SIMULATION FAST-PATH START
def _synapse_a8_r53_visible_simulation_fast_path() -> None:
    """Route `python -m synapse.cli simulate` before the existing dispatcher.

    This preserves the existing CLI commands and avoids rewriting the current
    argparse command registry. The simulation remains local-only and delegates
    to synapse.cli.simulate, which owns its own evidence sandbox contract.
    """
    import sys as _synapse_a8_r53_sys

    if len(_synapse_a8_r53_sys.argv) > 1 and _synapse_a8_r53_sys.argv[1] == "simulate":
        from synapse.cli.simulate import main as _synapse_a8_r53_simulate_main

        raise SystemExit(_synapse_a8_r53_simulate_main(_synapse_a8_r53_sys.argv[2:]))


_synapse_a8_r53_visible_simulation_fast_path()
# SYNAPSE A8-R53 VISIBLE SIMULATION FAST-PATH END

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
