"""Structural issuer fixtures; not native-driver acceptance."""

import textwrap

import pytest
from test_managed_lifecycle import _run
from test_managed_statement_lifecycle import _SETUP
from test_native_execution import _DRIVER

_COMPLETION = """
class Int8BinaryDumper: pass
numeric_types.Int8BinaryDumper = Int8BinaryDumper
from uuid import UUID

def completion_setup(key, *, root_xid=2**64-1, capacity=4096):
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);actual=n.ManagedConnection(PG())
    c=n.attach_native(actual,x,execution_ledger=L)
    with m._construction(False):
        root,code=m._reserve_root(c,L);assert code is None
        actual.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(root,L,known=True)
    fence=B.Fence(work_id=UUID(int=1),token=UUID(int=2),
        ownership_revision=2**63-1,cycle=1,expected_attempt=1)
    expected=fence
    parameters=(fence.work_id,fence.token,fence.ownership_revision,1,1)
    if key=='E06':parameters += (UUID(int=3),b'effect',b'evidence',None)
    if key=='E10':
        expected=B.GuardRef(guard_id=UUID(int=4),work_id=fence.work_id,root_xid=root_xid,
            token=fence.token,ownership_revision=fence.ownership_revision,cycle=1,expected_attempt=1)
        parameters=(expected.guard_id,expected.work_id,root_xid,expected.token,
            expected.ownership_revision,1,1,b'result')
    context=B.ReturnContext(expected=(expected,),readiness=None)
    a=native.prepare(x,C.get_statement(key),parameters,execution_ledger=L,context=context,capacity=4096)
    t=m.admit(root,a,execution_ledger=L);b=m.reserve_result(t,capacity,execution_ledger=L)
    wire=(b'\\x01',UUID(int=4).bytes,fence.work_id.bytes,root_xid.to_bytes(8,'big'),
        fence.token.bytes,fence.ownership_revision.to_bytes(8,'big'),(1).to_bytes(4,'big'),
        (1).to_bytes(4,'big'),b'\\x00',None,None,None)
    values=[wire] if key in ('E08','E09') else [(b'\\x01', (2).to_bytes(4,'big') if key=='E06' else b'\\x01')]
    Cursor.result=Result(key,values)
    return L,x,actual,c,root,a,t,b
"""


def run(body):
    _run(_SETUP + _DRIVER + _COMPLETION + textwrap.dedent(body))


