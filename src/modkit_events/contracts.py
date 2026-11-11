"""Additive, dependency-free event schemas; no persistence or execution authority."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, cast

from .models import Event


class PayloadValidator(Protocol):
    def validate(self, payload: Mapping[str, object]) -> None: ...


class PayloadValidationError(ValueError):
    def __init__(self) -> None:
        super().__init__("Payload does not satisfy event contract")


class InvalidValidatorResult(TypeError):
    pass


class DuplicateContractError(ValueError):
    pass


class ConflictingRouteError(ValueError):
    pass


class UnknownEventName(LookupError):
    pass


class UnsupportedSchemaVersion(LookupError):
    pass


class InvalidContractConfiguration(ValueError):
    pass


def _is_async_callable(value: object) -> bool:
    """Inspect entrypoints without calling them or rereading user descriptors."""
    if inspect.iscoroutinefunction(value) or inspect.isasyncgenfunction(value):
        return True
    call = getattr(type(value), "__call__", None)
    return inspect.iscoroutinefunction(call) or inspect.isasyncgenfunction(call)


def _close_created_coroutine(result: object) -> None:
    # Never touch foreign awaitable protocols or caller-owned started coroutines.
    if inspect.iscoroutine(result) and inspect.getcoroutinestate(result) == inspect.CORO_CREATED:
        result.close()


def _identifier(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        return False
    try:
        return len(value.encode("utf-8")) <= 256
    except UnicodeError:
        return False


def _version(value: object) -> bool:
    return type(value) is int and value >= 1


@dataclass(frozen=True, slots=True, kw_only=True)
class EventContract:
    name: str
    schema_version: int
    route: str
    validator: PayloadValidator

    def __post_init__(self) -> None:
        if (
            not _identifier(self.name)
            or not _identifier(self.route)
            or not _version(self.schema_version)
        ):
            raise InvalidContractConfiguration("Invalid event contract configuration")
        method = getattr(self.validator, "validate", None)
        if not callable(method) or _is_async_callable(method):
            raise InvalidContractConfiguration("Expected synchronous payload validator")


@dataclass(frozen=True, slots=True, init=False)
class ContractRegistry:
    _contracts: tuple[EventContract, ...]
    _by_key: Mapping[tuple[str, int], EventContract]
    _routes: Mapping[str, str]

    def __init__(self, contracts: Iterable[EventContract]) -> None:
        ordered: list[EventContract] = []
        by_key: dict[tuple[str, int], EventContract] = {}
        routes: dict[str, str] = {}
        for index, contract in enumerate(contracts):
            if index >= 4096 or not isinstance(contract, EventContract):
                raise InvalidContractConfiguration("Invalid or excessive contract registrations")
            key = (contract.name, contract.schema_version)
            if key in by_key:
                raise DuplicateContractError("Duplicate event contract registration")
            if contract.name in routes and routes[contract.name] != contract.route:
                raise ConflictingRouteError("Event name has conflicting routes")
            ordered.append(contract)
            by_key[key] = contract
            routes[contract.name] = contract.route
        object.__setattr__(self, "_contracts", tuple(ordered))
        object.__setattr__(self, "_by_key", MappingProxyType(by_key))
        object.__setattr__(self, "_routes", MappingProxyType(routes))

    def get(self, name: str, schema_version: int) -> EventContract:
        if not _identifier(name) or not _version(schema_version):
            raise InvalidContractConfiguration("Invalid contract lookup")
        if name not in self._routes:
            raise UnknownEventName("Unknown event name")
        result = self._by_key.get((name, schema_version))
        if result is None:
            raise UnsupportedSchemaVersion("Unsupported event schema version")
        return result

    def route_for(self, name: str) -> str:
        if not _identifier(name):
            raise InvalidContractConfiguration("Invalid route lookup")
        result = self._routes.get(name)
        if result is None:
            raise UnknownEventName("Unknown event name")
        return result

    def validate(self, event: Event) -> None:
        if not isinstance(event, Event):
            raise InvalidContractConfiguration("Expected Event")
        # Runtime-check the application boundary even when its static protocol says None.
        validate = cast(
            Callable[[Mapping[str, object]], object],
            self.get(event.name, event.schema_version).validator.validate,
        )
        result = validate(event.payload)
        if result is not None:
            # Only an unstarted native coroutine is safe for warning cleanup.
            # Started/running/closed and foreign awaitables remain caller-owned.
            _close_created_coroutine(result)
            raise InvalidValidatorResult("Payload validator must return None")

    def capabilities(self) -> frozenset[tuple[str, int]]:
        return frozenset(self._by_key)

    def contracts(self) -> tuple[EventContract, ...]:
        return self._contracts
