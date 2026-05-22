"""Static safety tests for the read-only Streamlit model."""

from __future__ import annotations

import ast
from pathlib import Path


READ_MODEL = Path("synapse/ui/read_model.py")


FORBIDDEN_MODULES = {
    "requests",
    "httpx",
    "subprocess",
}

FORBIDDEN_ATTR_CALLS = {
    ("Path", "write_text"),
    ("Path", "write_bytes"),
    ("subprocess", "run"),
    ("os", "system"),
    ("os", "popen"),
    ("urllib.request", "urlopen"),
}


def _attr_chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attr_chain(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def test_read_model_has_no_forbidden_imports() -> None:
    tree = ast.parse(READ_MODEL.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert not (imported & FORBIDDEN_MODULES)


def test_read_model_has_no_writes_execution_or_http_calls() -> None:
    tree = ast.parse(READ_MODEL.read_text(encoding="utf-8"))

    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function_name = _attr_chain(node.func)

            if function_name in {
                "subprocess.run",
                "os.system",
                "os.popen",
                "urllib.request.urlopen",
                "requests.get",
                "requests.post",
                "requests.request",
                "httpx.get",
                "httpx.post",
                "httpx.request",
            }:
                violations.append(function_name)

            if function_name.endswith(".write_text") or function_name.endswith(".write_bytes"):
                violations.append(function_name)

            if function_name == "open":
                mode = None
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    mode = node.args[1].value
                for keyword in node.keywords:
                    if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                        mode = keyword.value.value

                if mode is None:
                    violations.append("open")
                elif any(flag in str(mode) for flag in ("w", "a", "+", "x")):
                    violations.append(f"open:{mode}")

    assert violations == []
