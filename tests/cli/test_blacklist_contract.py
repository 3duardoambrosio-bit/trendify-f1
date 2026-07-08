from __future__ import annotations

import ast
from pathlib import Path

from synapse.cli._blacklist import GENERIC_BLACKLIST


def test_generic_blacklist_contract_is_stable() -> None:
    assert isinstance(GENERIC_BLACKLIST, tuple)
    assert len(GENERIC_BLACKLIST) == 28
    assert len(set(GENERIC_BLACKLIST)) == 28
    assert all(isinstance(pattern, str) for pattern in GENERIC_BLACKLIST)
    assert all(pattern == pattern.strip() for pattern in GENERIC_BLACKLIST)
    assert all(pattern for pattern in GENERIC_BLACKLIST)


def test_generic_blacklist_contains_known_npc_markers() -> None:
    required = {
        "compra ahora",
        "dile adiós",
        "dile adios",
        "producto increíble",
        "producto increible",
        "solución perfecta",
        "solucion perfecta",
    }

    assert required.issubset(set(GENERIC_BLACKLIST))


def test_blacklist_module_is_pure_data_shape() -> None:
    source_path = Path("synapse/cli/_blacklist.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))

    forbidden_text = [
        "subprocess",
        "requests",
        "urllib",
        "socket",
        ".write_text(",
        ".write_bytes(",
        "open(",
    ]

    for token in forbidden_text:
        assert token not in source

    allowed_node_types = (
        ast.Module,
        ast.Expr,
        ast.Constant,
        ast.ImportFrom,
        ast.alias,
        ast.AnnAssign,
        ast.Assign,
        ast.Name,
        ast.Subscript,
        ast.Tuple,
        ast.List,
        ast.Load,
        ast.Store,
    )

    for node in ast.walk(tree):
        assert isinstance(node, allowed_node_types), type(node).__name__
