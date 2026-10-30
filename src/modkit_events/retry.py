"""Explicit bounded retry policy; attempt counts include the initial attempt."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1
    max_delay: float = 60

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if any(
            isinstance(x, bool) or not math.isfinite(x) or x < 0
            for x in (self.base_delay, self.max_delay)
        ):
            raise ValueError("Retry delays must be finite and nonnegative")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")

    def delay(self, attempt: int) -> float:
        if type(attempt) is not int or attempt < 1:
            raise ValueError("attempt must be positive")
        if self.base_delay == 0:
            return 0
        exponent = min(attempt - 1, 1023)
        try:
            return min(self.max_delay, math.ldexp(self.base_delay, exponent))
        except OverflowError:
            return self.max_delay
