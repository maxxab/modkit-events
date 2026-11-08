"""Managed local controls; isolated reflection fixtures prove no driver outcome."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
_PRELUDE = """
import sys
sys.path.insert(0,SOURCE)
from modkit_events.persistence import resource_lifecycle as old
from modkit_events.persistence import managed_lifecycle as m
from modkit_events.persistence.errors import ErrorCode as E,PersistenceError
from modkit_events.persistence.ledger import ExecutionLedger

def expect(code, function, flag=False):
    try: function()
    except PersistenceError as error:
        assert error.code is code,(error.code,code)
        assert error.unconfirmed is flag
        assert str(error)==code.value
    else: raise AssertionError("expected "+code.value)

def limits(**overrides):
    values=dict(retained_cells=3,admitted_live=3,checkouts=3,roots=4,
        roots_per_checkout=2,executions=3,preparations=4,
        preparations_per_execution=2,prepare_bytes=64,
        prepare_bytes_per_execution=32,results=4,results_per_ticket=2,
        result_bytes=64,result_bytes_per_ticket=32,cleanup_bundles=3,
        cleanup_bytes=96,construction_slots=4)
    values.update(overrides)
    return m.LifecycleLimits(**values)
"""


def _run(body, *, native=False):
    script = "SOURCE=" + repr(str(_SRC)) + "\n" + _PRELUDE + textwrap.dedent(body)
    executable = os.environ.get("MODKIT_NATIVE_TEST_PYTHON") if native else sys.executable
    if executable is None:
        pytest.skip("set MODKIT_NATIVE_TEST_PYTHON to the qualified optional driver interpreter")
    result = subprocess.run(
        [executable, "-I", "-B", "-c", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "MANAGED_BODY_COMPLETE\n" and result.stderr == ""


def test_managed_startup_and_execution_are_explicit_and_one_shot():
    """Breaks if configure binds its contextual ledger or disposed ledgers rebind."""
    _run("""
    context,L=ExecutionLedger(),ExecutionLedger()
    m.configure_managed_registry(limits=limits(),execution_ledger=context)
    expect(E.PROFILE_REJECTED,lambda:old.configure_registry(retained_cell_limit=4,execution_ledger=L))
    x=m.reserve_execution(L)
    expect(E.INVALID_OBSERVATION,lambda:m.reserve_execution(L))
    m.dispose_execution(x,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m.reserve_execution(L))
    assert not L.uncertainty.present
    assert m.capacity_snapshot(execution_ledger=L)['X']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_limits_atomicity_t1_mode_and_missing_record_context():
    """Breaks on partial admission, mode switching, bool limits or false context."""
    _run("""
    L=ExecutionLedger()
    expect(E.LOCAL_INVALID_ARGUMENT,lambda:m.configure_managed_registry(limits=limits(retained_cells=True),execution_ledger=L))
    m.configure_managed_registry(limits=limits(executions=1),execution_ledger=L)
    x=m.reserve_execution(L)
    other=ExecutionLedger()
    expect(E.CAPACITY_EXCEEDED,lambda:m.reserve_execution(other))
    assert other._managed_execution is None
    L.note_incident(E.OUTCOME_UNKNOWN)
    m.dispose_execution(x,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m.dispose_execution(x,execution_ledger=L),True)
    expect(E.PROFILE_REJECTED,lambda:old.resource_cell(object(),execution_ledger=L),True)
    assert m.capacity_snapshot(execution_ledger=L)==dict.fromkeys(m._names,0)
    print('MANAGED_BODY_COMPLETE')
    """)
    _run("""
    L=ExecutionLedger();old.configure_registry(retained_cell_limit=2,execution_ledger=L)
    expect(E.PROFILE_REJECTED,lambda:m.configure_managed_registry(limits=limits(),execution_ledger=L))
    expect(E.PROFILE_REJECTED,lambda:m.reserve_execution(L))
    print('MANAGED_BODY_COMPLETE')
    """)


