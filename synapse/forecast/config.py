from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ForecastPaths:
    """
    Centralizes conventional artifact paths without hard-coding in multiple tools.
    """
    outdir: Path = Path("./out/forecast")
    report_json: Path = Path("./out/forecast/synapse_report_v13_2.json")
    scenarios_csv: Path = Path("./out/forecast/synapse_scenarios_v13_2.csv")
    report_md: Path = Path("./out/forecast/synapse_cloud_report.md")
    suite_report_json: Path = Path("./out/forecast/synapse_forecast_suite_report.json")
