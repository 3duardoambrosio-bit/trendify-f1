from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

_MAX_DEPTH = 12


@dataclass(frozen=True)
class ResolvedString:
    value: str
    lineno: int
    col_offset: int
    source_kind: str


@dataclass(frozen=True)
class NoGoFinding:
    token: str
    value: str
    lineno: int
    col_offset: int
    source_kind: str


def _norm_token(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def value_matches_token(value: str, token: str) -> bool:
    value_cf = value.casefold()
    token_cf = token.casefold()
    if token_cf in value_cf:
        return True
    norm_value = _norm_token(value)
    norm_token = _norm_token(token)
    return bool(norm_token and norm_token in norm_value)


def _node_pos(node: ast.AST) -> tuple[int, int]:
    return (getattr(node, "lineno", 0) or 0, getattr(node, "col_offset", 0) or 0)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


class _Resolver:
    def __init__(self) -> None:
        self.module_env: dict[str, str] = {}
        self.resolved: list[ResolvedString] = []

    def scan(self, tree: ast.AST) -> list[ResolvedString]:
        if isinstance(tree, ast.Module):
            self._scan_body(tree.body, dict(self.module_env), module_level=True)
        else:
            self._scan_node(tree, dict(self.module_env))
        return self.resolved

    def _scan_body(self, body: list[ast.stmt], env: dict[str, str], *, module_level: bool = False) -> None:
        for stmt in body:
            if isinstance(stmt, ast.Assign):
                resolved = self._resolve_expr(stmt.value, env)
                if resolved is not None:
                    self._record(stmt.value, resolved, "assign")
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            env[target.id] = resolved
                            if module_level:
                                self.module_env[target.id] = resolved
                self._scan_node(stmt.value, env)
                continue

            if isinstance(stmt, ast.AnnAssign):
                if stmt.value is not None:
                    resolved = self._resolve_expr(stmt.value, env)
                    if resolved is not None:
                        self._record(stmt.value, resolved, "assign")
                        if isinstance(stmt.target, ast.Name):
                            env[stmt.target.id] = resolved
                            if module_level:
                                self.module_env[stmt.target.id] = resolved
                    self._scan_node(stmt.value, env)
                continue

            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self._scan_body(stmt.body, dict(self.module_env))
                continue

            self._scan_node(stmt, env)

    def _scan_node(self, node: ast.AST, env: dict[str, str]) -> None:
        resolved = self._resolve_expr(node, env)
        if resolved is not None:
            self._record(node, resolved, type(node).__name__)

        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._scan_body(child.body, dict(self.module_env))
                else:
                    self._scan_body(child.body, dict(self.module_env))
                continue
            self._scan_node(child, env)

    def _record(self, node: ast.AST, value: str, source_kind: str) -> None:
        if not value:
            return
        lineno, col = _node_pos(node)
        self.resolved.append(
            ResolvedString(
                value=value,
                lineno=lineno,
                col_offset=col,
                source_kind=source_kind,
            )
        )

    def _resolve_expr(self, node: ast.AST, env: Mapping[str, str], *, depth: int = 0) -> str | None:
        if depth > _MAX_DEPTH:
            return None

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value

        if isinstance(node, ast.Name):
            return env.get(node.id) or self.module_env.get(node.id)

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._resolve_expr(node.left, env, depth=depth + 1)
            right = self._resolve_expr(node.right, env, depth=depth + 1)
            if left is not None and right is not None:
                return left + right
            return None

        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                    continue
                if isinstance(value, ast.FormattedValue):
                    resolved = self._resolve_expr(value.value, env, depth=depth + 1)
                    if resolved is None:
                        return None
                    parts.append(resolved)
                    continue
                return None
            return "".join(parts)

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "join" and len(node.args) == 1 and not node.keywords:
                separator = self._resolve_expr(node.func.value, env, depth=depth + 1)
                if separator is None:
                    return None
                arg = node.args[0]
                if isinstance(arg, (ast.List, ast.Tuple)):
                    pieces: list[str] = []
                    for elt in arg.elts:
                        resolved = self._resolve_expr(elt, env, depth=depth + 1)
                        if resolved is None:
                            return None
                        pieces.append(resolved)
                    return separator.join(pieces)

        return None


def _clean_source_for_ast(source: str) -> str:
    # Some legacy files may contain UTF BOM or mojibake BOM artifacts.
    # The no-go scanner must not crash on these while walking the repo.
    return (
        source
        .lstrip("\ufeff")
        .removeprefix("ï»¿")
        .removeprefix("´╗┐")
    )


def iter_resolved_strings(source: str) -> list[ResolvedString]:
    tree = ast.parse(_clean_source_for_ast(source))
    return _Resolver().scan(tree)


def scan_source_for_forbidden_strings(source: str, tokens: Iterable[str]) -> list[NoGoFinding]:
    token_tuple = tuple(tokens)
    findings: list[NoGoFinding] = []
    for resolved in iter_resolved_strings(source):
        for token in token_tuple:
            if value_matches_token(resolved.value, token):
                findings.append(
                    NoGoFinding(
                        token=token,
                        value=resolved.value,
                        lineno=resolved.lineno,
                        col_offset=resolved.col_offset,
                        source_kind=resolved.source_kind,
                    )
                )
    return findings


def scan_path_for_forbidden_strings(path: str | Path, tokens: Iterable[str]) -> list[NoGoFinding]:
    source = Path(path).read_text(encoding="utf-8", errors="ignore")
    return scan_source_for_forbidden_strings(source, tokens)


def has_call_to(source: str, function_name: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func).endswith(function_name):
            return True
    return False