def test_preparation_capacity_and_reference_release_preserve_sticky_ledger():
    """Breaks when held preparations refund before release or X disposes early."""
    _run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L)
    a=m.reserve_preparation(x,32,execution_ledger=L)
    m.set_preparation(a,b'payload',execution_ledger=L)
    expect(E.CAPACITY_EXCEEDED,lambda:m.reserve_preparation(x,1,execution_ledger=L))
    expect(E.RESOURCE_BUSY,lambda:m.dispose_execution(x,execution_ledger=L))
    L.note_incident(E.OUTCOME_UNKNOWN)
    m.release_preparation(a,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m.release_preparation(a,execution_ledger=L),True)
    m.dispose_execution(x,execution_ledger=L)
    assert L.uncertainty.present
    assert m.capacity_snapshot(execution_ledger=L)==dict.fromkeys(m._names,0)
    print('MANAGED_BODY_COMPLETE')
    """)


_FIXTURE = """
# Private structural fixtures only: no fixture proves a database outcome.
class Physical:
    __slots__=('anchor','pgconn','closed','autocommit')
    def __init__(self):
        self.pgconn=type('PG',(),{'transaction_status':0})();self.closed=False;self.autocommit=False
        self.anchor=old._issue(old.ResourceCell,_key=id(self),_stamp=object(),_terminal=False)
m._native_type=Physical;m._cell_descriptor=Physical.anchor

def setup_physical():
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);actual=Physical()
    c=m.attach_native(actual,x,execution_ledger=L)
    return L,x,actual,c

def active_root(c,L):
    # Reflect the issuer's local transition, NOT real start/rollback evidence.
    with m._construction(False):
        r,code=m._reserve_root(c,L)
        assert code is None
        m._complete_start(r,L,known=True)
    return r
