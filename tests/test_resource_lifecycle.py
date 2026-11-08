"""T1 local primitive controls; fresh processes own irreversible authorities.

No PostgreSQL/driver/lifecycle outcome is simulated by these identity objects.
Each test names the broken contract it detects and uses the real leaf/ledger.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
_PRELUDE = """
import copy
import gc
import importlib.util
import pickle
import threading
import weakref
assert importlib.util.find_spec('modkit_events.persistence.resource_lifecycle') is not None, 'T1 resource lifecycle primitive is missing'
from modkit_events.persistence import resource_lifecycle as m
from modkit_events.persistence.errors import ErrorCode as E, PersistenceError
from modkit_events.persistence.ledger import ExecutionLedger
from modkit_events.persistence.resource_registry import resource_domain

def expect(code, action, flag=False):
    try:
        action()
    except PersistenceError as error:
        assert error.code is code, (error.code, code)
        assert error.unconfirmed is flag
        assert str(error) == code.value
        assert error.__cause__ is None and error.__context__ is None
        assert error.__suppress_context__ is True
    else:
        raise AssertionError('missing fixed rejection: ' + code.value)

def setup(limit=2):
    ledger = ExecutionLedger()
    m.configure_registry(retained_cell_limit=limit, execution_ledger=ledger)
    return ledger

def binding(ledger, resource=None):
    resource = object() if resource is None else resource
    cell = m.resource_cell(resource, execution_ledger=ledger)
    checkout, root = object(), object()
    association = m.bind_initial(cell, checkout_witness=checkout,
        root_witness=root, execution_ledger=ledger)
    return cell, checkout, root, association
