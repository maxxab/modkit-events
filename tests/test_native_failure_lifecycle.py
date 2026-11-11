"""Pure lifecycle/probe fault injection; no database qualification."""

import textwrap

import pytest
from test_managed_lifecycle import _FIXTURE, _run
from test_managed_statement_lifecycle import _SETUP

_PROVENANCE = """
from uuid import UUID
from modkit_events.persistence.models import Fence
def issue(r,x,L,key,params,value,context=None):
    req=B._freeze_request_raw(C.get_statement(key),params,
        context=B._return_context_raw() if context is None else context)
    a=m.reserve_preparation(x,65536,execution_ledger=L)
    m.set_preparation(a,req,execution_ledger=L)
    t=m.admit(r,a,execution_ledger=L)
    b=m.reserve_result(t,4096,execution_ledger=L)
    with m._construction(False) as paid:
        m._start_operation(t,b,L,reservation=paid)
        m.set_result(b,value,execution_ledger=L)
        m._complete_operation(t,L,known=True)
        m.validate_ticket(t,execution_ledger=L)
        m._observe_native_result_paid(t,b,L,paid)
    m.release_result(b,execution_ledger=L)
    m.release_ticket(t,execution_ledger=L)
    m.release_preparation(a,execution_ledger=L)
def arm(r,x,L,xid=17):
    f=Fence(work_id=UUID(int=1),token=UUID(int=2),ownership_revision=3,
        cycle=1,expected_attempt=1)
    issue(r,x,L,'E14',(),xid)
    row=O.GuardRow(guard_id=UUID(int=4),work_id=f.work_id,root_xid=xid,
        token=f.token,ownership_revision=f.ownership_revision,cycle=f.cycle,
        expected_attempt=f.expected_attempt,satisfied=False,
        final_fence_at=None,terminal_state=None,result_digest=None)
    params=(f.work_id,f.token,f.ownership_revision,f.cycle,f.expected_attempt)
    issue(r,x,L,'E08',params,row,B._return_context_raw(expected=(f,)))
    return f
"""


def run(body):
    _run(_FIXTURE + _SETUP + _PROVENANCE + textwrap.dedent(body))


def test_native_witness_is_fixed_and_ordinary_rollback_is_not_proof():
    run("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    f=arm(r,x,L)
    p,record=m._root(r,L)
    assert record['failure_xid']==17
    assert record['failure_fence']==(1,2,3,1,1)
    assert record['failure_eligible'] and not record['failure_verified']
    with m._construction(False):
        op,receipt,code=m._reserve_rollback(r,L)
        assert code is None
        m._complete_rollback(r,L,known=True)
    m.acknowledge_root_end(receipt,execution_ledger=L)
    assert not record['failure_verified']
    print('MANAGED_BODY_COMPLETE')
    """)


def test_missing_witness_strict_preflight_leaves_root_unchanged():
    run("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    before=m.capacity_snapshot(execution_ledger=L)
    with m._construction(False):
        xid,code=m._failure_rollback_preflight(r,L,uncertain=False)
    assert xid is None and code is E.INVALID_OBSERVATION
    assert m._root(r,L)[1]['state']=='ACTIVE'
    assert m.capacity_snapshot(execution_ledger=L)==before
    print('MANAGED_BODY_COMPLETE')
    """)


