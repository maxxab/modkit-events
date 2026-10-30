"""Ordered async handler dispatch. Earlier side effects may repeat on retry."""

from collections.abc import Awaitable, Callable

from .models import Event

Handler = Callable[[Event], Awaitable[None]]


class Dispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    def subscribe(self, name: str, handler: Handler) -> None:
        if not isinstance(name, str) or not name.strip() or not callable(handler):
            raise ValueError("Expected nonempty event name and callable handler")
        self._handlers.setdefault(name, []).append(handler)

    async def dispatch(self, event: Event) -> None:
        handlers = tuple(self._handlers.get(event.name, ()))
        if not handlers:
            raise LookupError(f"No handler registered for {event.name}")
        for handler in handlers:
            await handler(event)
