# Forecast (synapse.forecast)

This module provides a tiny, test-driven core for forecast paths and scenario math.

## Core primitives
- `MonthRow`: normalized month record + derived metrics (`roas_eff_collected`, gate `unit>=thr`)
- `extend_plateau(rows, months)`: deterministic extension of a path to N months
- `first_profitable_month`, `first_cum_net_ge_0_month`

## Intended usage (tools / automation)
Tools can keep generating `out/forecast/synapse_report_v13_2.json` and then load it:

```py
from pathlib import Path
from synapse.forecast.model import load_report, extend_plateau

rep = load_report(Path("./out/forecast/synapse_report_v13_2.json"))
sc  = rep.get("FINISHED_BASE")
ext = extend_plateau(sc.path, 36)
print(len(ext), ext[-1].m)
```