@pytest.mark.parametrize("key", ["E06", "E08", "E09", "E10"])
def test_complete_result_and_retained_identity(key):
    run(f"""
    L,x,actual,c,r,a,t,b=completion_setup({key!r})
    req=m._preparations[a._stamp]['data'];params=req.parameters;context=req.context
    native.execute(t,b,execution_ledger=L)
    result=m.read_result(b,execution_ledger=L)
    assert req.parameters is params and req.context is context
    assert Cursor.instances[0].adapters.dumpers[int] is Int8BinaryDumper
    assert int not in actual.adapters.dumpers
    if {key!r}=='E06':assert result==2 and type(result) is int
    elif {key!r}=='E10':
        assert result is True
        sent=Cursor.instances[0].calls[0][1]
        assert sent[2]=='18446744073709551615' and params[2]==2**64-1
        assert sent[:2]==params[:2] and sent[3:]==params[3:]
    else:assert type(result) is O.GuardRow and result.root_xid==2**64-1
    assert not L.uncertainty.present and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_optional_absence_and_no_row_copy():
    run("""
    L,x,actual,c,r,a,t,b=completion_setup('E09')
    Cursor.result=Result('E09',[])
    native.execute(t,b,execution_ledger=L)
    assert m.read_result(b,execution_ledger=L) is None and Cursor.result.copies==[]
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("fault", ["extra_row", "extra_set", "false_unit", "wrong_oid"])
def test_post_execution_fault_is_held(fault):
    run(f"""
    L,x,actual,c,r,a,t,b=completion_setup('E10')
    if {fault!r}=='extra_row':Cursor.result=Result('E10',[(b'\\x01',b'\\x01')]*2)
    if {fault!r}=='extra_set':Cursor.extra=True
    if {fault!r}=='false_unit':Cursor.result=Result('E10',[(b'\\x01',b'\\x00')])
    if {fault!r}=='wrong_oid':Cursor.result.ftype=lambda index:17
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
    record=m._ticket(t,L)
    assert record.operation['state']=='HELD' and record.roots[t._subject]['state']=='UNKNOWN'
    if {fault!r} in ('extra_row','wrong_oid'):assert Cursor.result.copies==[]
    assert L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)


def test_close_failure_preserves_primary():
    run("""
    L,x,actual,c,r,a,t,b=completion_setup('E08')
    primary=KeyboardInterrupt('NONSECRET_COMPLETION');cause=ValueError('NONSECRET_CAUSE')
    primary.__cause__=cause;primary.__suppress_context__=True
    def fail(cursor):raise primary
    Cursor.close_effect=fail
    try:native.execute(t,b,execution_ledger=L)
    except BaseException as caught:
        assert caught is primary and caught.__cause__ is cause and caught.__suppress_context__
    else:raise AssertionError('missing failure')
    assert m._ticket(t,L).operation['state']=='HELD' and L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("root_xid", [1, 2**63 - 1, 2**63, 2**64 - 1])
def test_xid_transport_full_unsigned_domain(root_xid):
    run(f"""
    L,x,actual,c,r,a,t,b=completion_setup('E10',root_xid={root_xid})
    native.execute(t,b,execution_ledger=L)
    params=Cursor.instances[0].calls[0][1]
    assert type(params[2]) is str and params[2]==str({root_xid})
    assert len(params[2])<=20 and params[2].isascii() and params[2].isdigit()
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("fault", ["name", "format", "size", "tag", "count", "null", "cap"])
def test_guard_metadata_and_material_faults(fault):
    run(f"""
    L,x,actual,c,r,a,t,b=completion_setup('E08')
    if {fault!r}=='name':Cursor.result.fname=lambda index:b'wrong'
    if {fault!r}=='format':Cursor.result.fformat=lambda index:0
    if {fault!r}=='size':Cursor.result.fsize=lambda index:999
    if {fault!r}=='tag':Cursor.result.command_status=b'SELECT 2'
    if {fault!r}=='count':Cursor.result.command_tuples=2
    if {fault!r} in ('null','cap'):
        wire=list(Cursor.result.values[0]);wire[1 if {fault!r}=='null' else 0]=None
        Cursor.result.values=[tuple(wire)]
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
    assert m._ticket(t,L).operation['state']=='HELD' and L.uncertainty.present
    if {fault!r} not in ('null','cap'):assert Cursor.result.copies==[]
    if {fault!r}=='cap':assert Cursor.result.copies==[(0,0)]
    print('MANAGED_BODY_COMPLETE')
    """)


def test_temporary_parameter_reference_cleared_before_normal_construction_exit():
    run("""
    from contextlib import contextmanager
    import inspect
    L,x,actual,c,r,a,t,b=completion_setup('E10')
    original=m._construction
    observed=[]
    @contextmanager
    def observe(flag):
        with original(flag) as paid:
            yield paid
            caller=inspect.currentframe().f_back.f_back
            if caller.f_code is native.execute.__code__:
                observed.append(caller.f_locals['parameters'])
    m._construction=observe
    native.execute(t,b,execution_ledger=L)
    assert observed==[None]
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize(
    "capacity",
    [
        "True",
        "False",
        "0",
        "-1",
        "1.0",
        "4096.0",
        "float('nan')",
        "float('inf')",
        "'4096'",
        "Impostor()",
        "IntSubclass(4096)",
    ],
)
def test_bridge_sr_001_invalid_capacity_rejected_before_paid_work(capacity):
    run(f"""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L)
    before=m.capacity_snapshot(execution_ledger=L)
    execution=dict(m._executions[x._stamp]);preparations=dict(m._preparations)
    calls=[]
    class Impostor:
        def hook(self,*args):
            calls.append('arithmetic');raise AssertionError('capacity hook invoked')
        __add__=__radd__=__lt__=__le__=__gt__=__ge__=__int__=__index__=hook
    class IntSubclass(int):
        def __add__(self,*args):
            calls.append('subclass');raise AssertionError('subclass hook invoked')
        __radd__=__add__
    def forbidden(*args,**kwargs):
        calls.append('paid_or_freeze');raise AssertionError('validation happened too late')
    original=m._construction
    m._construction=forbidden
    m._reserve_preparation_paid=forbidden
    native._freeze_request_raw=forbidden
    native._return_context_raw=forbidden
    expect(E.LOCAL_INVALID_ARGUMENT,lambda:native.prepare(x,C.get_statement('E14'),(),
        execution_ledger=L,capacity={capacity}))
    m._construction=original
    assert calls==[] and Cursor.instances==[]
    assert m.capacity_snapshot(execution_ledger=L)==before
    assert m._executions[x._stamp]==execution and m._preparations==preparations
    assert not L.uncertainty.present and not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_bridge_sr_001_positive_undersizing_cleans_up_and_adequate_succeeds():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L)
    before=m.capacity_snapshot(execution_ledger=L)
    execution=dict(m._executions[x._stamp]);preparations=dict(m._preparations)
    expect(E.CAPACITY_EXCEEDED,lambda:native.prepare(x,C.get_statement('E14'),(),
        execution_ledger=L,capacity=1))
    assert m.capacity_snapshot(execution_ledger=L)==before
    assert m._executions[x._stamp]==execution and m._preparations==preparations
    assert not L.uncertainty.present and not old._domain.stopped and Cursor.instances==[]
    prepared=native.prepare(x,C.get_statement('E14'),(),execution_ledger=L,capacity=1024)
    assert m._preparations[prepared._stamp]['data'].statement is C.get_statement('E14')
    assert m._counts['D']==0 and not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)