def test_wrapper_rejects_nonbool_without_importing_driver_or_charging():
    run("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    class Truth:
        def __bool__(self):raise AssertionError('truthiness')
    before=m.capacity_snapshot(execution_ledger=L)
    for value in (0,1,None,Truth()):
        expect(E.LOCAL_INVALID_ARGUMENT,
            lambda:r.rollback(execution_ledger=L,confirm_failure=value))
    assert 'modkit_events.persistence.native_sync' not in sys.modules
    assert m.capacity_snapshot(execution_ledger=L)==before
    print('MANAGED_BODY_COMPLETE')
    """)


_FAKE = """
from types import ModuleType, SimpleNamespace
from enum import IntEnum
pg=ModuleType('psycopg');pg.__version__='3.3.8'
class TS(IntEnum):
    IDLE=0; ACTIVE=1; INTRANS=2; INERROR=3; UNKNOWN=4
class PS(IntEnum):
    OFF=0
class ES(IntEnum):
    COMMAND_OK=1; TUPLES_OK=2
pg.pq=SimpleNamespace(TransactionStatus=TS,PipelineStatus=PS,ExecStatus=ES)
class Connection:
    calls=0
    def __init__(self,pgconn,row_factory=None):
        self.pgconn=pgconn;self.closed=False;self.autocommit=False
    def rollback(self):
        Connection.calls+=1
        if rollback_error is not None:raise rollback_error
        self.pgconn.transaction_status=post_status
pg.Connection=Connection
rows=ModuleType('psycopg.rows');rows.tuple_row=object()
sys.modules.update({'psycopg':pg,'psycopg.rows':rows})
from modkit_events.persistence import native_sync as n
class Result:
    status=ES.TUPLES_OK;ntuples=1;nfields=1;binary_tuples=1
    command_status=b'SELECT 1';command_tuples=1
    def fname(self,i):return b'pg_current_xact_id_if_assigned'
    def ftype(self,i):return 5069
    def fformat(self,i):return 1
    def fsize(self,i):return 8
    def get_value(self,r,c):return probe_value
class Cursor:
    instances=[];calls=[]
    def __init__(self,actual,*,row_factory):
        assert row_factory is rows.tuple_row
        self.pgresult=Result();self.rowcount=1;self.statusmessage='SELECT 1'
        self.closed=False;Cursor.instances.append(self)
    def execute(self,sql,*,prepare,binary):
        Cursor.calls.append((sql,prepare,binary))
        if probe_error is not None:raise probe_error
    def nextset(self):return extra
    def close(self):
        if close_error is not None:raise close_error
        self.closed=True
pg.Cursor=Cursor
probe_value=(17).to_bytes(8,'big');probe_error=close_error=rollback_error=None
extra=None;post_status=TS.IDLE
def setup_physical():
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L)
    actual=n.ManagedConnection(SimpleNamespace(transaction_status=TS.IDLE,pipeline_status=PS.OFF))
    c=m.attach_native(actual,x,execution_ledger=L)
    return L,x,actual,c
def active_root(c,L):
    with m._construction(False):
        r,code=m._reserve_root(c,L);assert code is None
        m._physical(c,L).resource.pgconn.transaction_status=TS.INTRANS
        m._complete_start(r,L,known=True)
    return r
"""
_BIND = """
def failure_request(f,**changes):
    params=(f.work_id,f.token,f.ownership_revision,f.cycle,f.expected_attempt,
        17,'failed',None,'local',b'evidence')
    params=tuple(changes.get(i,v) for i,v in enumerate(params))
    return B._freeze_request_raw(C.get_statement('E11'),params,
        context=B._return_context_raw(expected=(f,)))
def prepare_failure(x,L,f,capacity=65536):
    req=failure_request(f)
    a=m.reserve_preparation(x,capacity,execution_ledger=L)
    m.set_preparation(a,req,execution_ledger=L)
    return a,req
def rolled_back():
    L,x,actual,c=setup_physical();r=active_root(c,L);f=arm(r,x,L)
    receipt=n.rollback(r,execution_ledger=L,confirm_failure=True)
    m.acknowledge_root_end(receipt,execution_ledger=L)
    return L,x,actual,c,r,f,receipt
