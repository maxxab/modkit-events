"""Immutable managed manifests; names filter intake, exact pairs define capability."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from .contracts import ContractRegistry, _identifier, _version
from .models import Event


class StartPosition(Enum):
    BEGINNING = "beginning"
    LATEST = "latest"


class InvalidSubscriptionConfiguration(ValueError):
    pass


class DuplicateSubscriptionError(ValueError):
    pass


class ConflictingConsumerGroupError(ValueError):
    pass


class UnsupportedCapabilityError(ValueError):
    pass


@dataclass(frozen=True, slots=True, init=False)
class Subscription:
    subscription_id: str
    group: str
    route: str
    event_names: frozenset[str]
    start_position: StartPosition

    def __init__(
        self,
        *,
        subscription_id: str,
        group: str,
        route: str,
        event_names: Iterable[str],
        start_position: StartPosition = StartPosition.BEGINNING,
    ) -> None:
        if not all(_identifier(value) for value in (subscription_id, group, route)):
            raise InvalidSubscriptionConfiguration("Invalid subscription identifiers")
        if not isinstance(start_position, StartPosition):
            raise InvalidSubscriptionConfiguration("Invalid subscription start position")
        # A string is not a manifest of single-character names.
        if isinstance(event_names, (str, bytes)):
            raise InvalidSubscriptionConfiguration("Expected event name collection")
        names: set[str] = set()
        for index, name in enumerate(event_names):
            if index >= 1024 or not _identifier(name):
                raise InvalidSubscriptionConfiguration("Invalid or excessive event filters")
            if name in names:
                raise InvalidSubscriptionConfiguration("Duplicate event filter")
            names.add(name)
        if not names:
            raise InvalidSubscriptionConfiguration("Event filter must not be empty")
        object.__setattr__(self, "subscription_id", subscription_id)
        object.__setattr__(self, "group", group)
        object.__setattr__(self, "route", route)
        object.__setattr__(self, "event_names", frozenset(names))
        object.__setattr__(self, "start_position", start_position)

    def matches(self, event: Event) -> bool:
        if not isinstance(event, Event):
            raise InvalidSubscriptionConfiguration("Expected Event")
        return event.name in self.event_names

    def validate(
        self,
        registry: ContractRegistry,
        *,
        handler_capabilities: Iterable[tuple[str, int]],
    ) -> None:
        if not isinstance(registry, ContractRegistry):
            raise UnsupportedCapabilityError("Expected ContractRegistry")
        pairs: set[tuple[str, int]] = set()
        names: set[str] = set()
        available = registry.capabilities()
        for index, pair in enumerate(handler_capabilities):
            if index >= 4096 or type(pair) is not tuple or len(pair) != 2:
                raise UnsupportedCapabilityError("Invalid or excessive handler capabilities")
            name, version = pair
            if not _identifier(name) or not _version(version):
                raise UnsupportedCapabilityError("Invalid handler capability")
            if pair in pairs or name not in self.event_names or pair not in available:
                raise UnsupportedCapabilityError("Duplicate or unsupported handler capability")
            if registry.route_for(name) != self.route:
                raise UnsupportedCapabilityError("Handler capability route mismatch")
            pairs.add(pair)
            names.add(name)
        if names != self.event_names:
            raise UnsupportedCapabilityError("Every subscribed name requires a handler capability")


def validate_subscriptions(subscriptions: Iterable[Subscription]) -> tuple[Subscription, ...]:
    result: list[Subscription] = []
    identities: set[str] = set()
    groups: set[tuple[str, str]] = set()
    for index, subscription in enumerate(subscriptions):
        if index >= 4096 or not isinstance(subscription, Subscription):
            raise InvalidSubscriptionConfiguration("Invalid or excessive subscriptions")
        if subscription.subscription_id in identities:
            raise DuplicateSubscriptionError("Duplicate subscription identity")
        group = (subscription.route, subscription.group)
        if group in groups:
            raise ConflictingConsumerGroupError("Subscriptions share a route and group")
        identities.add(subscription.subscription_id)
        groups.add(group)
        result.append(subscription)
    return tuple(result)
