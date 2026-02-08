from __future__ import annotations
import logging


log = logging.getLogger(__name__)

from dataclasses import dataclass
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")


class Result(Generic[T, E]):
    """
    Result Monad estilo Ok/Err.

    Objetivo:
    - Nunca esconder errores en try/except silenciosos.
    - Forzar a que el caller maneje el éxito o el error explícitamente.

    Patrón:
        def algo() -> Result[int, str]:
            if ok:
                return Ok(42)
            return Err("motivo")

        r = algo()
        if r.is_ok():
log.debug('%s', r.value)
        else:
log.debug('%s', r.error)
    """

    def is_ok(self) -> bool:
        raise NotImplementedError

    def is_err(self) -> bool:
        raise NotImplementedError

    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        """
        Aplica fn(value) sólo si es Ok, propaga Err tal cual.
        """
        raise NotImplementedError

    def map_err(self, fn: Callable[[E], F]) -> Result[T, F]:
        """
        Transforma el error si es Err, deja Ok igual.
        """
        raise NotImplementedError

    def bind(self, fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """
        FlatMap / and_then: encadena operaciones que también devuelven Result.
        """
        raise NotImplementedError

    def unwrap_or(self, default: T) -> T:
        """
        Devuelve el valor si es Ok, en caso contrario regresa default.
        """
        raise NotImplementedError

    def unwrap_or_else(self, fn: Callable[[E], T]) -> T:
        """
        Devuelve el valor si es Ok, o fn(error) si es Err.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class Ok(Result[T, E]):
    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        return Ok(fn(self.value))

    def map_err(self, fn: Callable[[E], F]) -> Result[T, F]:
        # No hay error que transformar, se mantiene Ok
        return Ok(self.value)  # type: ignore[return-value]

    def bind(self, fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return fn(self.value)

    def unwrap_or(self, default: T) -> T:
        return self.value

    def unwrap_or_else(self, fn: Callable[[E], T]) -> T:
        return self.value


@dataclass(frozen=True)
class Err(Result[T, E]):
    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        # Propaga el error; no aplica fn
        return Err(self.error)  # type: ignore[return-value]

    def map_err(self, fn: Callable[[E], F]) -> Result[T, F]:
        return Err(fn(self.error))

    def bind(self, fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        # Propaga el error; no llama fn
        return Err(self.error)  # type: ignore[return-value]

    def unwrap_or(self, default: T) -> T:
        return default

    def unwrap_or_else(self, fn: Callable[[E], T]) -> T:
        return fn(self.error)


def ok(value: T) -> Result[T, Any]:
    """Helper rápido para crear Ok."""
    return Ok(value)


def err(error: E) -> Result[Any, E]:
    """Helper rápido para crear Err."""
    return Err(error)
