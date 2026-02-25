# tools/l4_gate.py
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple


@dataclass(frozen=True, slots=True)
class Violation:
    level: str  # "RED" | "YELLOW"
    code: str
    message: str
    file: str
    line: int


@dataclass(frozen=True, slots=True)
class Report:
    status: str  # "GREEN" | "RED"
    files_checked: int
    red_violations: int
    yellow_violations: int
    violations: List[Violation]


def _read_text(p: Path) -> str:
    # Read raw text and strip UTF-8 BOM if present (ast.parse rejects U+FEFF at pos 0).
    s = p.read_text(encoding="utf-8")
    return s.lstrip("\ufeff")


def _parse(p: Path) -> ast.AST:
    return ast.parse(_read_text(p), filename=str(p))


def _is_public_name(name: str) -> bool:
    if name.startswith("_"):
        return False
    if name.startswith("__") and name.endswith("__"):
        return False
    return True


def _has_any_deal_contract(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in node.decorator_list:
        c = d if isinstance(d, ast.Call) else None
        f = c.func if c is not None else d
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "deal":
            if f.attr in {"pre", "post", "raises"}:
                return True
    return False


def _fn_len_ok(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Tuple[bool, int]:
    start = int(getattr(node, "lineno", 1))
    end = int(getattr(node, "end_lineno", start))
    length = int(end - start + 1)
    return (length <= 60), length


def _has_full_type_hints(node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool) -> bool:
    args = node.args
    all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    if args.vararg is not None:
        all_args.append(args.vararg)
    if args.kwarg is not None:
        all_args.append(args.kwarg)

    for idx, a in enumerate(all_args):
        if is_method and idx == 0 and a.arg in {"self", "cls"}:
            continue
        if a.annotation is None:
            return False
    return node.returns is not None


def _iter_public_callables(tree: ast.AST) -> List[Tuple[str, ast.AST, bool]]:
    out: List[Tuple[str, ast.AST, bool]] = []
    body = getattr(tree, "body", [])
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public_name(n.name):
            out.append((n.name, n, False))
        if isinstance(n, ast.ClassDef) and _is_public_name(n.name):
            for b in n.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public_name(b.name):
                    out.append((f"{n.name}.{b.name}", b, True))
    return out


class _FloatFinder(ast.NodeVisitor):
    def __init__(self) -> None:
        self.const_lines: List[int] = []
        self.call_lines: List[int] = []
        self.ann_lines: List[int] = []

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, float):
            self.const_lines.append(int(getattr(node, "lineno", 1)))

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "float":
            self.call_lines.append(int(getattr(node, "lineno", 1)))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.annotation, ast.Name) and node.annotation.id == "float":
            self.ann_lines.append(int(getattr(node, "lineno", 1)))
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        if isinstance(node.annotation, ast.Name) and node.annotation.id == "float":
            self.ann_lines.append(int(getattr(node, "lineno", 1)))


def _tests_path_for(py_file: Path) -> Path:
    stem = py_file.name.replace(".py", "")
    return Path("tests") / "p0" / f"test_{stem}_l4.py"


def _call_name(func: ast.AST) -> Optional[str]:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _TestCallIndex(ast.NodeVisitor):
    def __init__(self) -> None:
        self.unit: Set[str] = set()
        self.prop: Set[str] = set()
        self._in_test = False
        self._in_prop = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        prev_t, prev_p = self._in_test, self._in_prop
        self._in_test = node.name.startswith("test_")
        self._in_prop = self._has_given(node)
        self.generic_visit(node)
        self._in_test, self._in_prop = prev_t, prev_p

    def _has_given(self, node: ast.FunctionDef) -> bool:
        for d in node.decorator_list:
            c = d if isinstance(d, ast.Call) else None
            f = c.func if c is not None else d
            if isinstance(f, ast.Name) and f.id == "given":
                return True
        return False

    def visit_Call(self, node: ast.Call) -> None:
        if not self._in_test:
            self.generic_visit(node)
            return
        name = _call_name(node.func)
        if name is not None:
            if self._in_prop:
                self.prop.add(name)
            else:
                self.unit.add(name)
        self.generic_visit(node)


