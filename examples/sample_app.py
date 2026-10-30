"""An unrelated greenhouse application; no web framework or optional dependencies."""

import asyncio

from modkit_events import Consumer, Dispatcher, Event, JsonCodec, MemoryClaimStore


async def main():
    readings = []

    async def record(event):
        readings.append(event.payload["temperature"])

    dispatcher = Dispatcher()
    dispatcher.subscribe("greenhouse.reading", record)
    consumer = Consumer(MemoryClaimStore(), dispatcher, scope="greenhouse-storage")
    event = Event("reading-42", "greenhouse.reading", {"temperature": 21.5})
    event = JsonCodec().decode(JsonCodec().encode(event))
    assert await consumer.consume(event) == "processed"
    assert await consumer.consume(event) == "completed"
    assert readings == [21.5]
    print("Greenhouse event delivered; duplicate suppressed")


if __name__ == "__main__":
    asyncio.run(main())
