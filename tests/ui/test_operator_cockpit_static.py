"""Static safety tests for the A8-R74 operator cockpit module.

Fail-closed gates:
- no network library imports;
- no subprocess / heavy process execution;
- no file writes;
- no flag mutation surfaces (env writes or interactive toggles).
"""

from __future__ import annotations

import ast
from pathlib import Path


COCKPIT = Path("synapse/ui/operator_cockpit.py")

FORBIDDEN_IMPORT_ROOTS = {
    "requests",
    "httpx",
    "urllib",
    "aiohttp",
    "socket",
    "subprocess",
    "http",
    "ftplib",
    "telnetlib",
    "smtplib",
}

FORBIDDEN_IMPORT_MODULES = {
    "synapse.cli.cockpit",  # CLI uses subprocess; the UI must not pull it in.
}

FORBIDDEN_CALL_CHAINS = {
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_output",
    "os.system",
    "os.popen",
    "os.putenv",
    "os.environ.setdefault",
    "os.environ.update",
    "os.environ.pop",
    "urllib.request.urlopen",
    "requests.get",
    "requests.post",
    "requests.request",
    "httpx.get",
    "httpx.post",
    "httpx.request",
    "socket.socket",
}

FORBIDDEN_TOGGLE_TOKENS = (
    "st.toggle(",
    "st.checkbox(",
    ".toggle(",
    ".checkbox(",
)


def _source() -> str:
    return COCKPIT.read_text(encoding="utf-8")


def _tree() -> ast.AST:
    return ast.parse(_source())


def _attr_chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attr_chain(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def test_cockpit_no_network_imports() -> None:
    imported_roots: set[str] = set()
    imported_modules: set[str] = set()

    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
            imported_roots.add(node.module.split(".")[0])

    assert not (imported_roots & FORBIDDEN_IMPORT_ROOTS), imported_roots
    assert not (imported_modules & FORBIDDEN_IMPORT_MODULES), imported_modules


def test_cockpit_no_subprocess_heavy_or_pytest_invocation() -> None:
    source = _source()
    violations: list[str] = []

    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            chain = _attr_chain(node.func)
            if chain in FORBIDDEN_CALL_CHAINS:
                violations.append(chain)

    assert not violations, violations
    assert "-m pytest" not in source
    assert "pytest.main" not in source


def test_cockpit_no_write_calls() -> None:
    violations: list[str] = []

    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        chain = _attr_chain(node.func)

        if chain.endswith(".write_text") or chain.endswith(".write_bytes"):
            violations.append(chain)
        if chain.endswith(".mkdir") or chain.endswith(".unlink") or chain.endswith(".rmdir"):
            violations.append(chain)
        if chain in {"shutil.copy", "shutil.copyfile", "shutil.move", "shutil.rmtree"}:
            violations.append(chain)

        if chain == "open":
            mode = None
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                    mode = keyword.value.value
            if isinstance(mode, str) and any(ch in mode for ch in ("w", "a", "x", "+")):
                violations.append(f"open(mode={mode!r})")

    assert not violations, violations


def test_cockpit_flags_are_read_only_no_mutation_surfaces() -> None:
    source = _source()

    for token in FORBIDDEN_TOGGLE_TOKENS:
        assert token not in source, token

    for node in ast.walk(_tree()):
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Subscript):
                    chain = _attr_chain(target.value)
                    assert "environ" not in chain, "env mutation detected"