def _broad_except_lines(tree: ast.AST) -> List[int]:
    bad: List[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            t = node.type
            if t is None:
                bad.append(int(getattr(node, "lineno", 1)))
                continue
            if isinstance(t, ast.Name) and t.id == "Exception":
                bad.append(int(getattr(node, "lineno", 1)))
                continue
            if isinstance(t, ast.Attribute) and t.attr == "Exception":
                bad.append(int(getattr(node, "lineno", 1)))
    return bad


def _finalize(files: Sequence[Path], violations: List[Violation]) -> Report:
    reds = [v for v in violations if v.level == "RED"]
    yellows = [v for v in violations if v.level == "YELLOW"]
    status = "GREEN" if len(reds) == 0 else "RED"
    return Report(
        status=status,
        files_checked=len(files),
        red_violations=len(reds),
        yellow_violations=len(yellows),
        violations=violations,
    )


def _analyze_one(py_file: Path) -> Report:
    violations: List[Violation] = []

    if not py_file.exists():
        violations.append(Violation("RED", "FILE_MISSING", "target file missing", str(py_file), 1))
        return _finalize([py_file], violations)

    try:
        tree = _parse(py_file)
    except SyntaxError as e:
        violations.append(Violation("RED", "SYNTAX", "syntax error", str(py_file), int(e.lineno or 1)))
        return _finalize([py_file], violations)

    for ln in _broad_except_lines(tree):
        violations.append(Violation("RED", "NO_EXCEPT_EXCEPTION", "broad exception handler forbidden", str(py_file), ln))

    ff = _FloatFinder()
    ff.visit(tree)
    for ln in ff.const_lines:
        violations.append(Violation("RED", "NO_FLOAT_CONST", "float constant forbidden", str(py_file), ln))
    for ln in ff.call_lines:
        violations.append(Violation("RED", "NO_FLOAT_CALL", "float(...) forbidden", str(py_file), ln))
    for ln in ff.ann_lines:
        violations.append(Violation("RED", "NO_FLOAT_ANN", "float annotation forbidden", str(py_file), ln))

    public = _iter_public_callables(tree)
    for qname, node, is_method in public:
        fn = node
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ok_len, length = _fn_len_ok(fn)
            if not ok_len:
                violations.append(Violation("RED", "FN_TOO_LONG", f"{qname} length={length} > 60", str(py_file), int(fn.lineno)))
            if not _has_full_type_hints(fn, is_method=is_method):
                violations.append(Violation("RED", "TYPE_HINTS", f"{qname} missing type hints", str(py_file), int(fn.lineno)))
            if not _has_any_deal_contract(fn):
                violations.append(Violation("RED", "NO_DEAL", f"{qname} missing deal decorators", str(py_file), int(fn.lineno)))

    tpath = _tests_path_for(py_file)
    if not tpath.exists():
        violations.append(Violation("RED", "TEST_MISSING", f"missing {tpath}", str(py_file), 1))
        return _finalize([py_file], violations)

    try:
        ttree = _parse(tpath)
    except SyntaxError as e:
        violations.append(Violation("RED", "TEST_SYNTAX", "test file syntax error", str(tpath), int(e.lineno or 1)))
        return _finalize([py_file], violations)

    idx = _TestCallIndex()
    idx.visit(ttree)

    need_names: Set[str] = set()
    for qname, _node, _is_method in public:
        need_names.add(qname.split(".", 1)[1] if "." in qname else qname)

    missing_unit = sorted([n for n in need_names if n not in idx.unit and n not in idx.prop])
    missing_prop = sorted([n for n in need_names if n not in idx.prop])

    for n in missing_unit:
        violations.append(Violation("RED", "UNIT_MISSING", f"missing unit coverage for {n}", str(tpath), 1))
    for n in missing_prop:
        violations.append(Violation("RED", "HYPOTHESIS_MISSING", f"missing hypothesis coverage for {n}", str(tpath), 1))

    return _finalize([py_file], violations)


def _write_report(rep: Report, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(rep)
    payload["violations"] = [asdict(v) for v in rep.violations]
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _print_summary(rep: Report) -> None:
    print(f"status={rep.status}")
    print(f"files_checked={rep.files_checked}")
    print(f"red_violations={rep.red_violations}")
    print(f"yellow_violations={rep.yellow_violations}")
    print(f"L4_GATE_OK={1 if rep.status == 'GREEN' else 0}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=str, default="")
    ap.add_argument("--report", action="store_true")
    ns = ap.parse_args(argv)

    if not ns.file:
        print("status=RED")
        print("L4_GATE_OK=0")
        return 2

    rep = _analyze_one(Path(ns.file))
    if ns.report:
        _write_report(rep, Path("out") / "l4_gate_report.json")
    _print_summary(rep)
    return 0 if rep.status == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
