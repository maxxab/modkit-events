"""Optional adapter boundaries against real Pydantic, never silently skipped."""

import asyncio
import importlib
import importlib.util
import inspect
from collections.abc import Mapping

import pytest
from pydantic import BaseModel, ConfigDict, field_validator

from modkit_events import Event
from modkit_events.contracts import (
    InvalidContractConfiguration,
    InvalidValidatorResult,
    PayloadValidationError,
)


def adapter(model):
    name = "modkit_events.adapters.pydantic"
    assert importlib.util.find_spec(name) is not None, "Optional payload validator is missing"
    return importlib.import_module(name).PydanticPayloadValidator(model)


class Nested(BaseModel):
    number: int


class Payload(BaseModel):
    nested: Nested
    labels: list[str]
    attributes: dict[str, int]


def test_frozen_input_is_same_object_and_output_never_replaces_event():
    seen = []

    class Observed(Payload):
        @classmethod
        def model_validate(cls, value, **kwargs):
            seen.append(value)
            return super().model_validate(value, **kwargs)

    event = Event(
        "id", "event", {"nested": {"number": "2"}, "labels": ["a"], "attributes": {"x": 1}}
    )
    original = event.payload
    assert adapter(Observed).validate(original) is None
    assert seen == [original]
    assert seen[0] is original
    assert event.payload is original
    assert isinstance(event.payload["nested"], Mapping)
    assert event.payload["nested"]["number"] == "2"
    assert event.payload["labels"] == ("a",)


def assert_detached(error):
    assert type(error) is PayloadValidationError
    assert error.args == ("Payload does not satisfy event contract",)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert not getattr(error, "__notes__", [])
    assert vars(error) == {}
    assert "secret" not in repr(error)


@pytest.mark.parametrize("ambient", [False, True])
def test_validation_errors_detached_even_inside_callers_except(ambient):
    validator = adapter(Payload)
    invalid = Event("id", "event", {"nested": {"number": "secret-input"}})

    def fail():
        with pytest.raises(PayloadValidationError) as caught:
            validator.validate(invalid.payload)
        assert_detached(caught.value)

    if ambient:
        try:
            raise RuntimeError("secret-ambient")
        except RuntimeError:
            fail()
    else:
        fail()


def test_schema_owned_strictness_rejects_frozen_tuple_without_thawing():
    class Strict(BaseModel):
        model_config = ConfigDict(strict=True)
        labels: list[str]

    with pytest.raises(PayloadValidationError) as caught:
        adapter(Strict).validate(Event("id", "event", {"labels": ["a"]}).payload)
    assert_detached(caught.value)


@pytest.mark.parametrize(
    "error",
    [
        TypeError("bug"),
        RuntimeError("bug"),
        asyncio.CancelledError(),
        SystemExit(),
        KeyboardInterrupt(),
    ],
)
def test_programmer_and_base_exceptions_keep_identity(error):
    class Broken(BaseModel):
        number: int

        @field_validator("number")
        @classmethod
        def broken(cls, value):
            raise error

    with pytest.raises(type(error)) as caught:
        adapter(Broken).validate(Event("id", "event", {"number": 1}).payload)
    assert caught.value is error


@pytest.mark.parametrize("error", [ValueError("secret-value"), AssertionError("secret-assertion")])
def test_framework_conversion_is_sanitized(error):
    class Converted(BaseModel):
        number: int

        @field_validator("number")
        @classmethod
        def broken(cls, value):
            raise error

    with pytest.raises(PayloadValidationError) as caught:
        adapter(Converted).validate(Event("id", "event", {"number": 1}).payload)
    assert_detached(caught.value)


@pytest.mark.parametrize("model", [None, object, BaseModel, 1])
def test_invalid_model_rejected(model):
    with pytest.raises(InvalidContractConfiguration):
        adapter(model)


def test_selected_model_required_but_subclasses_accepted():
    class Other(BaseModel):
        pass

    class Selected(BaseModel):
        @classmethod
        def model_validate(cls, value, **kwargs):
            return result[0]

    class Child(Selected):
        pass

    result = [Child()]
    validator = adapter(Selected)
    assert validator.validate(Event("id", "event", {}).payload) is None
    for value in (Other(), None, False, 0, {}, object()):
        result[0] = value
        with pytest.raises(InvalidValidatorResult) as caught:
            validator.validate(Event("id", "event", {}).payload)
        assert "Other" not in str(caught.value)


def test_detectable_async_overrides_and_callable_objects_rejected():
    effects = []

    async def coroutine(value):
        effects.append("coroutine")

    async def generator(value):
        effects.append("generator")
        yield None

    class AsyncCall:
        async def __call__(self, value):
            effects.append("call")

    class GeneratorCall:
        async def __call__(self, value):
            effects.append("generator-call")
            yield None

    for entry in (coroutine, generator, AsyncCall(), GeneratorCall()):

        class Model(BaseModel):
            pass

        Model.model_validate = entry
        with pytest.raises(InvalidContractConfiguration):
            adapter(Model)
    assert effects == []


def test_descriptor_read_once_and_error_identity():
    reads = []

    class Descriptor:
        def __get__(self, instance, owner):
            reads.append(owner)
            return lambda value: owner()

    class Model(BaseModel):
        pass

    Model.model_validate = Descriptor()
    validator = adapter(Model)
    assert reads == [Model]
    validator.validate(Event("id", "event", {}).payload)
    assert reads == [Model]
    error = RuntimeError("descriptor")

    class BrokenDescriptor:
        def __get__(self, instance, owner):
            raise error

    Model.model_validate = BrokenDescriptor()
    with pytest.raises(RuntimeError) as caught:
        adapter(Model)
    assert caught.value is error


def test_disguised_awaitables_preserve_caller_lifecycle():
    result = [None]
    effects = []

    class Model(BaseModel):
        @classmethod
        def model_validate(cls, value, **kwargs):
            return result[0]

    class Foreign:
        def __await__(self):
            effects.append("await")
            yield None

        def close(self):
            effects.append("close")

        def cancel(self):
            effects.append("cancel")

    async def fresh():
        effects.append("fresh")

    async def generated():
        effects.append("generated")
        yield None

    validator = adapter(Model)
    payload = Event("id", "event", {}).payload
    native = fresh()
    generator = generated()
    for value in (Foreign(), native, generator):
        result[0] = value
        with pytest.raises(InvalidValidatorResult):
            validator.validate(payload)
    assert inspect.getcoroutinestate(native) == inspect.CORO_CLOSED
    assert generator.ag_frame is not None
    assert effects == []
    for raises in (False, True):
        token = object()

        class Inert:
            def __await__(self):
                yield token

        async def started():
            try:
                await Inert()
            finally:
                effects.append("owner-cleanup")
                if raises:
                    raise RuntimeError("owner-only")

        suspended = started()
        assert suspended.send(None) is token
        result[0] = suspended
        try:
            with pytest.raises(InvalidValidatorResult):
                validator.validate(payload)
            assert inspect.getcoroutinestate(suspended) == inspect.CORO_SUSPENDED
            assert effects.count("owner-cleanup") == int(raises)
        finally:
            if raises:
                with pytest.raises(RuntimeError, match="owner-only"):
                    suspended.close()
            else:
                suspended.close()
    result[0] = native
    with pytest.raises(InvalidValidatorResult):
        validator.validate(payload)
