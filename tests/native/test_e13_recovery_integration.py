"""Author-only opt-in E13 smoke test; NEVER run in source-only verification.

Requires separately authorized disposable schema, whole jobs namespace authority,
pinned E33 expectations and exact optional dependencies. No fixture creation,
grants or installs. Does not replace full item/fault/commit qualification.
"""

import json
import os
import unittest
from pathlib import Path


@unittest.skipUnless(
    os.environ.get("MODKIT_E13_NATIVE_AUTHORIZED") == "jobs-whole-namespace",
    "requires separate native execution authorization",
)
class RecoveryIntegration(unittest.TestCase):
    def test_readiness_then_page_on_original_root_and_rollback(self):
        from modkit_events.persistence import bindings as b
        from modkit_events.persistence import managed_lifecycle as m
        from modkit_events.persistence import observations as o
        from modkit_events.persistence.ledger import ExecutionLedger
        from modkit_events.persistence.recovery_profile import (
            recovery_requirements,
            verify_recovery_driver,
        )

        entries = json.loads(Path(os.environ["MODKIT_E13_READINESS_FILE"]).read_text())
        expectation = b.ReadinessExpectation(
            components=tuple(
                o.SchemaStatus(
                    component=e["component"],
                    version=e["version"],
                    migration_digest=bytes.fromhex(e["migration_digest"]),
                    catalog_contract_id=e["catalog_contract_id"],
                    scope_format_id=e["scope_format_id"],
                    intent_format_id=e["intent_format_id"],
                )
                for e in entries
            )
        )
        requirements = recovery_requirements(readiness=expectation)
        verify_recovery_driver(requirements)
        from modkit_events.persistence import native_execution as e
        from modkit_events.persistence import native_sync as n

        ledger = ExecutionLedger()
        m.configure_managed_registry(limits=requirements.lifecycle_minimum, execution_ledger=ledger)
        execution = m.reserve_execution(ledger)
        actual = n.ManagedConnection.connect(
            os.environ["MODKIT_NATIVE_TEST_DSN"], execution_ledger=ledger
        )
        checkout = n.attach_native(actual, execution, execution_ledger=ledger)
        for readiness in (True, False):
            root = n.start_root(checkout, execution_ledger=ledger)
            if readiness:
                a = e.prepare_readiness(
                    execution,
                    "workers",
                    expectation,
                    execution_ledger=ledger,
                    capacity=requirements.e33_preparation_min,
                )
                capacity = requirements.e33_result_min
            else:
                a = e.prepare_recovery(
                    execution,
                    execution_ledger=ledger,
                    capacity=requirements.e13_preparation_min,
                    namespace=b"jobs",
                    kind="job",
                    limit=1,
                    scan_after=None,
                    discovery_budget=128,
                )
                capacity = requirements.e13_result_min
            ticket = m.admit(root, a, execution_ledger=ledger)
            result = m.reserve_result(ticket, capacity, execution_ledger=ledger)
            if not readiness:
                self.assertEqual(m.result_capacity(ticket, execution_ledger=ledger), capacity)
            e.execute(ticket, result, execution_ledger=ledger)
            value = m.read_result(result, execution_ledger=ledger)
            if readiness:
                self.assertEqual(value, expectation.components)
            else:
                self.assertIs(type(value), o.ScanPage)
                self.assertLessEqual(len(value.items), 1)
                self.assertLessEqual(value.visited, 128)
            value = None
            m.release_result(result, execution_ledger=ledger)
            m.release_ticket(ticket, execution_ledger=ledger)
            m.release_preparation(a, execution_ledger=ledger)
            receipt = n.rollback(root, execution_ledger=ledger)
            m.acknowledge_root_end(receipt, execution_ledger=ledger)
            m.release_root(root, execution_ledger=ledger)
        m.retire(checkout, execution_ledger=ledger)
        intent = m.prepare_cleanup(checkout, execution_ledger=ledger)
        bundle = m.reserve_cleanup(intent, 4096, execution_ledger=ledger)
        permit = m.pin_cleanup(bundle, execution_ledger=ledger)
        receipt = n.close(permit, execution_ledger=ledger)
        m.acknowledge_physical_close(receipt, execution_ledger=ledger)
        m.release_cleanup(bundle, execution_ledger=ledger)
        m.detach_terminal(checkout, execution_ledger=ledger)
        m.dispose_execution(execution, execution_ledger=ledger)
