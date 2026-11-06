"""Synchronous public contract controls; no optional packages or resources."""

import asyncio
import inspect
import sys
import unittest

from modkit_events.contracts import (
    ConflictingRouteError,
    ContractRegistry,
    DuplicateContractError,
    EventContract,
    InvalidContractConfiguration,
    InvalidValidatorResult,
    PayloadValidationError,
    UnknownEventName,
    UnsupportedSchemaVersion,
)
from modkit_events.models import Event


class Validator:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def validate(self, payload):
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        return self.result


def contract(name="event", version=1, route="stream", validator=None):
    return EventContract(
        name=name,
        schema_version=version,
        route=route,
        validator=validator if validator is not None else Validator(),
    )


class ContractTests(unittest.TestCase):
    def test_lookup_routes_duplicates(self):
        c = contract()
        registry = ContractRegistry([c, contract(version=3), contract(name="other")])
        self.assertIs(registry.get("event", 1), c)
        self.assertEqual(registry.route_for("event"), "stream")
        self.assertEqual(registry.contracts()[0], c)
        self.assertEqual(
            registry.capabilities(), frozenset({("event", 1), ("event", 3), ("other", 1)})
        )
        with self.assertRaises(UnknownEventName):
            registry.get("absent", 1)
        with self.assertRaises(UnknownEventName):
            registry.route_for("absent")
        with self.assertRaises(UnsupportedSchemaVersion):
            registry.get("event", 2)
        for repeated in (c, contract()):
            with self.assertRaises(DuplicateContractError):
                ContractRegistry([c, repeated])
        with self.assertRaises(ConflictingRouteError):
            ContractRegistry([c, contract(version=2, route="elsewhere")])
        self.assertEqual(c.validator.calls, [])

    def test_logical_versions_no_serialization(self):
        setting = sys.get_int_max_str_digits()
        for version in (2147483647, 2147483648, 2**13600 - 1, 2**20000):
            c = contract(version=version)
            event = Event("id", "event", {}, version)
            registry = ContractRegistry([c])
            self.assertEqual(registry.get("event", version).schema_version, version)
            self.assertIs(type(event.schema_version), int)
            registry.validate(event)
            self.assertIn(("event", version), registry.capabilities())
        self.assertEqual(setting, sys.get_int_max_str_digits())
        for version in (True, False, 1.0, "1", 0, -1):
            with self.assertRaises(InvalidContractConfiguration):
                contract(version=version)
            with self.assertRaises(InvalidContractConfiguration):
                ContractRegistry([]).get("event", version)

    def test_validator_outcomes(self):
        event = Event("id", "event", {"nested": [1]})
        good = Validator()
        ContractRegistry([contract(validator=good)]).validate(event)
        self.assertIs(good.calls[0], event.payload)
        for value in (False, True, 0, {}, object()):
            with self.assertRaises(InvalidValidatorResult):
                ContractRegistry([contract(validator=Validator(value))]).validate(event)
        for error in (
            PayloadValidationError(),
            RuntimeError("bug"),
            asyncio.CancelledError(),
            SystemExit(),
            KeyboardInterrupt(),
        ):
            try:
                ContractRegistry([contract(validator=Validator(error=error))]).validate(event)
            except BaseException as actual:
                self.assertIs(actual, error)
            else:
                self.fail("exception not propagated")
        with self.assertRaises(InvalidContractConfiguration):
            ContractRegistry([]).validate({})

    def test_async_rejected_without_execution(self):
        effects = []

        class AsyncValidator:
            async def validate(self, payload):
                effects.append("body")

        with self.assertRaises(InvalidContractConfiguration):
            contract(validator=AsyncValidator())

        async def body():
            effects.append("body")

        native = body()
        with self.assertRaises(InvalidValidatorResult):
            ContractRegistry([contract(validator=Validator(native))]).validate(
                Event("id", "event", {})
            )
        self.assertIsNone(native.cr_frame)

        class Awaitable:
            def __await__(self):
                effects.append("await")
                yield

            def close(self):
                effects.append("close")

            def cancel(self):
                effects.append("cancel")

        with self.assertRaises(InvalidValidatorResult):
            ContractRegistry([contract(validator=Validator(Awaitable()))]).validate(
                Event("id", "event", {})
            )
        self.assertEqual(effects, [])

    def test_suspended_coroutine_result_preserves_caller_lifecycle(self):
        # Explicitly authorized inert protocol stepping, not an async-runtime test.
        for raising in (False, True):
            with self.subTest(cleanup_raises=raising):
                token = object()
                effects = []
                phase = ["library_rejection"]
                cleanup_error = RuntimeError("test-owned cleanup")

                class Inert:
                    def __await__(self):
                        yield token

                async def body():
                    try:
                        await Inert()
                    finally:
                        effects.append(phase[0])
                        if raising:
                            raise cleanup_error

                native = body()
                self.assertIs(native.send(None), token)
                self.assertEqual(inspect.getcoroutinestate(native), inspect.CORO_SUSPENDED)
                try:
                    registry = ContractRegistry([contract(validator=Validator(native))])
                    with self.assertRaises(InvalidValidatorResult):
                        registry.validate(Event("id", "event", {}))
                    self.assertEqual(effects, [])
                    self.assertEqual(inspect.getcoroutinestate(native), inspect.CORO_SUSPENDED)
                finally:
                    # Only the test owner resumes lifecycle cleanup after the assertions.
                    phase[0] = "test_teardown"
                    if inspect.getcoroutinestate(native) != inspect.CORO_CLOSED:
                        if raising:
                            with self.assertRaises(RuntimeError) as caught:
                                native.close()
                            self.assertIs(caught.exception, cleanup_error)
                        else:
                            native.close()
                self.assertEqual(effects, ["test_teardown"])

    def test_snapshot_bounds_and_failure(self):
        source = [contract()]
        registry = ContractRegistry(source)
        source.clear()
        self.assertEqual(len(registry.contracts()), 1)
        with self.assertRaises(AttributeError):
            registry._contracts = ()
        with self.assertRaises(AttributeError):
            registry.contracts()[0].name = "changed"
        for name in ("", " ", "x" * 257, "x\0", "\ud800"):
            with self.assertRaises(InvalidContractConfiguration):
                contract(name=name)
        contract(name="é" * 128)
        with self.assertRaises(InvalidContractConfiguration):
            contract(name="é" * 129)
        contract(name=" event ")
        self.assertEqual(
            len(ContractRegistry(contract(version=i + 1) for i in range(4096)).contracts()), 4096
        )

        def excess():
            for i in range(4097):
                yield contract(version=i + 1)
            self.fail("read past excess")

        with self.assertRaises(InvalidContractConfiguration):
            ContractRegistry(excess())
        error = RuntimeError("iterator")

        def broken():
            yield contract()
            raise error

        try:
            ContractRegistry(broken())
        except RuntimeError as actual:
            self.assertIs(actual, error)
        else:
            self.fail("partial registry returned")
        for bad in (None, {}, object()):
            with self.assertRaises(InvalidContractConfiguration):
                ContractRegistry([bad])
        for validator in (None, object()):
            with self.assertRaises(InvalidContractConfiguration):
                EventContract(name="event", schema_version=1, route="stream", validator=validator)