"""


def _run(body):
    script = "import sys\nsys.path.insert(0, " + repr(str(_SRC)) + ")\n"
    script += textwrap.dedent(_PRELUDE) + textwrap.dedent(body)
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == result.stderr == ""


def test_configuration_rejects_invalid_reconfiguration_and_has_no_eager_limit_allocation():
    """Catches a default, bool limit, reconfigure escape, or proportional allocation."""
    _run("""
    ledger = ExecutionLedger()
    expect(E.PROFILE_REJECTED, lambda: m.resource_cell(object(), execution_ledger=ledger))
    for value in (None, True, False, 0, -1, 1.5, '2'):
        expect(E.LOCAL_INVALID_ARGUMENT, lambda: m.configure_registry(
            retained_cell_limit=value, execution_ledger=ledger))
    m.configure_registry(retained_cell_limit=10**1000, execution_ledger=ledger)
    expect(E.PROFILE_REJECTED, lambda: m.configure_registry(
        retained_cell_limit=10**1000, execution_ledger=ledger))
    binding(ledger)
    binding(ledger)
    """)


def test_identity_lookup_never_calls_resource_hooks_and_retention_counts_retired_cells():
    """Catches hash/equality/repr lookup, resource dropping, or retirement eviction."""
    _run("""
    ledger = setup(2)
    class Hostile:
        def __hash__(self): raise AssertionError('hash called')
        def __eq__(self, other): raise AssertionError('equality called')
        def __repr__(self): raise AssertionError('repr called')
        def __del__(self, lock=m._lock):
            assert not lock.locked(), 'resource finalized while locked'
    resource = Hostile()
    retained = weakref.ref(resource)
    cell, checkout, root, association = binding(ledger, resource)
    assert m.resource_cell(resource, execution_ledger=ledger) is cell
    receipt = m.retire_cell(association, root_witness=root, execution_ledger=ledger)
    m.acknowledge_retirement(receipt, association=association,
        root_witness=root, execution_ledger=ledger)
    assert m.resource_cell(resource, execution_ledger=ledger) is cell
    del resource
    gc.collect()
    assert retained() is not None
    other, _, _, _ = binding(ledger, Hostile())
    assert other is not cell
    expect(E.CAPACITY_EXCEEDED, lambda: m.resource_cell(Hostile(), execution_ledger=ledger))
    assert m.resource_cell(retained(), execution_ledger=ledger) is cell
    """)


def test_binding_is_one_shot_and_subjects_and_ledger_use_exact_identity():
    """Catches lost-return recovery, root reassociation, or equivalent ledger use."""
    _run("""
    ledger = setup()
    cell, checkout, root, association = binding(ledger)
    assert association.generation == 1
    expect(E.INVALID_OBSERVATION, lambda: m.bind_initial(cell,
        checkout_witness=checkout, root_witness=root, execution_ledger=ledger))
    expect(E.INVALID_OBSERVATION, lambda: m.bind_initial(cell,
        checkout_witness=object(), root_witness=object(), execution_ledger=ledger))
    expect(E.INVALID_OBSERVATION, lambda: m.try_admit(association,
        root_witness=object(), execution_ledger=ledger))
    expect(E.INVALID_OBSERVATION, lambda: m.try_admit(association,
        root_witness=root, execution_ledger=ExecutionLedger()))
    expect(E.LOCAL_INVALID_ARGUMENT, lambda: m.try_admit(object(),
        root_witness=root, execution_ledger=ledger))
    ticket = m.try_admit(association, root_witness=root, execution_ledger=ledger)
    m.release_ticket(ticket, association=association, root_witness=root, execution_ledger=ledger)
    """)


def test_stale_release_cannot_free_successor_and_retirement_wins_acceptance():
    """Catches ticket-history replay and acceptance after a linearized retirement."""
    _run("""
    ledger = setup()
    cell, checkout, root, association = binding(ledger)
    first = m.try_admit(association, root_witness=root, execution_ledger=ledger)
    m.validate_ticket(first, association=association, root_witness=root, execution_ledger=ledger)
    expect(E.RESOURCE_BUSY, lambda: m.try_admit(association, root_witness=root, execution_ledger=ledger))
    m.release_ticket(first, association=association, root_witness=root, execution_ledger=ledger)
    second = m.try_admit(association, root_witness=root, execution_ledger=ledger)
    expect(E.INVALID_OBSERVATION, lambda: m.release_ticket(first,
        association=association, root_witness=root, execution_ledger=ledger))
    m.validate_ticket(second, association=association, root_witness=root, execution_ledger=ledger)
    receipt = m.retire_cell(association, root_witness=root, execution_ledger=ledger)
    expect(E.PROFILE_REJECTED, lambda: m.validate_ticket(second,
        association=association, root_witness=root, execution_ledger=ledger))
    expect(E.PROFILE_REJECTED, lambda: m.try_admit(association, root_witness=root, execution_ledger=ledger))
    m.release_ticket(second, association=association, root_witness=root, execution_ledger=ledger)
    expect(E.INVALID_OBSERVATION, lambda: m.release_ticket(second,
        association=association, root_witness=root, execution_ledger=ledger))
    m.acknowledge_retirement(receipt, association=association, root_witness=root, execution_ledger=ledger)
    """)


def test_retirement_receipt_requires_original_possession_and_exact_subject():
    """Catches receipt reconstruction from repeat retire and cross-cell acknowledgement."""
    _run("""
    ledger = setup()
    _, _, root, association = binding(ledger)
    _, _, other_root, other = binding(ledger)
    ticket = m.try_admit(association, root_witness=root, execution_ledger=ledger)
    receipt = m.retire_cell(association, root_witness=root, execution_ledger=ledger)
    expect(E.PROFILE_REJECTED, lambda: m.retire_cell(association, root_witness=root, execution_ledger=ledger))
    expect(E.LOCAL_INVALID_ARGUMENT, lambda: m.acknowledge_retirement(ticket,
        association=association, root_witness=root, execution_ledger=ledger))
    expect(E.INVALID_OBSERVATION, lambda: m.acknowledge_retirement(receipt,
        association=other, root_witness=other_root, execution_ledger=ledger))
    m.acknowledge_retirement(receipt, association=association, root_witness=root, execution_ledger=ledger)
    m.acknowledge_retirement(receipt, association=association, root_witness=root, execution_ledger=ledger)
    expect(E.CAPACITY_EXCEEDED, lambda: m.resource_cell(object(), execution_ledger=ledger))
    resource_domain().trip()
    m.acknowledge_retirement(receipt, association=association, root_witness=root, execution_ledger=ledger)
    m.release_ticket(ticket, association=association, root_witness=root, execution_ledger=ledger)
    """)


def test_opaque_tokens_cannot_be_issued_mutated_copied_or_serialized():
    """Catches public token factories, payload repr, writable state or copied authority."""
    _run("""
    ledger = setup()
    cell, checkout, root, association = binding(ledger)
    ticket = m.try_admit(association, root_witness=root, execution_ledger=ledger)
    receipt = m.retire_cell(association, root_witness=root, execution_ledger=ledger)
    for value, name in ((cell, 'ResourceCell'), (association, 'ResourceAssociation'),
                        (ticket, 'OperationTicket'), (receipt, 'RetirementReceipt')):
        assert repr(value) == '<' + name + '>'
        assert not hasattr(value, '__dict__')
        for action, kind in ((lambda: type(value)(), TypeError),
             (lambda: type('Derived', (type(value),), {}), TypeError),
             (lambda: setattr(value, 'payload', 'secret'), AttributeError),
             (lambda: delattr(value, 'payload'), AttributeError),
             (lambda: copy.copy(value), TypeError),
             (lambda: copy.deepcopy(value), TypeError),
             (lambda: pickle.dumps(value), TypeError)):
            try: action()
            except kind: pass
            else: raise AssertionError('opaque authority escaped')
    """)


def test_contextual_errors_keep_sticky_uncertainty_and_detach_ambient_context():
    """Catches hardcoded False leaf errors and ledger lock nesting."""
    _run("""
    ledger = setup(1)
    cell, checkout, root, association = binding(ledger)
    ledger.note_incident(E.OUTCOME_UNKNOWN)
    class LedgerLock:
        def __enter__(self):
            assert not m._lock.locked(), 'ledger lock nested in registry lock'
        def __exit__(self, *args): return False
    ledger._lock = LedgerLock()
    try: raise RuntimeError('sensitive ambient value')
    except RuntimeError:
        expect(E.LOCAL_INVALID_ARGUMENT, lambda: m.resource_cell(None, execution_ledger=ledger), True)
        expect(E.INVALID_OBSERVATION, lambda: m.try_admit(association,
            root_witness=object(), execution_ledger=ledger), True)
        expect(E.CAPACITY_EXCEEDED, lambda: m.resource_cell(object(), execution_ledger=ledger), True)
        ticket = m.try_admit(association, root_witness=root, execution_ledger=ledger)
        expect(E.RESOURCE_BUSY, lambda: m.try_admit(association,
            root_witness=root, execution_ledger=ledger), True)
        resource_domain().trip()
        expect(E.PROFILE_REJECTED, lambda: m.try_admit(association,
            root_witness=root, execution_ledger=ledger), True)
        m.release_ticket(ticket, association=association, root_witness=root, execution_ledger=ledger)
    assert ledger.uncertainty.present
    """)


def test_two_real_threads_share_one_active_slot_with_deterministic_release():
    """Catches facade-local admission locks and concurrent successful ticket publication."""
    _run("""
    ledger = setup()
    _, _, root, association = binding(ledger)
    admitted, contender_done = threading.Event(), threading.Event()
    failures = []
    def owner():
        try:
            ticket = m.try_admit(association, root_witness=root, execution_ledger=ledger)
            admitted.set()
            assert contender_done.wait(3)
            m.validate_ticket(ticket, association=association, root_witness=root, execution_ledger=ledger)
            m.release_ticket(ticket, association=association, root_witness=root, execution_ledger=ledger)
        except BaseException as error: failures.append(error)
    def contender():
        try:
            assert admitted.wait(3)
            expect(E.RESOURCE_BUSY, lambda: m.try_admit(association, root_witness=root, execution_ledger=ledger))
        except BaseException as error: failures.append(error)
        finally: contender_done.set()
    threads = [threading.Thread(target=owner, daemon=True), threading.Thread(target=contender, daemon=True)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(5)
    assert all(not thread.is_alive() for thread in threads)
    assert not failures, failures
    ticket = m.try_admit(association, root_witness=root, execution_ledger=ledger)
    m.release_ticket(ticket, association=association, root_witness=root, execution_ledger=ledger)
    """)


def test_uncertain_lock_exit_keeps_primary_baseexception_and_stops_domain():
    """Catches success after uncertain publication or replacement of primary cancellation."""
    _run("""
    ledger = setup()
    cell, checkout, root, association = binding(ledger)
    class Abort(BaseException): pass
    primary = Abort('private sentinel')
    real_lock = m._lock
    class InterruptedExit:
        def __enter__(self): return real_lock.__enter__()
        def __exit__(self, *args):
            real_lock.__exit__(*args)
            raise primary
    m._lock = InterruptedExit()
    try:
        m.try_admit(association, root_witness=root, execution_ledger=ledger)
    except BaseException as error:
        assert error is primary
    else: raise AssertionError('interruption was hidden')
    m._lock = real_lock
    assert resource_domain().stopped
    expect(E.PROFILE_REJECTED, lambda: m.try_admit(association,
        root_witness=root, execution_ledger=ledger))
    """)


@pytest.mark.parametrize(
    "body_failure,exit_failure,containment_failure,context_is_exit",
    [
        (True, False, False, False),
        (True, True, False, False),
        (False, True, False, False),
        (True, True, True, False),
        (True, True, False, True),
    ],
)
def test_first_publication_failure_survives_cleanup_and_containment_failures(
    body_failure,
    exit_failure,
    containment_failure,
    context_is_exit,
):
    """Catches replacement of primary P by exit S or containment Q, including chains."""
    flags = (
        f"body_failure={body_failure!r}\nexit_failure={exit_failure!r}\n"
        f"containment_failure={containment_failure!r}\ncontext_is_exit={context_is_exit!r}\n"
    )
    _run(
        flags
        + textwrap.dedent("""
    ledger = setup()
    class Abort(BaseException): pass
    primary, secondary, containment = Abort('P'), Abort('S'), Abort('Q')
    expected = primary if body_failure else secondary
    cause, context = RuntimeError('original cause'), RuntimeError('original context')
    if context_is_exit: context = secondary
    expected.__cause__ = cause
    expected.__context__ = context
    expected.__suppress_context__ = False
    expected.add_note('original note')
    original_notes = expected.__notes__
    real_lock, real_domain, real_cells = m._lock, m._domain, m._cells
    containment_calls = []
    class FaultLock:
        def __enter__(self): return real_lock.__enter__()
        def __exit__(self, *args):
            real_lock.__exit__(*args)
            if exit_failure: raise secondary
    class FaultTable(dict):
        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            if body_failure: raise primary
    class Containment:
        @property
        def stopped(self): return real_domain.stopped
        def trip(self):
            containment_calls.append(True)
            result = real_domain.trip()
            if containment_failure: raise containment
            return result
    m._lock, m._domain, m._cells = FaultLock(), Containment(), FaultTable(real_cells)
    escaped = None
    try:
        try: m.resource_cell(object(), execution_ledger=ledger)
        except BaseException as error: escaped = error
    finally:
        m._lock, m._domain, m._cells = real_lock, real_domain, real_cells
    assert escaped is expected, 'mutex cleanup replaced the first failure'
    assert escaped.__cause__ is cause
    assert escaped.__context__ is context
    assert escaped.__suppress_context__ is False
    assert escaped.__notes__ is original_notes and original_notes == ['original note']
    assert containment_calls == [True]
    assert real_domain.stopped
    assert not real_lock.locked()
    """)
    )
