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


@dataclass(frozen=True)
class ResolvedCall:
    canonical_name: str
    lineno: int
    col_offset: int
    source_kind: str


NETWORK_CALLABLE_NAMES = frozenset(
    {
        "urllib.request.urlopen",
        "requests.get",
        "requests.post",
        "requests.request",
        "httpx.get",
        "httpx.post",
        "httpx.request",
        "aiohttp.request",
    }
)


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


class _CallResolver:
    def __init__(self) -> None:
        self.resolved: list[ResolvedCall] = []
        self.module_env: dict[str, str | None] = {}

    def scan(self, tree: ast.AST) -> list[ResolvedCall]:
        if isinstance(tree, ast.Module):
            self.module_env = self._collect_module_env(tree.body)
            self._scan_body(tree.body, {}, scope="module")
        else:
            self._scan_node(tree, {})
        return self.resolved

    def _collect_module_env(
        self,
        body: list[ast.stmt],
    ) -> dict[str, str | None]:
        env: dict[str, str | None] = {}
        self._apply_module_bindings(body, env)
        return env

    def _apply_module_bindings(
        self,
        body: list[ast.stmt],
        env: dict[str, str | None],
    ) -> None:
        for stmt in body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.asname:
                        env[alias.asname] = alias.name
                    else:
                        root_name = alias.name.split(".", 1)[0]
                        env[root_name] = root_name
                continue

            if isinstance(stmt, ast.ImportFrom):
                if stmt.level:
                    continue
                module = stmt.module or ""
                for alias in stmt.names:
                    if alias.name == "*":
                        continue
                    local_name = alias.asname or alias.name
                    env[local_name] = (
                        f"{module}.{alias.name}" if module else alias.name
                    )
                continue

            if isinstance(stmt, ast.Assign):
                identity = self._resolve_identity(stmt.value, env)
                for target in stmt.targets:
                    self._bind_target(target, identity, env)
                continue

            if isinstance(stmt, ast.AnnAssign):
                identity = (
                    self._resolve_identity(stmt.value, env)
                    if stmt.value is not None
                    else None
                )
                self._bind_target(stmt.target, identity, env)
                continue

            if isinstance(stmt, ast.AugAssign):
                self._bind_target(stmt.target, None, env)
                continue

            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                env[stmt.name] = None
                continue

            if isinstance(stmt, ast.Delete):
                for target in stmt.targets:
                    self._bind_target(target, None, env)
                continue

            if isinstance(stmt, ast.If):
                truth = self._static_truth(stmt.test, env)
                if truth is True:
                    self._apply_module_bindings(stmt.body, env)
                elif truth is False:
                    self._apply_module_bindings(stmt.orelse, env)

    def _scan_body(
        self,
        body: list[ast.stmt],
        env: dict[str, str | None],
        *,
        scope: str,
    ) -> None:
        for stmt in body:
            self._scan_stmt(stmt, env, scope=scope)

    def _scan_stmt(
        self,
        stmt: ast.stmt,
        env: dict[str, str | None],
        *,
        scope: str,
    ) -> None:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.asname:
                    env[alias.asname] = alias.name
                else:
                    root_name = alias.name.split(".", 1)[0]
                    env[root_name] = root_name
            return

        if isinstance(stmt, ast.ImportFrom):
            if stmt.level:
                return
            module = stmt.module or ""
            for alias in stmt.names:
                if alias.name == "*":
                    continue
                local_name = alias.asname or alias.name
                env[local_name] = f"{module}.{alias.name}" if module else alias.name
            return

        if isinstance(stmt, ast.Assign):
            self._scan_node(stmt.value, env)
            identity = self._resolve_identity(stmt.value, env)
            for target in stmt.targets:
                self._bind_target(target, identity, env)
            return

        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is not None:
                self._scan_node(stmt.value, env)
                identity = self._resolve_identity(stmt.value, env)
            else:
                identity = None
            self._bind_target(stmt.target, identity, env)
            return

        if isinstance(stmt, ast.AugAssign):
            self._scan_node(stmt.target, env)
            self._scan_node(stmt.value, env)
            self._bind_target(stmt.target, None, env)
            return

        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in stmt.decorator_list:
                self._scan_node(decorator, env)
            for default in (*stmt.args.defaults, *stmt.args.kw_defaults):
                if default is not None:
                    self._scan_node(default, env)

            env[stmt.name] = None
            function_env = dict(
                self.module_env if scope in {"module", "class"} else env
            )
            for local_name in self._function_local_names(stmt.body):
                function_env[local_name] = None
            self._shadow_arguments(stmt.args, function_env)
            self._scan_body(stmt.body, function_env, scope="function")
            return

        if isinstance(stmt, ast.ClassDef):
            for decorator in stmt.decorator_list:
                self._scan_node(decorator, env)
            for base in stmt.bases:
                self._scan_node(base, env)
            for keyword in stmt.keywords:
                self._scan_node(keyword.value, env)

            env[stmt.name] = None
            self._scan_body(stmt.body, dict(env), scope="class")
            return

        if isinstance(stmt, ast.If):
            self._scan_node(stmt.test, env)
            truth = self._static_truth(stmt.test, env)
            if truth is True:
                self._scan_body(stmt.body, env, scope=scope)
            elif truth is False:
                self._scan_body(stmt.orelse, env, scope=scope)
            else:
                self._scan_body(stmt.body, dict(env), scope=scope)
                self._scan_body(stmt.orelse, dict(env), scope=scope)
            return

        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            body_env = dict(env)
            for item in stmt.items:
                self._scan_node(item.context_expr, env)
                if item.optional_vars is not None:
                    self._bind_target(item.optional_vars, None, body_env)
            self._scan_body(stmt.body, body_env, scope=scope)
            return

        if isinstance(stmt, (ast.For, ast.AsyncFor)):
            self._scan_node(stmt.iter, env)
            body_env = dict(env)
            self._bind_target(stmt.target, None, body_env)
            self._scan_body(stmt.body, body_env, scope=scope)
            self._scan_body(stmt.orelse, dict(env), scope=scope)
            return

        if isinstance(stmt, ast.While):
            self._scan_node(stmt.test, env)
            self._scan_body(stmt.body, dict(env), scope=scope)
            self._scan_body(stmt.orelse, dict(env), scope=scope)
            return

        try_nodes = (ast.Try, ast.TryStar) if hasattr(ast, "TryStar") else (ast.Try,)
        if isinstance(stmt, try_nodes):
            self._scan_body(stmt.body, dict(env), scope=scope)
            for handler in stmt.handlers:
                handler_env = dict(env)
                if handler.type is not None:
                    self._scan_node(handler.type, env)
                if handler.name:
                    handler_env[handler.name] = None
                self._scan_body(handler.body, handler_env, scope=scope)
            self._scan_body(stmt.orelse, dict(env), scope=scope)
            self._scan_body(stmt.finalbody, dict(env), scope=scope)
            return

        if isinstance(stmt, ast.Delete):
            for target in stmt.targets:
                self._bind_target(target, None, env)
            return

        self._scan_node(stmt, env)

    def _scan_node(self, node: ast.AST, env: dict[str, str | None]) -> None:
        if isinstance(node, ast.Lambda):
            lambda_env = dict(env)
            self._shadow_arguments(node.args, lambda_env)
            self._scan_node(node.body, lambda_env)
            return

        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            self._scan_comprehension(node.elt, node.generators, env)
            return

        if isinstance(node, ast.DictComp):
            comp_env = self._scan_generators(node.generators, env)
            self._scan_node(node.key, comp_env)
            self._scan_node(node.value, comp_env)
            return

        if isinstance(node, ast.NamedExpr):
            self._scan_node(node.value, env)
            self._bind_target(node.target, self._resolve_identity(node.value, env), env)
            return

        if isinstance(node, ast.Call):
            canonical_name = self._resolve_identity(node.func, env)
            if canonical_name:
                lineno, col = _node_pos(node)
                self.resolved.append(
                    ResolvedCall(
                        canonical_name=canonical_name,
                        lineno=lineno,
                        col_offset=col,
                        source_kind="call",
                    )
                )

        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                continue
            self._scan_node(child, env)

    def _scan_comprehension(
        self,
        element: ast.AST,
        generators: list[ast.comprehension],
        env: dict[str, str | None],
    ) -> None:
        comp_env = self._scan_generators(generators, env)
        self._scan_node(element, comp_env)

    def _scan_generators(
        self,
        generators: list[ast.comprehension],
        env: dict[str, str | None],
    ) -> dict[str, str | None]:
        comp_env = dict(env)
        for generator in generators:
            self._scan_node(generator.iter, comp_env)
            self._bind_target(generator.target, None, comp_env)
            for condition in generator.ifs:
                self._scan_node(condition, comp_env)
        return comp_env

    def _resolve_identity(
        self,
        node: ast.AST,
        env: Mapping[str, str | None],
        *,
        depth: int = 0,
    ) -> str | None:
        if depth > _MAX_DEPTH:
            return None

        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            if node.id in {"__import__", "getattr"}:
                return node.id
            return None

        if isinstance(node, ast.Attribute):
            base = self._resolve_identity(node.value, env, depth=depth + 1)
            return f"{base}.{node.attr}" if base else None

        if not isinstance(node, ast.Call):
            return None

        function_name = self._resolve_identity(node.func, env, depth=depth + 1)
        if function_name == "__import__":
            if not node.args:
                return None
            module_name = self._literal_string(node.args[0])
            if not module_name:
                return None
            fromlist = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "fromlist"),
                node.args[3] if len(node.args) > 3 else None,
            )
            if fromlist is None:
                return module_name.split(".", 1)[0]
            if isinstance(fromlist, (ast.List, ast.Tuple, ast.Set)):
                return module_name if fromlist.elts else module_name.split(".", 1)[0]
            return None

        if function_name == "importlib.import_module":
            if not node.args:
                return None
            module_name = self._literal_string(node.args[0])
            return module_name or None

        if function_name == "getattr" and len(node.args) >= 2:
            base = self._resolve_identity(node.args[0], env, depth=depth + 1)
            attribute = self._literal_string(node.args[1])
            if base and attribute:
                return f"{base}.{attribute}"

        return None

    def _static_truth(
        self,
        node: ast.AST,
        env: Mapping[str, str | None],
    ) -> bool | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            truth = self._static_truth(node.operand, env)
            return None if truth is None else not truth
        if self._resolve_identity(node, env) == "typing.TYPE_CHECKING":
            return False
        return None

    @staticmethod
    def _literal_string(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @classmethod
    def _function_local_names(cls, body: list[ast.stmt]) -> set[str]:
        bound: set[str] = set()
        declared_global: set[str] = set()
        declared_nonlocal: set[str] = set()

        def collect(statements: list[ast.stmt]) -> None:
            for stmt in statements:
                if isinstance(stmt, ast.Global):
                    declared_global.update(stmt.names)
                    continue
                if isinstance(stmt, ast.Nonlocal):
                    declared_nonlocal.update(stmt.names)
                    continue
                if isinstance(
                    stmt,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                ):
                    bound.add(stmt.name)
                    continue
                if isinstance(stmt, ast.Import):
                    for alias in stmt.names:
                        bound.add(alias.asname or alias.name.split(".", 1)[0])
                    continue
                if isinstance(stmt, ast.ImportFrom):
                    for alias in stmt.names:
                        if alias.name != "*":
                            bound.add(alias.asname or alias.name)
                    continue
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        bound.update(cls._target_names(target))
                    continue
                if isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
                    bound.update(cls._target_names(stmt.target))
                    continue
                if isinstance(stmt, ast.Delete):
                    for target in stmt.targets:
                        bound.update(cls._target_names(target))
                    continue
                if isinstance(stmt, (ast.For, ast.AsyncFor)):
                    bound.update(cls._target_names(stmt.target))
                    collect(stmt.body)
                    collect(stmt.orelse)
                    continue
                if isinstance(stmt, (ast.With, ast.AsyncWith)):
                    for item in stmt.items:
                        if item.optional_vars is not None:
                            bound.update(cls._target_names(item.optional_vars))
                    collect(stmt.body)
                    continue
                if isinstance(stmt, ast.If):
                    collect(stmt.body)
                    collect(stmt.orelse)
                    continue
                if isinstance(stmt, ast.While):
                    collect(stmt.body)
                    collect(stmt.orelse)
                    continue
                try_nodes = (
                    (ast.Try, ast.TryStar)
                    if hasattr(ast, "TryStar")
                    else (ast.Try,)
                )
                if isinstance(stmt, try_nodes):
                    collect(stmt.body)
                    for handler in stmt.handlers:
                        if handler.name:
                            bound.add(handler.name)
                        collect(handler.body)
                    collect(stmt.orelse)
                    collect(stmt.finalbody)

        collect(body)
        return bound - declared_global - declared_nonlocal

    @staticmethod
    def _target_names(target: ast.AST) -> set[str]:
        if isinstance(target, ast.Name):
            return {target.id}
        if isinstance(target, (ast.Tuple, ast.List)):
            names: set[str] = set()
            for element in target.elts:
                names.update(_CallResolver._target_names(element))
            return names
        if isinstance(target, ast.Starred):
            return _CallResolver._target_names(target.value)
        return set()

    @staticmethod
    def _bind_target(
        target: ast.AST,
        identity: str | None,
        env: dict[str, str | None],
    ) -> None:
        if isinstance(target, ast.Name):
            env[target.id] = identity
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                _CallResolver._bind_target(element, None, env)
            return
        if isinstance(target, ast.Starred):
            _CallResolver._bind_target(target.value, None, env)

    @staticmethod
    def _shadow_arguments(
        arguments: ast.arguments,
        env: dict[str, str | None],
    ) -> None:
        all_arguments = (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        )
        for argument in all_arguments:
            env[argument.arg] = None
        if arguments.vararg is not None:
            env[arguments.vararg.arg] = None
        if arguments.kwarg is not None:
            env[arguments.kwarg.arg] = None


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


def iter_resolved_calls(source: str) -> list[ResolvedCall]:
    tree = ast.parse(_clean_source_for_ast(source))
    return _CallResolver().scan(tree)


def scan_source_for_network_calls(source: str) -> list[ResolvedCall]:
    return [
        resolved
        for resolved in iter_resolved_calls(source)
        if resolved.canonical_name in NETWORK_CALLABLE_NAMES
    ]


def has_resolved_network_call(source: str) -> bool:
    return bool(scan_source_for_network_calls(source))


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