"""


def native_run(body):
    _run(_SETUP + _FAKE + _PROVENANCE + _BIND + textwrap.dedent(body))


def test_strict_probe_precedes_actual_rollback_and_preserves_paid_root():
    native_run("""
    L,x,actual,c,r,f,receipt=rolled_back()
    assert Cursor.calls==[('SELECT pg_catalog.pg_current_xact_id_if_assigned()',False,True)]
    assert Cursor.instances[0].closed and Connection.calls==1
    assert m._root(r,L)[1]['failure_verified']
    assert m._counts['R']==1 and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize(
    "change",
    [
        "probe_value=(18).to_bytes(8,'big')",
        "probe_value=None",
        "probe_value=b'123'",
        "Result.ftype=lambda s,i:20",
        "Result.ntuples=2",
        "Result.fname=lambda s,i:b'other'",
        "Result.fformat=lambda s,i:0",
        "Result.fsize=lambda s,i:4",
        "Result.command_tuples=2",
        "Result.command_status=b'SELECT 2'",
        "extra=True",
        "probe_value=bytes(8)",
    ],
)
def test_bad_probe_never_rolls_back_or_mints_proof(change):
    native_run(
        change
        + """
L,x,actual,c=setup_physical();r=active_root(c,L);arm(r,x,L)
expect(E.INVALID_OBSERVATION,lambda:n.rollback(r,execution_ledger=L,confirm_failure=True),True)
record=m._root(r,L)[1]
assert record['state']=='UNKNOWN' and not record['failure_verified']
assert Connection.calls==0 and L.uncertainty.present and m._counts['D']>=1
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_known_inerror_preflight_does_not_query_reserve_or_consume():
    native_run("""
    L,x,actual,c=setup_physical();r=active_root(c,L);arm(r,x,L)
    actual.pgconn.transaction_status=TS.INERROR
    before=m.capacity_snapshot(execution_ledger=L)
    expect(E.PROFILE_REJECTED,lambda:n.rollback(r,execution_ledger=L,confirm_failure=True))
    assert Cursor.calls==[] and Connection.calls==0
    assert m._root(r,L)[1]['state']=='ACTIVE'
    assert m.capacity_snapshot(execution_ledger=L)==before
    print('MANAGED_BODY_COMPLETE')
    """)


def test_false_post_idle_refunds_only_transient_d_not_unknown_root():
    native_run("""
    L,x,actual,c=setup_physical();r=active_root(c,L);arm(r,x,L)
    post_status=TS.INTRANS
    expect(E.OUTCOME_UNKNOWN,lambda:n.rollback(r,execution_ledger=L,confirm_failure=True),True)
    p,rec=m._root(r,L)
    assert rec['state']=='UNKNOWN' and p.blocked_root and not rec['failure_verified']
    assert m._counts['D']==0 and m._counts['R']==1 and p.operation is not None
    print('MANAGED_BODY_COMPLETE')
    """)


def test_binding_pins_root_and_atomic_start_consumes_forever():
    native_run("""
    L,x,actual,c,r,f,receipt=rolled_back()
    a,req=prepare_failure(x,L,f)
    m.bind_failure_settlement(a,r,receipt,execution_ledger=L)
    expect(E.RESOURCE_BUSY,lambda:m.release_root(r,execution_ledger=L))
    expect(E.INVALID_OBSERVATION,lambda:m.bind_failure_settlement(a,r,receipt,execution_ledger=L))
    rf=active_root(c,L);t=m.admit(rf,a,execution_ledger=L)
    b=m.reserve_result(t,64,execution_ledger=L)
    with m._construction(False) as paid:
        assert m._start_operation(t,b,L,reservation=paid) is req
        m.set_result(b,True,execution_ledger=L)
        m._complete_operation(t,L,known=True)
    assert m._root(r,L)[1]['failure_consumed']
    m.release_result(b,execution_ledger=L);m.release_ticket(t,execution_ledger=L)
    m.release_preparation(a,execution_ledger=L)
    a2,req2=prepare_failure(x,L,f)
    expect(E.INVALID_OBSERVATION,lambda:m.bind_failure_settlement(a2,r,receipt,execution_ledger=L))
    m.release_root(r,execution_ledger=L)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_unbound_e11_cannot_admit_and_prestart_release_allows_rebind():
    native_run("""
    L,x,actual,c,r,f,receipt=rolled_back()
    a,req=prepare_failure(x,L,f);rf=active_root(c,L)
    expect(E.INVALID_OBSERVATION,lambda:m.admit(rf,a,execution_ledger=L))
    m.bind_failure_settlement(a,r,receipt,execution_ledger=L)
    m.release_preparation(a,execution_ledger=L)
    a2,req2=prepare_failure(x,L,f)
    m.bind_failure_settlement(a2,r,receipt,execution_ledger=L)
    assert not m._root(r,L)[1]['failure_consumed']
    print('MANAGED_BODY_COMPLETE')
    """)


def test_binding_revalidates_replaced_parameters_before_start():
    native_run("""
    L,x,actual,c,r,f,receipt=rolled_back()
    a,req=prepare_failure(x,L,f)
    m.bind_failure_settlement(a,r,receipt,execution_ledger=L)
    rf=active_root(c,L);t=m.admit(rf,a,execution_ledger=L)
    b=m.reserve_result(t,64,execution_ledger=L)
    object.__setattr__(req,'parameters',tuple(list(req.parameters)))
    expect(E.INVALID_OBSERVATION,lambda:m._start_operation(t,b,L))
    assert not m._root(r,L)[1]['failure_consumed'] and Connection.calls==1
    print('MANAGED_BODY_COMPLETE')
    """)


def test_e09_without_prior_e08_cannot_establish_a_witness():
    run("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    f=arm(r,x,L)
    # Independently start another root with E14 then only E09.
    with m._construction(False):
        op,receipt,code=m._reserve_rollback(r,L)
        m._complete_rollback(r,L,known=True)
    m.acknowledge_root_end(receipt,execution_ledger=L)
    rf=active_root(c,L)
    issue(rf,x,L,'E14',(),17)
    row=O.GuardRow(guard_id=UUID(int=4),work_id=f.work_id,root_xid=17,
        token=f.token,ownership_revision=3,cycle=1,expected_attempt=1,
        satisfied=False,final_fence_at=None,terminal_state=None,result_digest=None)
    issue(rf,x,L,'E09',(f.work_id,f.token,3,1,1),row,B._return_context_raw(expected=(f,)))
    assert not m._root(rf,L)[1]['failure_eligible']
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("stage", ["probe", "close", "rollback"])
def test_strict_driver_error_preserves_primary_and_unknown(stage):
    native_run(
        """
    L,x,actual,c=setup_physical();r=active_root(c,L);arm(r,x,L)
    primary=KeyboardInterrupt('nonsecret');cause=ValueError('cause')
    primary.__cause__=cause;primary.__suppress_context__=True
    """
        + stage
        + """_error=primary
    try:n.rollback(r,execution_ledger=L,confirm_failure=True)
    except BaseException as caught:
        assert caught is primary and caught.__cause__ is cause and caught.__suppress_context__
    else:raise AssertionError('missing primary')
    assert m._root(r,L)[1]['state']=='UNKNOWN' and L.uncertainty.present
    assert not m._root(r,L)[1]['failure_verified'] and m._counts['D']>=1
    print('MANAGED_BODY_COMPLETE')
    """
    )


def test_ordinary_receipt_and_released_root_cannot_bind():
    native_run("""
    L,x,actual,c=setup_physical();r=active_root(c,L);f=arm(r,x,L)
    receipt=n.rollback(r,execution_ledger=L)
    m.acknowledge_root_end(receipt,execution_ledger=L)
    a,req=prepare_failure(x,L,f)
    expect(E.INVALID_OBSERVATION,lambda:m.bind_failure_settlement(a,r,receipt,execution_ledger=L))
    assert not Cursor.calls and Connection.calls==1
    m.release_root(r,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m.bind_failure_settlement(a,r,receipt,execution_ledger=L))
    assert m._counts['R']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_prior_uncertainty_never_becomes_failure_authority():
    native_run("""
    L,x,actual,c,r,f,receipt=rolled_back();a,req=prepare_failure(x,L,f)
    L.note_incident(E.OUTCOME_UNKNOWN)
    expect(E.PROFILE_REJECTED,lambda:m.bind_failure_settlement(a,r,receipt,execution_ledger=L),True)
    assert not m._root(r,L)[1]['failure_consumed'] and L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize(
    "mutation",
    [
        "object.__setattr__(req,'context',B._return_context_raw(expected=(f,)))",
        "object.__setattr__(req.context,'expected',tuple([f]))",
        "object.__setattr__(f.work_id,'int',99)",
        "object.__setattr__(f,'cycle',2)",
        "object.__setattr__(req,'parameters',req.parameters[:8]+('other',b'evidence'))",
        "object.__setattr__(req,'statement',C.get_statement('E14'))",
    ],
)
def test_proof_rejects_all_carrier_mutations_before_admission(mutation):
    native_run(
        """
L,x,actual,c,r,f,receipt=rolled_back();a,req=prepare_failure(x,L,f)
m.bind_failure_settlement(a,r,receipt,execution_ledger=L)
rf=active_root(c,L)
"""
        + mutation
        + """
expect(E.INVALID_OBSERVATION,lambda:m.admit(rf,a,execution_ledger=L))
assert not m._root(r,L)[1]['failure_consumed']
assert not old._domain.stopped
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_second_association_busy_and_prestart_release_drops_only_a_charge():
    native_run("""
    L,x,actual,c,r,f,receipt=rolled_back()
    a,req=prepare_failure(x,L,f);a2,req2=prepare_failure(x,L,f)
    m.bind_failure_settlement(a,r,receipt,execution_ledger=L)
    expect(E.RESOURCE_BUSY,lambda:m.bind_failure_settlement(a2,r,receipt,execution_ledger=L))
    before=m.capacity_snapshot(execution_ledger=L)
    m.release_preparation(a,execution_ledger=L)
    after=m.capacity_snapshot(execution_ledger=L)
    assert after['R']==before['R']==1 and after['A']==before['A']-1
    assert after['AB']==before['AB']-65536
    m.bind_failure_settlement(a2,r,receipt,execution_ledger=L)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_exact_and_one_byte_short_binding_capacity_count_snapshot_occurrences():
    native_run("""
    L,x,actual,c,r,f,receipt=rolled_back()
    req=failure_request(f)
    snapshot=m._failure_snapshot(req)
    dummy=m._FailureBinding(r,receipt,req,req.parameters,req.context,
        req.context.expected,f,snapshot)
    # Independent occurrence-based formula, counting nested timestamp fields.
    def scalar_size(v):
        return getsizeof(v)+(getsizeof(v.int) if type(v) is UUID else 0)
    raw=(getsizeof(req)+getsizeof(req.parameters)+sum(map(scalar_size,req.parameters))
        +getsizeof(req.context)+getsizeof(req.context.expected)+getsizeof(f)
        +sum(scalar_size(getattr(f,k)) for k in f.__dataclass_fields__))
    snap=getsizeof(snapshot)+sum(getsizeof(v)+(
        sum(getsizeof(k) for k in v) if type(v) is tuple else 0) for v in snapshot)
    exact=2*raw+getsizeof(dummy)+snap
    assert exact==m._failure_binding_size(req,dummy)
    a=m.reserve_preparation(x,exact-1,execution_ledger=L)
    m.set_preparation(a,req,execution_ledger=L)
    expect(E.CAPACITY_EXCEEDED,lambda:m.bind_failure_settlement(a,r,receipt,execution_ledger=L))
    assert m._root(r,L)[1]['failure_preparation'] is None
    m.release_preparation(a,execution_ledger=L)
    a=m.reserve_preparation(x,exact,execution_ledger=L)
    m.set_preparation(a,req,execution_ledger=L)
    m.bind_failure_settlement(a,r,receipt,execution_ledger=L)
    assert m._counts['AB']==exact
    print('MANAGED_BODY_COMPLETE')
    """)


def test_max_domain_snapshot_bound_and_aliases_are_occurrences():
    run("""
    U=UUID(int=2**128-1)
    f=Fence(work_id=U,token=U,ownership_revision=2**63-1,cycle=1,expected_attempt=1000)
    req=B._freeze_request_raw(C.get_statement('E11'),
        (U,U,2**63-1,1,1000,2**64-1,'retry_waiting',
         datetime(9999,12,31,23,59,59,999999,tzinfo=timezone.utc),'r'*256,b'e'*1048576),
        context=B._return_context_raw(expected=(f,)))
    snap=m._failure_snapshot(req)
    dummy=m._FailureBinding(None,None,req,req.parameters,req.context,
        req.context.expected,f,snap)
    assert snap[0]==snap[1]==2**128-1 and snap[5]==2**64-1
    assert len(snap[7])==8 and len(snap[9])==1048576
    assert m._failure_binding_size(req,dummy)<=4194304
    # Aliased UUID occurrences must not collapse into one retained scalar charge.
    assert m._snapshot_size(snap)==getsizeof(snap)+sum(
        getsizeof(v)+(sum(map(getsizeof,v)) if type(v) is tuple else 0) for v in snap)
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("key,value", [("E14", 18), ("E09", None)])
def test_contradictory_observation_disables_only_proof(key, value):
    run(
        """
    L,x,actual,c=setup_physical();r=active_root(c,L);f=arm(r,x,L)
    """
        + (
            "issue(r,x,L,'E14',(),18)"
            if key == "E14"
            else "issue(r,x,L,'E09',(f.work_id,f.token,3,1,1),None,B._return_context_raw(expected=(f,)))"
        )
        + """
    rec=m._root(r,L)[1]
    assert rec['failure_disabled'] and not rec['failure_eligible']
    assert rec['state']=='ACTIVE' and not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """
    )


def test_native_boundary_rejects_nonbool_before_d_or_driver():
    native_run("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    class Truth:
        def __bool__(self):raise AssertionError('truthiness invoked')
    before=m.capacity_snapshot(execution_ledger=L)
    for value in (0,1,None,Truth()):
        expect(E.LOCAL_INVALID_ARGUMENT,
            lambda:n.rollback(r,execution_ledger=L,confirm_failure=value))
    assert m.capacity_snapshot(execution_ledger=L)==before
    assert Cursor.calls==[] and Connection.calls==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_preflight_accessor_error_contains_without_reserving_rollback():
    native_run("""
    L,x,actual,c=setup_physical();r=active_root(c,L);arm(r,x,L)
    primary=RuntimeError('nonsecret')
    class BrokenPG:
        pipeline_status=PS.OFF
        @property
        def transaction_status(self):raise primary
    broken=BrokenPG()
    actual.pgconn=broken;m._physical(c,L).pgconn=broken
    try:n.rollback(r,execution_ledger=L,confirm_failure=True)
    except BaseException as caught:assert caught is primary
    else:raise AssertionError('missing')
    physical,record=m._root(r,L)
    assert record['state']=='UNKNOWN' and physical.operation is None
    assert physical.blocked_root and L.uncertainty.present and m._counts['D']>=1
    assert Cursor.calls==[] and Connection.calls==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_wrong_physical_or_ledger_and_root_receipt_are_rejected():
    native_run("""
    L,x,actual,c,r,f,receipt=rolled_back();a,req=prepare_failure(x,L,f)
    other=ExecutionLedger()
    expect(E.INVALID_OBSERVATION,lambda:m.bind_failure_settlement(a,r,receipt,execution_ledger=other))
    forged=m._handle('ROOT_END',r._key,r._pstamp,r._stamp)
    expect(E.INVALID_OBSERVATION,lambda:m.bind_failure_settlement(a,r,forged,execution_ledger=L))
    m.bind_failure_settlement(a,r,receipt,execution_ledger=L)
    actual2=n.ManagedConnection(SimpleNamespace(transaction_status=TS.IDLE,pipeline_status=PS.OFF))
    c2=m.attach_native(actual2,x,execution_ledger=L);rf=active_root(c2,L)
    expect(E.INVALID_OBSERVATION,lambda:m.admit(rf,a,execution_ledger=L))
    assert not m._root(r,L)[1]['failure_consumed']
    print('MANAGED_BODY_COMPLETE')
    """)


def test_public_result_without_live_issuer_cannot_publish_native_witness():
    run("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    req=request();a=m.reserve_preparation(x,4096,execution_ledger=L)
    m.set_preparation(a,req,execution_ledger=L);t=m.admit(r,a,execution_ledger=L)
    b=m.reserve_result(t,64,execution_ledger=L)
    m._start_operation(t,b,L)
    m.set_result(b,17,execution_ledger=L);m._complete_operation(t,L,known=True)
    with m._construction(False) as paid:
        try:m._observe_native_result_paid(t,b,L,paid)
        except PersistenceError as error:assert error.code is E.INVALID_OBSERVATION
        else:raise AssertionError('synthetic issuer accepted')
    assert m._root(r,L)[1]['failure_xid'] is None
    print('MANAGED_BODY_COMPLETE')
    """)


def test_fixed_root_witness_maximum_occurrence_bound():
    run("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    U=UUID(int=2**128-1)
    f=Fence(work_id=U,token=U,ownership_revision=2**63-1,cycle=1,expected_attempt=1000)
    issue(r,x,L,'E14',(),2**64-1)
    row=O.GuardRow(guard_id=U,work_id=U,root_xid=2**64-1,token=U,
        ownership_revision=2**63-1,cycle=1,expected_attempt=1000,satisfied=False,
        final_fence_at=None,terminal_state=None,result_digest=None)
    issue(r,x,L,'E08',(U,U,2**63-1,1,1000),row,B._return_context_raw(expected=(f,)))
    rec=m._root(r,L)[1]
    witness={k:v for k,v in rec.items() if k.startswith('failure_')}
    def size(v):return getsizeof(v)+(sum(map(size,v)) if type(v) is tuple else 0)
    assert getsizeof(witness)+sum(getsizeof(k)+size(v) for k,v in witness.items())<=4096
    assert all(type(v) in (int,bool,tuple,type(None)) for v in witness.values())
    assert m._counts['R']==1
    print('MANAGED_BODY_COMPLETE')
    """)