"""


def _run_fixture(body):
    _run(_FIXTURE + textwrap.dedent(body))


def test_actual_identity_single_gate_and_result_envelope_limits():
    """Breaks if aliases split gates, live result releases early, or stale ticket frees."""
    _run_fixture("""
    L,x,actual,c=setup_physical()
    cell=old.resource_cell(actual,execution_ledger=L)
    assert cell is actual.anchor
    expect(E.INVALID_OBSERVATION,lambda:m.attach_native(actual,x,execution_ledger=L))
    r=active_root(c,L);a=m.reserve_preparation(x,8,execution_ledger=L)
    m.set_preparation(a,b'intent',execution_ledger=L)
    t=m.admit(r,a,execution_ledger=L)
    expect(E.RESOURCE_BUSY,lambda:m.admit(r,a,execution_ledger=L))
    b=m.reserve_result(t,32,execution_ledger=L)
    expect(E.CAPACITY_EXCEEDED,lambda:m.reserve_result(t,1,execution_ledger=L))
    expect(E.RESOURCE_BUSY,lambda:m.release_ticket(t,execution_ledger=L))
    m.release_result(b,execution_ledger=L);m.release_ticket(t,execution_ledger=L)
    t2=m.admit(r,a,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m.release_ticket(t,execution_ledger=L))
    m.validate_ticket(t2,execution_ledger=L)
    m.retire(c,execution_ledger=L)
    expect(E.PROFILE_REJECTED,lambda:m.validate_ticket(t2,execution_ledger=L))
    m.release_ticket(t2,execution_ledger=L)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_terminal_detach_preserves_original_anchor_and_refunds_only_exact_scopes():
    """Local consumers only; injected private receipts are not physical proof."""
    _run_fixture("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    m.abandon_root(r,execution_ledger=L)
    assert L.uncertainty.present
    m.retire(c,execution_ledger=L)
    intent=m.prepare_cleanup(c,execution_ledger=L)
    reservation=m.reserve_cleanup(intent,16,execution_ledger=L)
    permit=m.pin_cleanup(reservation,execution_ledger=L)
    # Exact private issuer state drives consumer test; no real close happened.
    with m._construction(True):
        op,receipt,code=m._reserve_close(permit,L)
        assert code is None
        m._complete_close(permit,L,known=True)
    expect(E.INVALID_OBSERVATION,lambda:m.acknowledge_physical_close(m._handle('CLOSE'),execution_ledger=L),True)
    m.acknowledge_physical_close(receipt,execution_ledger=L)
    assert m.capacity_snapshot(execution_ledger=L)['V']==0
    assert m.capacity_snapshot(execution_ledger=L)['P']==1
    m.release_root(r,execution_ledger=L)
    m.release_cleanup(reservation,execution_ledger=L)
    m.detach_terminal(c,execution_ledger=L)
    assert old.resource_cell(actual,execution_ledger=L) is actual.anchor
    expect(E.PROFILE_REJECTED,lambda:m.attach_native(actual,x,execution_ledger=L),True)
    m.dispose_execution(x,execution_ledger=L)
    assert m.capacity_snapshot(execution_ledger=L)==dict.fromkeys(m._names,0)
    expect(E.INVALID_OBSERVATION,lambda:m.detach_terminal(c,execution_ledger=L),True)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_root_receipt_is_exact_and_successive_roots_do_not_replace_execution():
    """Private issuer transitions test consumers only, not actual rollback history."""
    _run_fixture("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    with m._construction(False):
        op,receipt,code=m._reserve_rollback(r,L)
        assert code is None
        m._complete_rollback(r,L,known=True)
    expect(E.INVALID_OBSERVATION,lambda:m.acknowledge_root_end(m._handle('ROOT_END'),execution_ledger=L))
    m.acknowledge_root_end(receipt,execution_ledger=L)
    m.acknowledge_root_end(receipt,execution_ledger=L)
    r2=active_root(c,L)
    assert r2 is not r and m.capacity_snapshot(execution_ledger=L)['X']==1
    m.release_root(r,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m.acknowledge_root_end(receipt,execution_ledger=L))
    m.abandon_root(r2,execution_ledger=L)
    expect(E.RESOURCE_BUSY,lambda:m.release_root(r2,execution_ledger=L),True)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_lost_close_receipt_and_running_abandon_keep_charges():
    """Breaks if storage supplies a public receipt getter or unknown close refunds."""
    _run_fixture("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    with m._construction(False):
        op,receipt,code=m._reserve_rollback(r,L)
        assert code is None
    expect(E.RESOURCE_BUSY,lambda:m.abandon_root(r,execution_ledger=L))
    with m._construction(True): m._complete_rollback(r,L,known=False)
    m.abandon_root(r,execution_ledger=L)
    m.retire(c,execution_ledger=L)
    intent=m.prepare_cleanup(c,execution_ledger=L)
    reservation=m.reserve_cleanup(intent,16,execution_ledger=L)
    permit=m.pin_cleanup(reservation,execution_ledger=L)
    with m._construction(True):
        op,receipt,code=m._reserve_close(permit,L)
        assert code is None
        m._complete_close(permit,L,known=True)
    del receipt
    expect(E.RESOURCE_BUSY,lambda:m.detach_terminal(c,execution_ledger=L),True)
    assert m.capacity_snapshot(execution_ledger=L)['V']==1
    assert not hasattr(m,'get_close_receipt')
    print('MANAGED_BODY_COMPLETE')
    """)


def test_optional_native_exact_version_and_startup_reject_before_acquisition():
    """Real installed module/class; guarded calls must not reach connection acquisition."""
    _run(
        """
    from modkit_events.persistence import native_sync as n
    import importlib
    assert importlib.import_module('modkit_events.persistence.native_sync') is n
    assert issubclass(n.ManagedConnection,n.psycopg.Connection)
    L=ExecutionLedger()
    expect(E.PROFILE_REJECTED,lambda:n.ManagedConnection.connect('host=must-not-contact',execution_ledger=L))
    m.configure_managed_registry(limits=limits(),execution_ledger=L)
    n.psycopg.__version__='unsupported'
    def acquisition_forbidden(cls,*args,**kwargs):
        raise AssertionError('unqualified acquisition reached')
    n.psycopg.Connection.connect=classmethod(acquisition_forbidden)
    expect(E.PROFILE_REJECTED,lambda:n.ManagedConnection.connect('host=must-not-contact',execution_ledger=L))
    try: type('Override',(n.ManagedConnection,),{})
    except TypeError: pass
    else: raise AssertionError('native subclass was not sealed')
    print('MANAGED_BODY_COMPLETE')
    """,
        native=True,
    )


def test_native_public_failure_boundary_preserves_first_baseexception_and_unknown():
    """Dependency fault injection only; no database history or real rollback pass."""
    body = """
    from modkit_events.persistence import native_sync as n
    """
    body = (
        textwrap.dedent(body)
        + _FIXTURE
        + textwrap.dedent("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    class Stop(BaseException): pass
    first=Stop('sentinel');cause=ValueError('primary cause')
    first.__cause__=cause;first.__suppress_context__=True
    calls=[]
    actual.pgconn.transaction_status=n.pq.TransactionStatus.INTRANS
    actual.pgconn.pipeline_status=n.pq.PipelineStatus.OFF
    def public_rollback(connection):
        assert connection is actual
        calls.append('rollback')
        raise first
    n.psycopg.Connection.rollback=public_rollback
    try: n.rollback(r,execution_ledger=L)
    except Stop as seen:
        assert seen is first and seen.__cause__ is cause and seen.__suppress_context__ is True
    else: raise AssertionError('original BaseException was replaced')
    assert calls==['rollback'] and L.uncertainty.present
    m.abandon_root(r,execution_ledger=L)
    assert m.capacity_snapshot(execution_ledger=L)['R']==1
    print('MANAGED_BODY_COMPLETE')
    """)
    )
    _run(body, native=True)


def test_native_primary_failure_survives_secondary_uncertainty_bookkeeping_failure():
    """Breaks if an exact-ledger cleanup failure replaces the original driver failure."""
    body = (
        textwrap.dedent("""
    from modkit_events.persistence import native_sync as n
    """)
        + _FIXTURE
        + textwrap.dedent("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    first=KeyboardInterrupt('first');cause=ValueError('cause')
    first.__cause__=cause;first.__suppress_context__=True
    actual.pgconn.transaction_status=n.pq.TransactionStatus.INTRANS
    actual.pgconn.pipeline_status=n.pq.PipelineStatus.OFF
    def failed_rollback(connection): raise first
    def failed_union(self,code): raise SystemExit('secondary')
    n.psycopg.Connection.rollback=failed_rollback
    ExecutionLedger.note_incident=failed_union
    try: n.rollback(r,execution_ledger=L)
    except KeyboardInterrupt as seen:
        assert seen is first and seen.__cause__ is cause and seen.__suppress_context__ is True
    else: raise AssertionError('primary was replaced')
    assert old._domain.stopped and m._counts['D']>=1
    print('MANAGED_BODY_COMPLETE')
    """)
    )
    _run(body, native=True)


def test_malformed_managed_handles_keep_explicit_context_without_record_lookup():
    """Breaks if missing payload records fabricate false uncertainty or leak AttributeError."""
    _run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    L.note_incident(E.OUTCOME_UNKNOWN)
    bad=object()
    cases=(lambda:m.dispose_execution(bad,execution_ledger=L),
        lambda:m.reserve_preparation(bad,8,execution_ledger=L),
        lambda:m.set_preparation(bad,b'x',execution_ledger=L),
        lambda:m.release_preparation(bad,execution_ledger=L),
        lambda:m.admit(bad,bad,execution_ledger=L),
        lambda:m.validate_ticket(bad,execution_ledger=L),
        lambda:m.release_ticket(bad,execution_ledger=L),
        lambda:m.reserve_result(bad,8,execution_ledger=L),
        lambda:m.set_result(bad,b'x',execution_ledger=L),
        lambda:m.release_result(bad,execution_ledger=L),
        lambda:m.abandon_root(bad,execution_ledger=L),
        lambda:m.release_root(bad,execution_ledger=L),
        lambda:m.retire(bad,execution_ledger=L),
        lambda:m.prepare_cleanup(bad,execution_ledger=L),
        lambda:m.reserve_cleanup(bad,8,execution_ledger=L),
        lambda:m.pin_cleanup(bad,execution_ledger=L),
        lambda:m.acknowledge_physical_close(bad,execution_ledger=L),
        lambda:m.release_cleanup(bad,execution_ledger=L),
        lambda:m.detach_terminal(bad,execution_ledger=L),
        lambda:m.acknowledge_root_end(bad,execution_ledger=L))
    for action in cases: expect(E.LOCAL_INVALID_ARGUMENT,action,True)
    assert m.capacity_snapshot(execution_ledger=L)==dict.fromkeys(m._names,0)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_startup_mode_linearizes_before_generic_t1_publication():
    """A caller paused after route selection must obey the winning locked mode."""
    _run("""
    import threading
    L=ExecutionLedger();entered=threading.Event();resume=threading.Event();observed=[]
    original=old._CellState
    def paused_candidate(actual):
        entered.set();assert resume.wait(5)
        return original(actual)
    old._CellState=paused_candidate
    class Plain:
        def __hash__(self):raise AssertionError('hash')
        def __eq__(self,other):raise AssertionError('eq')
        def __getattr__(self,name):raise AssertionError('getattr')
    actual=Plain()
    def lookup():
        try:observed.append(old.resource_cell(actual,execution_ledger=L))
        except PersistenceError as error:observed.append(error.code)
    worker=threading.Thread(target=lookup);worker.start();assert entered.wait(5)
    m.configure_managed_registry(limits=limits(),execution_ledger=L)
    resume.set();worker.join(5);assert not worker.is_alive()
    assert observed==[E.PROFILE_REJECTED],observed
    assert old._cells=={} and old._mode=='MANAGED'
    assert m.capacity_snapshot(execution_ledger=L)==dict.fromkeys(m._names,0)
    print('MANAGED_BODY_COMPLETE')
    """)
    _run("""
    import threading
    L=ExecutionLedger()
    expect(E.PROFILE_REJECTED,lambda:old.resource_cell(object(),execution_ledger=L))
    assert old._cells=={} and old._mode is None
    entered=threading.Event();resume=threading.Event();observed=[]
    original=old._CellState
    def paused_candidate(actual):
        entered.set();assert resume.wait(5)
        return original(actual)
    old._CellState=paused_candidate
    actual=object()
    def lookup():observed.append(old.resource_cell(actual,execution_ledger=L))
    worker=threading.Thread(target=lookup);worker.start();assert entered.wait(5)
    old.configure_registry(retained_cell_limit=2,execution_ledger=L)
    expect(E.PROFILE_REJECTED,lambda:m.configure_managed_registry(limits=limits(),execution_ledger=L))
    resume.set();worker.join(5);assert not worker.is_alive()
    assert len(observed)==1 and type(observed[0]) is old.ResourceCell
    assert old._cells[id(actual)].resource is actual and old._mode=='T1'
    assert m._counts==dict.fromkeys(m._names,0)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_bind_initial_rechecks_managed_mode_after_paused_candidate():
    """Private inert cell fixture exercises the analogous preconfiguration route."""
    _run("""
    import threading
    L=ExecutionLedger();entered=threading.Event();resume=threading.Event();observed=[]
    cell=old._issue(old.ResourceCell,_key=1)
    original=old._issue
    def paused_issue(kind,**fields):
        if kind is old.ResourceAssociation:
            entered.set();assert resume.wait(5)
        return original(kind,**fields)
    old._issue=paused_issue
    def bind():
        try:observed.append(old.bind_initial(cell,checkout_witness=object(),root_witness=object(),execution_ledger=L))
        except PersistenceError as error:observed.append(error.code)
    worker=threading.Thread(target=bind);worker.start();assert entered.wait(5)
    m.configure_managed_registry(limits=limits(),execution_ledger=L)
    resume.set();worker.join(5);assert not worker.is_alive()
    assert observed==[E.PROFILE_REJECTED],observed
    assert old._cells=={} and m.capacity_snapshot(execution_ledger=L)==dict.fromkeys(m._names,0)
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("issuer", ("start", "rollback", "commit", "close"))
def test_escaping_native_primary_keeps_charged_error_frames(issuer):
    """Dependency faults certify accounting/metadata only, never physical outcomes."""
    body = (
        textwrap.dedent("""
    from modkit_events.persistence import native_sync as n
    """)
        + _FIXTURE
        + "\nissuer="
        + repr(issuer)
        + "\n"
        + textwrap.dedent("""
    L,x,actual,c=setup_physical()
    actual.pgconn.pipeline_status=n.pq.PipelineStatus.OFF
    class Cancel(BaseException):pass
    first=Cancel('first');cause=ValueError('cause');context=LookupError('context')
    first.__cause__=cause;first.__context__=context;first.__suppress_context__=False
    cursors=[];retained=[]
    class ControlCursor:
        def __init__(self,connection,**kwargs):self.actual=connection;cursors.append(self)
        def execute(self,*args,**kwargs):
            retained_actual=self.actual
            raise first
        def close(self):pass
    def failed_public_call(connection):
        retained_actual=connection
        raise first
    if issuer=='start':
        n.psycopg.Cursor=ControlCursor
        invoke=lambda:n.start_root(c,execution_ledger=L)
        r=None
    elif issuer in ('rollback','commit'):
        r=active_root(c,L);actual.pgconn.transaction_status=n.pq.TransactionStatus.INTRANS
        if issuer=='rollback':n.psycopg.Connection.rollback=failed_public_call
        else:n.psycopg.Cursor=ControlCursor
        invoke=lambda:getattr(n,issuer)(r,execution_ledger=L)
    else:
        r=None;m.retire(c,execution_ledger=L)
        intent=m.prepare_cleanup(c,execution_ledger=L)
        reservation=m.reserve_cleanup(intent,16,execution_ledger=L)
        permit=m.pin_cleanup(reservation,execution_ledger=L)
        n.psycopg.Connection.close=failed_public_call
        invoke=lambda:n.close(permit,execution_ledger=L)
    try:invoke()
    except Cancel as error:
        assert error is first and error.__cause__ is cause and error.__context__ is context
        assert error.__suppress_context__ is False
        retained.append(error)
    else:raise AssertionError('primary replaced')
    frames=[];tb=retained[0].__traceback__
    while tb is not None:frames.append(tb.tb_frame);tb=tb.tb_next
    assert any(any(value is actual for value in frame.f_locals.values()) for frame in frames)
    if issuer in ('start','commit'):
        assert cursors and any(any(value is cursors[0] for value in frame.f_locals.values()) for frame in frames)
    assert L.uncertainty.present
    assert m.capacity_snapshot(execution_ledger=L)['D']>=1,'escaping traceback was uncharged'
    assert old._domain.stopped,'error-frame containment did not stop domain'
    if issuer in ('rollback','commit'):
        m.abandon_root(r,execution_ledger=L);m.retire(c,execution_ledger=L)
        intent=m.prepare_cleanup(c,execution_ledger=L)
        reservation=m.reserve_cleanup(intent,16,execution_ledger=L)
        permit=m.pin_cleanup(reservation,execution_ledger=L)
        def normal_public_close(connection):connection.closed=True
        n.psycopg.Connection.close=normal_public_close
        closed=n.close(permit,execution_ledger=L)
        m.acknowledge_physical_close(closed,execution_ledger=L)
        m.release_root(r,execution_ledger=L);m.release_cleanup(reservation,execution_ledger=L)
        m.detach_terminal(c,execution_ledger=L);m.dispose_execution(x,execution_ledger=L)
        counts=m.capacity_snapshot(execution_ledger=L)
        assert counts['D']>=1 and all(value==0 for name,value in counts.items() if name!='D')
        assert retained[0] is first and actual is not None
    print('MANAGED_BODY_COMPLETE')
    """)
    )
    _run(body, native=True)


def test_blocked_root_latch_avoids_locked_generator_or_view_entry():
    """An instrumented roster detects package-controlled reentry before any deadlock."""
    _run_fixture("""
    import ast,inspect
    L,x,actual,c=setup_physical();attempts=[]
    class ReentrantRoster(dict):
        def values(self):
            attempts.append('values')
            assert not old._lock.locked(),'roster view/callback entered under registry lock'
            m.capacity_snapshot(execution_ledger=L)
            return super().values()
    p=old._cells[c._key];p.roots=ReentrantRoster(p.roots)
    r=active_root(c,L)
    m.abandon_root(r,execution_ledger=L)
    assert p.blocked_root is True
    with m._construction(True):
        refused,code=m._reserve_root(c,L)
        assert code is E.PROFILE_REJECTED
    assert attempts==[] and m.capacity_snapshot(execution_ledger=L)['R']==1
    tree=ast.parse(inspect.getsource(m._reserve_root))
    assert not any(isinstance(node,ast.GeneratorExp) for node in ast.walk(tree))
    assert not any(isinstance(node,ast.Attribute) and node.attr=='values' for node in ast.walk(tree))
    print('MANAGED_BODY_COMPLETE')
    """)


_COMMIT_FIXTURE = (
    """
from modkit_events.persistence import native_sync as n
"""
    + _FIXTURE
    + """
L,x,actual,c=setup_physical();r=active_root(c,L)
actual.pgconn.transaction_status=n.pq.TransactionStatus.INTRANS
actual.pgconn.pipeline_status=n.pq.PipelineStatus.OFF
calls=[];cursors=[]
tag=b'COMMIT';message='COMMIT';status=n.pq.ExecStatus.COMMAND_OK
extra=None;post=n.pq.TransactionStatus.IDLE;phase=None;secondary=False
first=KeyboardInterrupt('primary');cause=ValueError('cause');context=LookupError('context')
first.__cause__=cause;first.__context__=context;first.__suppress_context__=False

def fault(at):
    if phase==at:raise first

# Deliberately inject resource-retaining observation frames; this is not
# an assertion about real driver PGresult Python frames. S2 must hold them.
class PublicResult:
    def __init__(self,cursor):self.cursor=cursor
    @property
    def status(self):
        retained_cursor=self.cursor;retained_actual=retained_cursor.actual
        fault('status');return status
    @property
    def command_status(self):
        retained_cursor=self.cursor;retained_actual=retained_cursor.actual
        fault('tag');return tag

class ControlCursor:
    def __init__(self,connection,**kwargs):
        assert connection is actual and kwargs=={'row_factory':n.tuple_row}
        self.actual=connection;cursors.append(self);calls.append('cursor');fault('construct')
    def execute(self,sql,**kwargs):
        retained_actual=self.actual
        assert sql=='COMMIT' and kwargs=={'prepare':False}
        assert m._counts['D']>=1
        expect(E.INVALID_OBSERVATION,lambda:m.admit(r,prep,execution_ledger=L),L.uncertainty.present)
        expect(E.RESOURCE_BUSY,lambda:n.start_root(c,execution_ledger=L),L.uncertainty.present)
        calls.append('execute');fault('execute')
        self.actual.pgconn.transaction_status=post
        return self
    @property
    def pgresult(self):fault('pgresult');return PublicResult(self) if status is not None else None
    @property
    def statusmessage(self):fault('message');return message
    def nextset(self):calls.append('nextset');fault('nextset');return extra
    def close(self):
        calls.append('close')
        if secondary:raise SystemExit('secondary close')
        fault('close')

prep=m.reserve_preparation(x,1,execution_ledger=L)
m.set_preparation(prep,b'x',execution_ledger=L)
n.psycopg.Cursor=ControlCursor

def forbidden_commit(connection):raise AssertionError('Connection.commit discarded command tag')
n.psycopg.Connection.commit=forbidden_commit
"""
)


@pytest.mark.parametrize("rolled_back", (False, True))
def test_commit_response_outcome_exact_echo_and_stale_receipt(rolled_back):
    """Old Connection.commit path or generic rollback echo cannot satisfy this."""
    _run(
        _COMMIT_FIXTURE
        + "\nrolled_back="
        + repr(rolled_back)
        + "\n"
        + textwrap.dedent("""
    if rolled_back:
        tag=b'ROLLBACK';message='ROLLBACK'
        actual.pgconn.transaction_status=n.pq.TransactionStatus.INERROR
        L.note_incident(E.DATABASE_FAILURE)
    receipt=n.commit(r,execution_ledger=L)
    expected=m.CommitOutcome.ABORTED_COMMIT_ROLLED_BACK if rolled_back else m.CommitOutcome.COMMITTED
    assert type(receipt) is m.CommitResultReceipt
    assert receipt._kind=='COMMIT_RESULT' and not hasattr(receipt,'__dict__')
    assert calls==['cursor','execute','nextset','close']
    before=m.capacity_snapshot(execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m.acknowledge_root_end(receipt,execution_ledger=L),rolled_back)
    expect(E.INVALID_OBSERVATION,lambda:m.acknowledge_commit_result(receipt,execution_ledger=ExecutionLedger()))
    forged=m._handle('COMMIT_RESULT',receipt._key,receipt._pstamp,receipt._subject)
    expect(E.INVALID_OBSERVATION,lambda:m.acknowledge_commit_result(forged,execution_ledger=L),rolled_back)
    expect(E.INVALID_OBSERVATION,lambda:m.admit(r,prep,execution_ledger=L),rolled_back)
    assert m.acknowledge_commit_result(receipt,execution_ledger=L) is expected
    assert m.acknowledge_commit_result(receipt,execution_ledger=L) is expected
    expect(E.INVALID_OBSERVATION,lambda:m.acknowledge_root_end(receipt,execution_ledger=L),rolled_back)
    assert m.capacity_snapshot(execution_ledger=L)==before
    assert L.uncertainty.present is rolled_back and not old._domain.stopped
    # Successor gate is independent of replaying an older already-ACKed receipt.
    successor=active_root(c,L)
    assert m.acknowledge_commit_result(receipt,execution_ledger=L) is expected
    ticket=m.admit(successor,prep,execution_ledger=L)
    m.release_ticket(ticket,execution_ledger=L)
    m.release_root(r,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m.acknowledge_commit_result(receipt,execution_ledger=L),rolled_back)
    assert calls==['cursor','execute','nextset','close']
    print('MANAGED_BODY_COMPLETE')
    """),
        native=True,
    )


@pytest.mark.parametrize("invalid", ("missing", "status", "tag", "message", "extra", "post"))
def test_commit_response_incomplete_observation_stays_unknown(invalid):
    """Removing a result/postcheck must not grant known root-end authority."""
    _run(
        _COMMIT_FIXTURE
        + "\ninvalid="
        + repr(invalid)
        + "\n"
        + textwrap.dedent("""
    if invalid=='missing':status=None
    if invalid=='status':status=n.pq.ExecStatus.TUPLES_OK
    if invalid=='tag':tag=b'UPDATE 1'
    if invalid=='message':message='ROLLBACK'
    if invalid=='extra':extra=True
    if invalid=='post':post=n.pq.TransactionStatus.INTRANS
    expect(E.OUTCOME_UNKNOWN,lambda:n.commit(r,execution_ledger=L),True)
    assert L.uncertainty.present and not old._domain.stopped
    assert calls.count('execute')==1 and calls[-1]=='close'
    p,record=m._root(r,L)
    assert record['state']=='UNKNOWN' and p.blocked_root and not p.operation['running']
    assert record['commit_outcome'] is None
    if invalid in ('message','extra','post'):
        assert record['observed_commit_tag'] is m.CommitOutcome.COMMITTED
    expect(E.INVALID_OBSERVATION,lambda:n.commit(r,execution_ledger=L),True)
    assert calls.count('execute')==1
    print('MANAGED_BODY_COMPLETE')
    """),
        native=True,
    )


@pytest.mark.parametrize(
    "failed_phase",
    ("construct", "execute", "pgresult", "status", "tag", "message", "nextset", "close"),
)
def test_commit_response_primary_frames_and_late_tag_are_held(failed_phase):
    """Every public-control failure keeps the first primary and charged frames."""
    _run(
        _COMMIT_FIXTURE
        + "\nphase="
        + repr(failed_phase)
        + "\n"
        + textwrap.dedent("""
    secondary=phase=='execute'
    retained=[]
    try:n.commit(r,execution_ledger=L)
    except KeyboardInterrupt as seen:
        assert seen is first and seen.__cause__ is cause and seen.__context__ is context
        assert seen.__suppress_context__ is False
        retained.append(seen)
    else:raise AssertionError('primary replaced or swallowed')
    assert old._domain.stopped and m._counts['D']>=1 and L.uncertainty.present
    p,record=m._root(r,L)
    assert record['state']=='UNKNOWN' and p.blocked_root and not p.operation['running']
    if phase in ('message','nextset','close'):
        assert record['observed_commit_tag'] is m.CommitOutcome.COMMITTED
    assert record['commit_outcome'] is None
    frames=[];tb=retained[0].__traceback__
    while tb is not None:frames.append(tb.tb_frame);tb=tb.tb_next
    assert any(any(value is actual for value in frame.f_locals.values()) for frame in frames)
    assert cursors and any(any(value is cursors[0] for value in frame.f_locals.values()) for frame in frames)
    expect(E.INVALID_OBSERVATION,lambda:m.acknowledge_commit_result(record['receipt'],execution_ledger=L),True)
    assert m._counts['D']>=1
    print('MANAGED_BODY_COMPLETE')
    """),
        native=True,
    )


def test_commit_response_secondary_publication_failure_preserves_first_primary():
    _run(
        _COMMIT_FIXTURE
        + textwrap.dedent("""
    phase='close'
    def failed_union(self,code):raise SystemExit('secondary publication')
    ExecutionLedger.note_incident=failed_union
    try:n.commit(r,execution_ledger=L)
    except KeyboardInterrupt as seen:
        assert seen is first and seen.__cause__ is cause and seen.__context__ is context
        assert seen.__suppress_context__ is False
    else:raise AssertionError('secondary replaced primary')
    assert old._domain.stopped and m._counts['D']>=1
    p,record=m._root(r,L)
    assert record['observed_commit_tag'] is m.CommitOutcome.COMMITTED
    assert record['commit_outcome'] is None
    print('MANAGED_BODY_COMPLETE')
    """),
        native=True,
    )


def test_commit_response_lost_return_cannot_reissue_or_reconstruct():
    _run(
        _COMMIT_FIXTURE
        + textwrap.dedent("""
    n.commit(r,execution_ledger=L)  # Deliberately discard the only returned receipt.
    expect(E.INVALID_OBSERVATION,lambda:n.commit(r,execution_ledger=L))
    assert calls.count('execute')==1 and m._counts['R']==1
    m.abandon_root(r,execution_ledger=L)
    assert L.uncertainty.present and m._counts['R']==1
    expect(E.PROFILE_REJECTED,lambda:n.start_root(c,execution_ledger=L),True)
    print('MANAGED_BODY_COMPLETE')
    """),
        native=True,
    )


@pytest.mark.parametrize("unsupported", ("idle", "pipeline", "autocommit", "closed"))
def test_commit_response_observable_preconditions_reject_before_command(unsupported):
    _run(
        _COMMIT_FIXTURE
        + "\nunsupported="
        + repr(unsupported)
        + "\n"
        + textwrap.dedent("""
    if unsupported=='idle':actual.pgconn.transaction_status=n.pq.TransactionStatus.IDLE
    if unsupported=='pipeline':actual.pgconn.pipeline_status=n.pq.PipelineStatus.ON
    if unsupported=='autocommit':actual.autocommit=True
    if unsupported=='closed':actual.closed=True
    expect(E.PROFILE_REJECTED,lambda:n.commit(r,execution_ledger=L),True)
    assert calls==[] and L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """),
        native=True,
    )