class ValidatorBoundaryTests(unittest.TestCase):
    def test_detectable_async_entrypoints_rejected_without_execution(self):
        effects = []

        async def coroutine(payload):
            effects.append("coroutine")

        async def generator(payload):
            effects.append("generator")
            yield None

        class AsyncCall:
            async def __call__(self, payload):
                effects.append("async-call")

        class GeneratorCall:
            async def __call__(self, payload):
                effects.append("generator-call")
                yield None

        for entrypoint in (coroutine, generator, AsyncCall(), GeneratorCall()):
            with self.subTest(kind=type(entrypoint).__name__):

                class Configured:
                    validate = staticmethod(entrypoint)

                with self.assertRaises(InvalidContractConfiguration):
                    contract(validator=Configured())
        self.assertEqual(effects, [])

    def test_descriptor_read_once_and_original_failure(self):
        class Descriptor:
            reads = 0

            @property
            def validate(self):
                self.reads += 1
                return lambda payload: None

        validator = Descriptor()
        contract(validator=validator)
        self.assertEqual(validator.reads, 1)
        failure = RuntimeError("descriptor")

        class Broken:
            @property
            def validate(self):
                raise failure

        with self.assertRaises(RuntimeError) as caught:
            contract(validator=Broken())
        self.assertIs(caught.exception, failure)

    def test_disguised_generators_and_closed_coroutine_remain_unmodified(self):
        effects = []

        async def body():
            effects.append("body")
            try:
                yield None
            finally:
                effects.append("cleanup")

        generated = body()
        with self.assertRaises(InvalidValidatorResult):
            ContractRegistry([contract(validator=Validator(generated))]).validate(
                Event("id", "event", {})
            )
        self.assertIsNotNone(generated.ag_frame)
        self.assertEqual(effects, [])

        async def coroutine():
            effects.append("coroutine")

        closed = coroutine()
        closed.close()
        with self.assertRaises(InvalidValidatorResult):
            ContractRegistry([contract(validator=Validator(closed))]).validate(
                Event("id", "event", {})
            )
        self.assertEqual(effects, [])
