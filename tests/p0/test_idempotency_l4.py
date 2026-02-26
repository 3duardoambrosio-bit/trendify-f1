from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from hypothesis import given, strategies as st

from infra.idempotency import IdempotencyGuard


def test_execute_once_runs_operation() -> None:
    """Primera ejecución con key nuevo  ejecuta y retorna COMPLETED."""
    with TemporaryDirectory() as td:
        db = str(Path(td) / "idem.db")
        guard = IdempotencyGuard(db_path=db)
        called = {"n": 0}

        def op() -> Any:
            called["n"] += 1
            return {"spent": "10.00"}

        r = guard.execute_once("spend-meta-001", op)
        assert called["n"] == 1
        assert r.was_cached is False
        assert r.status == "COMPLETED"


def test_execute_once_twice_returns_cached() -> None:
    """Segunda ejecución con mismo key  NO ejecuta, retorna DUPLICATE."""
    with TemporaryDirectory() as td:
        db = str(Path(td) / "idem.db")
        guard = IdempotencyGuard(db_path=db)
        called = {"n": 0}

        def op() -> Any:
            called["n"] += 1
            return {"spent": "10.00"}

        r1 = guard.execute_once("spend-meta-001", op)
        r2 = guard.execute_once("spend-meta-001", op)

        assert called["n"] == 1
        assert r1.was_cached is False
        assert r2.was_cached is True
        assert r2.status == "DUPLICATE"


def test_failed_operation_allows_retry() -> None:
    """Si operation lanza excepción, el key queda FAILED y se puede reintentar."""
    with TemporaryDirectory() as td:
        db = str(Path(td) / "idem.db")
        guard = IdempotencyGuard(db_path=db)
        attempt = {"n": 0}

        def flaky_op() -> Any:
            attempt["n"] += 1
            if attempt["n"] == 1:
                raise ConnectionError("Meta API down")
            return {"spent": "10.00"}

        try:
            guard.execute_once("spend-meta-002", flaky_op)
        except ConnectionError:
            pass

        r = guard.execute_once("spend-meta-002", flaky_op)
        assert r.was_cached is False
        assert r.status == "COMPLETED"
        assert attempt["n"] == 2


def test_different_keys_both_execute() -> None:
    """Keys diferentes  ambos ejecutan."""
    with TemporaryDirectory() as td:
        db = str(Path(td) / "idem.db")
        guard = IdempotencyGuard(db_path=db)
        called = {"a": 0, "b": 0}

        def op_a() -> Any:
            called["a"] += 1
            return "A"

        def op_b() -> Any:
            called["b"] += 1
            return "B"

        guard.execute_once("k-a", op_a)
        guard.execute_once("k-b", op_b)
        assert called["a"] == 1
        assert called["b"] == 1


@given(st.lists(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))), min_size=1, max_size=20))
def test_idempotency_hypothesis_no_double_execution(keys: list[str]) -> None:
    """Hypothesis: ejecutar N keys, cada uno 2 veces  cada operación corre exactamente 1 vez."""
    with TemporaryDirectory() as td:
        db = str(Path(td) / "idem.db")
        guard = IdempotencyGuard(db_path=db)
        counts: dict[str, int] = {}

        for key in keys:
            def op(k: str = key) -> Any:
                counts[k] = counts.get(k, 0) + 1
                return f"result-{k}"

            guard.execute_once(key, op)
            guard.execute_once(key, op)

        for key in set(keys):
            assert counts.get(key, 0) == 1, f"key '{key}' executed {counts.get(key, 0)} times"

# --- L4 coverage add-ons: is_completed + clear (unit + hypothesis) ---

def test_is_completed_and_clear_unit() -> None:
    """Unit: execute_once -> is_completed True; clear -> is_completed False; re-exec runs again."""
    with TemporaryDirectory() as td:
        db = str(Path(td) / "idem.db")
        guard = IdempotencyGuard(db_path=db)
        called = {"n": 0}

        def op() -> Any:
            called["n"] += 1
            return {"spent": "10.00"}

        r1 = guard.execute_once("iscomp-001", op)
        assert r1.status == "COMPLETED"
        assert guard.is_completed("iscomp-001") is True

        guard.clear("iscomp-001")
        assert guard.is_completed("iscomp-001") is False

        r2 = guard.execute_once("iscomp-001", op)
        assert r2.was_cached is False
        assert r2.status == "COMPLETED"
        assert called["n"] == 2


KEY = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L", "N")),
)

@given(KEY)
def test_is_completed_and_clear_hypothesis(key: str) -> None:
    """Hypothesis: is_completed + clear are called under @given (prop coverage)."""
    with TemporaryDirectory() as td:
        db = str(Path(td) / "idem.db")
        guard = IdempotencyGuard(db_path=db)

        def op() -> Any:
            return {"k": key}

        guard.execute_once(key, op)
        assert guard.is_completed(key) is True
        guard.clear(key)
        assert guard.is_completed(key) is False
