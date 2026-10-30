"""Consume without conflating handler, claim storage and acknowledgement failures."""

from typing import Literal

from .claims import ClaimStore, OwnershipLost, validate_key
from .dispatch import Dispatcher
from .models import Event


class Consumer:
    def __init__(self, store: ClaimStore, dispatcher: Dispatcher, *, scope: str):
        validate_key(scope, "scope")
        self.store = store
        self.dispatcher = dispatcher
        self.scope = scope

    async def consume(self, event: Event) -> Literal["processed", "inflight", "completed"]:
        result = await self.store.claim(self.scope, event.event_id)
        if result.state != "acquired":
            return result.state
        claim = result.claim
        if claim is None:
            raise RuntimeError("Acquired claim missing owner token")
        try:
            await self.dispatcher.dispatch(event)
        except BaseException as original:
            try:
                released = await self.store.release(claim)
                if not released:
                    original.add_note("Claim release lost ownership")
            except BaseException as cleanup:
                original.add_note(f"Claim cleanup failed: {type(cleanup).__name__}: {cleanup}")
            raise
        if not await self.store.complete(claim):
            raise OwnershipLost("Handler finished after claim ownership was lost")
        return "processed"
