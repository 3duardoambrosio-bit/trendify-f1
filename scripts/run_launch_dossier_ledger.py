import json
import pandas as pd
from pathlib import Path

def load_candidates_table(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Candidates file not found: {p}")

    ext = p.suffix.lower()

    if ext == ".csv":
        df = pd.read_csv(p)

    elif ext == ".json":
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # soporta lista plana o dict con buckets comunes
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict):
            for key in ("items", "products", "data"):
                if key in raw and isinstance(raw[key], list):
                    rows = raw[key]
                    break
            else:
                # data anidada tipo {"data":{"products":[...]}}
                if isinstance(raw.get("data"), dict):
                    d2 = raw["data"]
                    rows = d2.get("products") or d2.get("items") or []
                else:
                    rows = []
        else:
            rows = []

        df = pd.DataFrame(rows)

    elif ext in (".ndjson", ".jsonl"):
        rows = []
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        df = pd.DataFrame(rows)

    else:
        raise ValueError(f"Unsupported candidates file type: {ext}")

    if df is None or df.empty:
        raise ValueError(f"Loaded 0 candidates from {p}. Schema mismatch or empty file.")

    return df
