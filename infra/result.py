from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar, cast

import deal

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
    """

    @deal.pre(lambda self: True, message="Result.is_ok contract")
    @deal.post(lambda result: isinstance(result, bool), message="Result.is_ok must return bool")
    @deal.raises(NotImplementedError)
    def is_ok(self: Result[T, E]) -> bool:
        raise NotImplementedError

    @deal.pre(lambda self: True, message="Result.is_err contract")
    @deal.post(lambda result: isinstance(result, bool), message="Result.is_err must return bool")
    @deal.raises(NotImplementedError)
    def is_err(self: Result[T, E]) -> bool:
        raise NotImplementedError

    @deal.pre(lambda self, fn: callable(fn), message="Result.map fn must be callable")
    @deal.post(lambda result: isinstance(result, Result), message="Result.map must return Result")
    @deal.raises(NotImplementedError)
    def map(self: Result[T, E], fn: Callable[[T], U]) -> Result[U, E]:
        """Aplica fn(value) sólo si es Ok, propaga Err tal cual."""
        raise NotImplementedError

    @deal.pre(lambda self, fn: callable(fn), message="Result.map_err fn must be callable")
    @deal.post(lambda result: isinstance(result, Result), message="Result.map_err must return Result")
    @deal.raises(NotImplementedError)
    def map_err(self: Result[T, E], fn: Callable[[E], F]) -> Result[T, F]:
        """Transforma el error si es Err, deja Ok igual."""
        raise NotImplementedError

    @deal.pre(lambda self, fn: callable(fn), message="Result.bind fn must be callable")
    @deal.post(lambda result: isinstance(result, Result), message="Result.bind must return Result")
    @deal.raises(NotImplementedError)
    def bind(self: Result[T, E], fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """FlatMap / and_then: encadena operaciones que también devuelven Result."""
        raise NotImplementedError

    @deal.pre(lambda self, default: True, message="Result.unwrap_or contract")
    @deal.post(lambda result: True, message="Result.unwrap_or post")
    @deal.raises(NotImplementedError)
    def unwrap_or(self: Result[T, E], default: T) -> T:
        """Devuelve el valor si es Ok, en caso contrario regresa default."""
        raise NotImplementedError

    @deal.pre(lambda self, fn: callable(fn), message="Result.unwrap_or_else fn must be callable")
    @deal.post(lambda result: True, message="Result.unwrap_or_else post")
    @deal.raises(NotImplementedError)
    def unwrap_or_else(self: Result[T, E], fn: Callable[[E], T]) -> T:
        """Devuelve el valor si es Ok, o fn(error) si es Err."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class Ok(Result[T, E]):
    value: T

    @deal.pre(lambda self: True, message="Ok.is_ok contract")
    @deal.post(lambda result: result is True, message="Ok.is_ok must be True")
    @deal.raises(deal.RaisesContractError)
    def is_ok(self: Ok[T, E]) -> bool:
        return True

    @deal.pre(lambda self: True, message="Ok.is_err contract")
    @deal.post(lambda result: result is False, message="Ok.is_err must be False")
    @deal.raises(deal.RaisesContractError)
    def is_err(self: Ok[T, E]) -> bool:
        return False

    @deal.pre(lambda self, fn: callable(fn), message="Ok.map fn must be callable")
    @deal.post(lambda result: isinstance(result, Result), message="Ok.map must return Result")
    @deal.raises(deal.RaisesContractError)
    def map(self: Ok[T, E], fn: Callable[[T], U]) -> Result[U, E]:
        return Ok(fn(self.value))

    @deal.pre(lambda self, fn: callable(fn), message="Ok.map_err fn must be callable")
    @deal.post(lambda result: isinstance(result, Result), message="Ok.map_err must return Result")
    @deal.raises(deal.RaisesContractError)
    def map_err(self: Ok[T, E], fn: Callable[[E], F]) -> Result[T, F]:
        _ = fn
        return cast(Result[T, F], Ok(self.value))

    @deal.pre(lambda self, fn: callable(fn), message="Ok.bind fn must be callable")
    @deal.post(lambda result: isinstance(result, Result), message="Ok.bind must return Result")
    @deal.raises(deal.RaisesContractError)
    def bind(self: Ok[T, E], fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return fn(self.value)

    @deal.pre(lambda self, default: True, message="Ok.unwrap_or contract")
    @deal.post(lambda result: True, message="Ok.unwrap_or post")
    @deal.raises(deal.RaisesContractError)
    def unwrap_or(self: Ok[T, E], default: T) -> T:
        _ = default
        return self.value

    @deal.pre(lambda self, fn: callable(fn), message="Ok.unwrap_or_else fn must be callable")
    @deal.post(lambda result: True, message="Ok.unwrap_or_else post")
    @deal.raises(deal.RaisesContractError)
    def unwrap_or_else(self: Ok[T, E], fn: Callable[[E], T]) -> T:
        _ = fn
        return self.value


@dataclass(frozen=True, slots=True)
class Err(Result[T, E]):
    error: E

    @deal.pre(lambda self: True, message="Err.is_ok contract")
    @deal.post(lambda result: result is False, message="Err.is_ok must be False")
    @deal.raises(deal.RaisesContractError)
    def is_ok(self: Err[T, E]) -> bool:
        return False

    @deal.pre(lambda self: True, message="Err.is_err contract")
    @deal.post(lambda result: result is True, message="Err.is_err must be True")
    @deal.raises(deal.RaisesContractError)
    def is_err(self: Err[T, E]) -> bool:
        return True

    @deal.pre(lambda self, fn: callable(fn), message="Err.map fn must be callable")
    @deal.post(lambda result: isinstance(result, Result), message="Err.map must return Result")
    @deal.raises(deal.RaisesContractError)
    def map(self: Err[T, E], fn: Callable[[T], U]) -> Result[U, E]:
        _ = fn
        return cast(Result[U, E], Err(self.error))

    @deal.pre(lambda self, fn: callable(fn), message="Err.map_err fn must be callable")
    @deal.post(lambda result: isinstance(result, Result), message="Err.map_err must return Result")
    @deal.raises(deal.RaisesContractError)
    def map_err(self: Err[T, E], fn: Callable[[E], F]) -> Result[T, F]:
        return Err(fn(self.error))

    @deal.pre(lambda self, fn: callable(fn), message="Err.bind fn must be callable")
    @deal.post(lambda result: isinstance(result, Result), message="Err.bind must return Result")
    @deal.raises(deal.RaisesContractError)
    def bind(self: Err[T, E], fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        _ = fn
        return cast(Result[U, E], Err(self.error))

    @deal.pre(lambda self, default: True, message="Err.unwrap_or contract")
    @deal.post(lambda result: True, message="Err.unwrap_or post")
    @deal.raises(deal.RaisesContractError)
    def unwrap_or(self: Err[T, E], default: T) -> T:
        return default

    @deal.pre(lambda self, fn: callable(fn), message="Err.unwrap_or_else fn must be callable")
    @deal.post(lambda result: True, message="Err.unwrap_or_else post")
    @deal.raises(deal.RaisesContractError)
    def unwrap_or_else(self: Err[T, E], fn: Callable[[E], T]) -> T:
        return fn(self.error)


@deal.pre(lambda value: True, message="ok(value) contract")
@deal.post(lambda result: isinstance(result, Result), message="ok(value) must return Result")
@deal.raises(deal.RaisesContractError)
def ok(value: T) -> Result[T, Any]:
    """Helper rápido para crear Ok."""
    return Ok(value)


@deal.pre(lambda error: True, message="err(error) contract")
@deal.post(lambda result: isinstance(result, Result), message="err(error) must return Result")
@deal.raises(deal.RaisesContractError)
def err(error: E) -> Result[Any, E]:
    """Helper rápido para crear Err."""
    return Err(error)