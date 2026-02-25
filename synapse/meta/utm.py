# synapse/meta/utm.py
"""
UTM — OLEADA 19
===============

Formato contract:
utm_content = H{hook_id}_A{angle}_V{variant}

Ej:
H01_Adolor_V1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


class UTMError(Exception):
    pass


def build_utm_content(hook_id: str, angle: str, variant: str) -> str:
    hook = str(hook_id).strip()
    ang = str(angle).strip()
    var = str(variant).strip()
    if not hook or not ang or not var:
        raise UTMError("hook_id, angle, variant required")
    return f"H{hook}_A{ang}_V{var}"


def parse_utm_content(utm_content: str) -> Dict[str, str]:
    s = str(utm_content or "").strip()
    if not s.startswith("H") or "_A" not in s or "_V" not in s:
        raise UTMError("Invalid utm_content format")
    # H{hook}_A{angle}_V{variant}
    try:
        h_part, rest = s[1:].split("_A", 1)
        a_part, v_part = rest.split("_V", 1)
        return {"hook_id": h_part, "angle": a_part, "variant": v_part}
    except (KeyError, IndexError, TypeError) as e:
        raise UTMError("Invalid utm_content parse") from e
