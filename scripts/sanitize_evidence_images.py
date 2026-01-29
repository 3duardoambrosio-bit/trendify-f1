#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sanitiza placeholders de imagen (ej. via.placeholder.com) dentro de un JSON.
- Recorre recursivamente dict/list.
- Si encuentra strings con dominios bloqueados, los reemplaza por:
    - None (default) o
    - un default URL (por ejemplo tu Shopify CDN)
- Genera reporte de cuántas cosas tocó.
"""

from __future__ import annotations
import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

BLOCKED_PATTERNS = [
    re.compile(r"via\.placeholder\.com", re.IGNORECASE),
]

IMAGE_KEY_HINT = re.compile(r"(image|img|thumbnail|picture|photo)", re.IGNORECASE)


@dataclass
class Report:
    input: str
    output: str
    in_place: bool
    replace_mode: str  # "null" | "default"
    default_url: str | None
    scanned_nodes: int
    scanned_strings: int
    replaced_strings: int
    replaced_nodes: int
    blocked_hits: int
    blocked_examples: List[str]


def is_blocked_url(s: str) -> bool:
    for pat in BLOCKED_PATTERNS:
        if pat.search(s):
            return True
    return False


def sanitize_value(val: Any, replace_with: str, default_url: str | None,
                   report: Dict[str, Any], path_stack: List[str]) -> Any:
    """
    Recursively sanitize JSON node.
    report: mutable counters + examples
    path_stack: debug path within JSON
    """
    report["scanned_nodes"] += 1

    if isinstance(val, str):
        report["scanned_strings"] += 1
        if is_blocked_url(val):
            report["blocked_hits"] += 1
            if len(report["blocked_examples"]) < 10:
                report["blocked_examples"].append(f"{'/'.join(path_stack)} => {val[:160]}")
            report["replaced_strings"] += 1
            report["replaced_nodes"] += 1
            if replace_with == "default":
                return default_url or val
            return None
        return val

    if isinstance(val, list):
        out = []
        for idx, item in enumerate(val):
            out.append(sanitize_value(item, replace_with, default_url, report, path_stack + [f"[{idx}]"]))
        return out

    if isinstance(val, dict):
        out = {}
        for k, v in val.items():
            k_str = str(k)
            # Recorremos todo, pero si la key huele a imagen, igual lo limpiamos
            out[k] = sanitize_value(v, replace_with, default_url, report, path_stack + [k_str])
        return out

    # numbers, bools, null
    return val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Ruta al JSON de entrada")
    ap.add_argument("--output", default=None, help="Ruta al JSON de salida (si no, genera *_sanitized.json)")
    ap.add_argument("--in-place", action="store_true", help="Sobrescribe el archivo de entrada")
    ap.add_argument("--replace-with", choices=["null", "default"], default="null",
                    help="Cómo reemplazar placeholders: null (None) o default (URL). Default: null")
    ap.add_argument("--default-url", default=None,
                    help="URL default (solo si --replace-with default). Ej: https://cdn.shopify.com/.../default.png")
    ap.add_argument("--fail-if-found", action="store_true",
                    help="Si encuentra placeholders, sale con código 2 (útil para CI).")
    args = ap.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        raise SystemExit(f"ERROR: No existe: {inp}")

    raw = inp.read_text(encoding="utf-8")
    data = json.loads(raw)

    counters = {
        "scanned_nodes": 0,
        "scanned_strings": 0,
        "replaced_strings": 0,
        "replaced_nodes": 0,
        "blocked_hits": 0,
        "blocked_examples": [],
    }

    cleaned = sanitize_value(
        data,
        replace_with=args.replace_with,
        default_url=args.default_url,
        report=counters,
        path_stack=[inp.name],
    )

    if args.in_place:
        outp = inp
    else:
        outp = Path(args.output) if args.output else inp.with_name(inp.stem + "_sanitized.json")

    outp.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")

    rep = Report(
        input=str(inp),
        output=str(outp),
        in_place=bool(args.in_place),
        replace_mode=args.replace_with,
        default_url=args.default_url,
        scanned_nodes=counters["scanned_nodes"],
        scanned_strings=counters["scanned_strings"],
        replaced_strings=counters["replaced_strings"],
        replaced_nodes=counters["replaced_nodes"],
        blocked_hits=counters["blocked_hits"],
        blocked_examples=counters["blocked_examples"],
    )

    rep_path = outp.with_suffix(outp.suffix + ".sanitize_report.json")
    rep_path.write_text(json.dumps(asdict(rep), ensure_ascii=False, indent=2), encoding="utf-8")

    print("SANITIZE_OK")
    print(f"IN : {rep.input}")
    print(f"OUT: {rep.output}")
    print(f"HITS(blocked): {rep.blocked_hits}")
    print(f"REPLACED(strings): {rep.replaced_strings}")
    print(f"REPORT: {rep_path}")

    if args.fail_if_found and rep.blocked_hits > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
