"""Public discoverability and base-import independence in fresh processes."""

import importlib
import subprocess
import sys
from pathlib import Path

import modkit_events

LEGACY = {
    "Claim": "claims",
    "ClaimResult": "claims",
    "ClaimStore": "claims",
    "Consumer": "consumer",
    "Dispatcher": "dispatch",
    "Event": "models",
    "JsonCodec": "codec",
    "MemoryClaimStore": "claims",
    "OwnershipLost": "claims",
    "Publisher": "protocols",
    "RetryPolicy": "retry",
    "OutboxClaim": "outbox",
    "OutboxPublisher": "outbox",
    "OutboxStore": "outbox",
}
ADDITIVE = {
    "contracts": (
        "ConflictingRouteError",
        "ContractRegistry",
        "DuplicateContractError",
        "EventContract",
        "InvalidContractConfiguration",
        "InvalidValidatorResult",
        "PayloadValidationError",
        "PayloadValidator",
        "UnknownEventName",
        "UnsupportedSchemaVersion",
    ),
    "subscriptions": (
        "ConflictingConsumerGroupError",
        "DuplicateSubscriptionError",
        "InvalidSubscriptionConfiguration",
        "StartPosition",
        "Subscription",
        "UnsupportedCapabilityError",
        "validate_subscriptions",
    ),
    "delivery": (
        "DeliveryContext",
        "DeliveryPhase",
        "DeliveryRecord",
        "DeliveryRouteMismatch",
        "Disposition",
        "DispositionKind",
    ),
}


def test_public_objects_preserve_legacy_and_expose_managed_contracts():
    for name, module in LEGACY.items():
        assert getattr(modkit_events, name) is getattr(
            importlib.import_module("modkit_events." + module), name
        )
    for module, names in ADDITIVE.items():
        for name in names:
            assert hasattr(modkit_events, name), name
            assert getattr(modkit_events, name) is getattr(
                importlib.import_module("modkit_events." + module), name
            )
    assert set(modkit_events.__all__) == set(LEGACY) | {
        name for names in ADDITIVE.values() for name in names
    }
    assert len(modkit_events.__all__) == len(set(modkit_events.__all__))


def test_base_import_without_extras_or_sibling_packages():
    source = Path(__file__).resolve().parents[1] / "src"
    code = """
import sys, importlib.abc, logging
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'redis','sqlalchemy','psycopg','asyncpg','pydantic','modkit_workers',
            'modkit_diagnostics','modkit_api_versioning','modkit_api_responses',
        }:
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Block())
initial = tuple(logging.getLogger().handlers)
import modkit_events
from modkit_events import contracts, subscriptions, delivery
assert tuple(logging.getLogger().handlers) == initial
assert not hasattr(modkit_events, 'PydanticPayloadValidator')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(source)!r});\n" + code],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
