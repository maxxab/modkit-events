"""Minimal broker-neutral publishing contract."""

from typing import Protocol

from .models import Event


class Publisher(Protocol):
    async def publish(self, event: Event) -> str: ...
