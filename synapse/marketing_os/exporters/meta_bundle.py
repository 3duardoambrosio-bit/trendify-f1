from __future__ import annotations

from pathlib import Path
from typing import Any

from synapse.infra.contract_snapshot import stable_json_dumps


def write_meta_bundle(
    out_dir: Path,
    *,
    product_id: str,
    creatives: list[dict[str, Any]],
) -> Path:
    """
    Writes a minimal Meta assets bundle as JSON.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "product_id": product_id,
        "count": len(creatives),
        "creatives": creatives,
    }
    out = out_dir / "meta_assets.json"
    out.write_text(stable_json_dumps(payload) + "\n", encoding="utf-8", newline="\n")
    return out
