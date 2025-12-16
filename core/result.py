from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar, Union


T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")


@dataclass(frozen=True)
class Ok(Generic[T]):
    """
    Variante exitosa del Result Monad.

    Contiene un valor de tipo T y nunca un error.
    """
    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value

    def map(self, f: Callable[[T], U]) -> "Result[U, E]":
        return Ok(f(self.value))

    def flat_map(self, f: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        return f(self.value)


@dataclass(frozen=True)
class Err(Generic[E]):
    """
    Variante de error del Result Monad.

    Contiene un error de tipo E y ningún valor exitoso.
    """
    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> T:
        raise ValueError(f"Called unwrap() on Err: {self.error}")

    def unwrap_or(self, default: T) -> T:
        return default

    def map(self, f: Callable[[T], U]) -> "Result[U, E]":
        # map no aplica sobre Err; se devuelve tal cual
        return self  # type: ignore[return-value]

    def flat_map(self, f: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        # Igual que map: no se aplica f sobre Err.
        return self  # type: ignore[return-value]


Result = Union[Ok[T], Err[E]]
