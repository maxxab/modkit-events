"""Native renewal qualification is intentionally gated.

This file does not open connections or claim database coverage. The separately
reviewed native packet must exercise E08-open renewal beyond the original lease,
observed E10 and cancellation wait edges in both orders, post-lock lease/deadline
expiry, staged rollback versus committed/fresh W02 observation, and isolated
unknown/fail-stop/cancelled-await cases. Pure fakes are not replacements.
"""

import pytest

pytest.skip(
    "E05 native qualification requires a separately released reviewed packet; no DB execution",
    allow_module_level=True,
)
