from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ForecastGateResult:
    ok: bool
    json_exists: int
    csv_exists: int
    md_exists: int


def check_forecast_artifacts(
    report_json: Path = Path("./out/forecast/synapse_report_v13_2.json"),
    scenarios_csv: Path = Path("./out/forecast/synapse_scenarios_v13_2.csv"),
    report_md: Path = Path("./out/forecast/synapse_cloud_report.md"),
) -> ForecastGateResult:
    """
    Not wired into synapse.infra.doctor yet (by design).
    This is a reusable gate for future automation.
    """
    je = int(report_json.exists())
    ce = int(scenarios_csv.exists())
    me = int(report_md.exists())
    ok = bool(je == 1 and ce == 1 and me == 1)
    return ForecastGateResult(ok=ok, json_exists=je, csv_exists=ce, md_exists=me)
