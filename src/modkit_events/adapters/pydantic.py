"""Explicit optional Pydantic validation; core imports never load this module."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import cast

from pydantic import BaseModel, ValidationError

from ..contracts import (
    InvalidContractConfiguration,
    InvalidValidatorResult,
    PayloadValidationError,
    _close_created_coroutine,
    _is_async_callable,
)


class PydanticPayloadValidator:
    """Validate frozen input without replacing it with model output.

    Schema coercion/strictness and overrides remain application owned. Pydantic
    converts validator ValueError/AssertionError into ValidationError; only that
    framework error is sanitized. Other callback failures retain their identity.
    """

    def __init__(self, model: type[BaseModel]) -> None:
        if not isinstance(model, type) or not issubclass(model, BaseModel) or model is BaseModel:
            raise InvalidContractConfiguration("Expected a Pydantic model subclass")
        method = getattr(model, "model_validate", None)
        if not callable(method) or _is_async_callable(method):
            raise InvalidContractConfiguration("Expected synchronous model validation")
        self._model = model
        # Snapshot the entrypoint once; do not repeatedly execute user descriptors.
        self._validate = cast(Callable[[Mapping[str, object]], object], method)

    def _accepts(self, payload: Mapping[str, object]) -> bool:
        try:
            result = self._validate(payload)
        except ValidationError:
            # Retain no framework exception object or parsed output on the public error.
            return False
        if inspect.isawaitable(result) or inspect.isasyncgen(result):
            _close_created_coroutine(result)
            raise InvalidValidatorResult("Model validator must return the selected model")
        if not isinstance(result, self._model):
            raise InvalidValidatorResult("Model validator must return the selected model")
        return True

    def validate(self, payload: Mapping[str, object]) -> None:
        if self._accepts(payload):
            return
        # Outside the framework except, but callers may have an ambient exception.
        # A bare reraise preserves our explicit detachment instead of chaining it again.
        try:
            raise PayloadValidationError() from None
        except PayloadValidationError as error:
            error.__context__ = None
            raise
