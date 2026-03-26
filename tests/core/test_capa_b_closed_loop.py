from __future__ import annotations

import importlib.util
from pathlib import Path

_PROBE_PATH = Path(__file__).resolve().with_name("capa_b_closed_loop_probe.py")
_SPEC = importlib.util.spec_from_file_location("capa_b_closed_loop_probe", _PROBE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load probe from {_PROBE_PATH}")

_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
run_all = _MODULE.run_all


def test_capa_b_closed_loop_contracts_and_scenarios():
    summary = run_all()

    assert summary["contract_error_count"] == 0, summary
    assert summary["probe_total"] == 2, summary
    assert summary["probe_ok_count"] == 2, summary
    assert summary["scenario_total"] == 2, summary
    assert summary["scenario_ok_count"] == 2, summary
    assert summary["probes"]["decision_journal"]["status"] == "ok", summary
    assert summary["probes"]["creative_tracker"]["status"] == "ok", summary
    assert summary["scenarios"]["nominal"]["status"] == "ok", summary
    assert summary["scenarios"]["breaker_open"]["status"] == "ok", summary
    assert summary["CAPA_B_PASS"] is True, summary