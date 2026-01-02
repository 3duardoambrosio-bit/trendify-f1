from __future__ import annotations

import inspect
from types import ModuleType
from typing import Any, Callable


_CANDIDATES = (
    # Programmatic (kwargs-friendly)
    "run",
    "run_wave",
    "execute",
    "entrypoint",
    "entry",
    # CLI-ish
    "cli_main",
    "cli",
    "main",
)


def _callable_accepts_kwargs(fn: Callable[..., Any], kwargs: dict[str, Any]) -> bool:
    if not kwargs:
        return False
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False

    params = sig.parameters
    has_varkw = any(p.kind == p.VAR_KEYWORD for p in params.values())
    if has_varkw:
        return True
    return all(k in params for k in kwargs.keys())


def _call_callable(fn: Callable[..., Any], argv: list[str] | None = None, **kwargs: Any) -> int:
    try:
        sig = inspect.signature(fn)
        params = sig.parameters

        if kwargs and _callable_accepts_kwargs(fn, kwargs):
            out = fn(**kwargs)
            return _normalize_rc(out)

        if argv is not None:
            positional = [
                p for p in params.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
            has_var = any(p.kind == p.VAR_POSITIONAL for p in params.values())
            if has_var or len(positional) >= 1:
                try:
                    out = fn(argv)
                    return _normalize_rc(out)
                except TypeError:
                    pass

        out = fn()
        return _normalize_rc(out)

    except SystemExit as e:
        code = getattr(e, "code", 1)
        return int(code) if isinstance(code, int) else 1


def _normalize_rc(out: Any) -> int:
    if out is None:
        return 0
    if isinstance(out, bool):
        return 0 if out else 1
    if isinstance(out, int):
        return out
    return 0


def invoke_best(mod: ModuleType, argv: list[str] | None = None, **kwargs: Any) -> int:
    if kwargs:
        for name in _CANDIDATES:
            fn = getattr(mod, name, None)
            if callable(fn) and _callable_accepts_kwargs(fn, kwargs):
                return _call_callable(fn, argv=argv, **kwargs)

    for name in _CANDIDATES:
        fn = getattr(mod, name, None)
        if callable(fn):
            return _call_callable(fn, argv=argv, **kwargs)

    raise AttributeError(f"No known entrypoint found in module={mod.__name__}")


def invoke_module(modname: str, argv: list[str] | None = None, **kwargs: Any) -> int:
    import importlib

    mod = importlib.import_module(modname)
    return invoke_best(mod, argv=argv, **kwargs)
