"""Structural issuer failures; faked driver only, not native qualification."""

import textwrap

import pytest
from test_managed_lifecycle import _run
from test_managed_statement_lifecycle import _SETUP
from test_native_execution import _DRIVER


def run(body):
    _run(
        _SETUP
        + _DRIVER
        + "\nfrom pathlib import Path\nsys.path.insert(0,str(Path(SOURCE).parent / 'tests'))\n"
        + textwrap.dedent(body)
    )


def test_e11_materializer_returns_staged_exact_true():
    run("""
    from test_native_failure_contract import request
    req=request()
    cursor=Cursor(type('Connection',(),{'adapters':type('Adapters',(),{'dumpers':{},'loaders':{}})()})(),
                  row_factory=rows.tuple_row)
    Cursor.result=Result('E11',[(b'\\x01',b'\\x01')])
    cursor.execute(b'unused',(),prepare=False,binary=True)
    assert native._materialize(cursor,req,_selected_sql_descriptor(req.statement)) is True
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("fault", ["empty", "extra", "false", "null", "oid", "extra_set"])
def test_e11_materializer_rejects_incomplete_unit(fault):
    run(f"""
    from test_native_failure_contract import request
    req=request()
    L,x,actual,c,r,a,t,b=setup()
    values=[(b'\\x01',b'\\x01')]
    if {fault!r}=='empty':values=[]
    if {fault!r}=='extra':values*=2
    if {fault!r}=='false':values=[(b'\\x01',b'\\x00')]
    if {fault!r}=='null':values=[(b'\\x01',None)]
    Cursor.result=Result('E11',values)
    if {fault!r}=='oid':Cursor.result.ftype=lambda index:17
    if {fault!r}=='extra_set':Cursor.extra=True
    cursor=Cursor(actual,row_factory=rows.tuple_row)
    cursor.execute(b'unused',(),prepare=False,binary=True)
    expect(E.INVALID_OBSERVATION,
           lambda:native._materialize(cursor,req,_selected_sql_descriptor(req.statement)),True)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_native_witness_hook_receives_completed_paid_issuer():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    calls=[]
    def observe(ticket,result,ledger,paid):
        operation=m._ticket(ticket,ledger).operation
        assert operation['state']=='COMPLETED' and not operation['running']
        assert operation['issuer'] is paid and m._reservation_live(paid)
        assert ticket is t and result is b and ledger is L
        assert m.read_result(result,execution_ledger=L)==17
        calls.append(True)
    m._observe_native_result_paid=observe
    native.execute(t,b,execution_ledger=L)
    assert calls==[True] and m._counts['D']==0 and not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)


def test_native_witness_hook_failure_preserves_primary_and_holds_completed_operation():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    primary=KeyboardInterrupt('NONSECRET_HOOK')
    cause=ValueError('NONSECRET_CAUSE')
    primary.__cause__=cause;primary.__suppress_context__=True
    def observe(ticket,result,ledger,paid):
        assert m._ticket(ticket,ledger).operation['state']=='COMPLETED'
        raise primary
    m._observe_native_result_paid=observe
    try:native.execute(t,b,execution_ledger=L)
    except BaseException as caught:
        assert caught is primary and caught.__cause__ is cause and caught.__suppress_context__
    else:raise AssertionError('missing hook failure')
    record=m._ticket(t,L)
    assert record.operation['state']=='HELD' and not record.operation['running']
    assert record.roots[t._subject]['state']=='UNKNOWN' and L.uncertainty.present
    assert m._counts['D']>=1 and old._domain.stopped
    assert len(Cursor.instances)==1
    print('MANAGED_BODY_COMPLETE')
    """)


# Bounded pg.Cursor probe fake adapted from the lifecycle owner's _FAKE.
# All root witnesses below are earned by actual native.execute, never arm/issue.
_FAILURE = """
from uuid import UUID
class Int8BinaryDumper:pass
numeric_types.Int8BinaryDumper=Int8BinaryDumper
class ProbeResult:
    status=ExecStatus.TUPLES_OK;ntuples=1;nfields=1;binary_tuples=1
    command_status=b'SELECT 1';command_tuples=1
    def fname(self,i):return b'pg_current_xact_id_if_assigned'
    def ftype(self,i):return 5069
    def fformat(self,i):return 1
    def fsize(self,i):return 8
    def get_value(self,r,c):return probe_xid.to_bytes(8,'big')
class ProbeCursor:
    instances=[];calls=[]
    def __init__(self,actual,*,row_factory):
        assert row_factory is rows.tuple_row
        self.pgresult=ProbeResult();self.rowcount=1;self.statusmessage='SELECT 1'
        self.closed=False;ProbeCursor.instances.append(self)
    def execute(self,sql,*,prepare,binary):
        ProbeCursor.calls.append((sql,prepare,binary))
    def nextset(self):return None
    def close(self):self.closed=True
pg.Cursor=ProbeCursor
rollback_calls=[]
def rollback(actual):
    assert ProbeCursor.instances[-1].closed
    rollback_calls.append(actual)
    actual.pgconn.transaction_status=TransactionStatus.IDLE
Connection.rollback=rollback

def release(a,t,b,L):
    m.release_result(b,execution_ledger=L)
    m.release_ticket(t,execution_ledger=L)
    m.release_preparation(a,execution_ledger=L)

def failure_setup(*,xid=17,outcome='failed',bind=True):
    global probe_xid
    probe_xid=xid
    L,x,actual,c,r,a,t,b=setup(values=[(b'\\x01',xid.to_bytes(8,'big'))],capacity=64)
    native.execute(t,b,execution_ledger=L)
    release(a,t,b,L)
    f=B.Fence(work_id=UUID(int=1),token=UUID(int=2),ownership_revision=2**63-1,
              cycle=1,expected_attempt=1)
    fp=(f.work_id,f.token,f.ownership_revision,1,1)
    context=B._return_context_raw(expected=(f,))
    a=native.prepare(x,C.get_statement('E08'),fp,execution_ledger=L,
                     context=context,capacity=4096)
    t=m.admit(r,a,execution_ledger=L);b=m.reserve_result(t,4096,execution_ledger=L)
    Cursor.result=Result('E08',[(b'\\x01',UUID(int=4).bytes,f.work_id.bytes,
        xid.to_bytes(8,'big'),f.token.bytes,(2**63-1).to_bytes(8,'big'),
        (1).to_bytes(4,'big'),(1).to_bytes(4,'big'),b'\\x00',None,None,None)])
    native.execute(t,b,execution_ledger=L)
    release(a,t,b,L)
    receipt=n.rollback(r,execution_ledger=L,confirm_failure=True)
    m.acknowledge_root_end(receipt,execution_ledger=L)
    retry=datetime(2026,1,1,tzinfo=timezone.utc) if outcome=='retry_waiting' else None
    params=fp+(xid,outcome,retry,'local',b'evidence')
    a=native.prepare(x,C.get_statement('E11'),params,execution_ledger=L,
                     context=context,capacity=65536)
    if bind:m.bind_failure_settlement(a,r,receipt,execution_ledger=L)
    with m._construction(False):
        settlement,code=m._reserve_root(c,L);assert code is None
        actual.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(settlement,L,known=True)
    return L,x,actual,c,r,settlement,a,receipt

def failure_ticket(**kwargs):
    L,x,actual,c,r,settlement,a,receipt=failure_setup(**kwargs)
    t=m.admit(settlement,a,execution_ledger=L)
    b=m.reserve_result(t,64,execution_ledger=L)
    Cursor.result=Result('E11',[(b'\\x01',b'\\x01')])
    return L,x,actual,c,r,settlement,a,t,b,receipt
"""


def failure_run(body):
    run(_FAILURE + textwrap.dedent(body))


@pytest.mark.parametrize("outcome", ["failed", "cancelled", "retry_waiting"])
@pytest.mark.parametrize("xid", [1, 2**63 - 1, 2**63, 2**64 - 1])
def test_e11_paid_execute_unsigned_transport_and_staged_result(outcome, xid):
    failure_run(f"""
    L,x,actual,c,r,settlement,a,t,b,receipt=failure_ticket(xid={xid},outcome={outcome!r})
    req=m._preparations[a._stamp]['data'];params=req.parameters;context=req.context
    native.execute(t,b,execution_ledger=L)
    sent=Cursor.instances[-1].calls[0]
    assert sent[0]==_selected_sql_descriptor(C.get_statement('E11')).sql
    assert sent[1]==params[:5]+(str({xid}),)+params[6:]
    assert sent[2:]==(False,True)
    assert req.parameters is params and req.context is context
    assert Cursor.instances[-1].adapters.dumpers[int] is Int8BinaryDumper
    assert int not in actual.adapters.dumpers
    assert m.read_result(b,execution_ledger=L) is True
    assert m._root(settlement,L)[1]['state']=='ACTIVE'
    assert m._root(r,L)[1]['failure_consumed']
    assert actual.pgconn.transaction_status is TransactionStatus.INTRANS
    assert len(rollback_calls)==1 and not L.uncertainty.present and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("fault", ["unbound", "replacement", "root_xid", "fence"])
def test_e11_proof_rejection_never_creates_statement_cursor(fault):
    failure_run(f"""
    if {fault!r}=='unbound':
        L,x,actual,c,r,settlement,a,receipt=failure_setup(bind=False)
        before=len(Cursor.instances)
        expect(E.INVALID_OBSERVATION,lambda:m.admit(settlement,a,execution_ledger=L))
    else:
        L,x,actual,c,r,settlement,a,t,b,receipt=failure_ticket()
        req=m._preparations[a._stamp]['data'];params=list(req.parameters)
        if {fault!r}=='replacement':object.__setattr__(req,'parameters',tuple(params))
        if {fault!r}=='root_xid':
            params[5]=18;object.__setattr__(req,'parameters',tuple(params))
        if {fault!r}=='fence':object.__setattr__(req.context.expected[0],'token',UUID(int=9))
        before=len(Cursor.instances)
        expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L))
    assert len(Cursor.instances)==before and not L.uncertainty.present
    assert not m._root(r,L)[1]['failure_consumed']
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("fault", ["false", "extra", "oid", "close", "driver", "capacity"])
def test_e11_post_start_fault_consumes_proof_and_holds(fault):
    failure_run(f"""
    L,x,actual,c,r,settlement,a,t,b,receipt=failure_ticket()
    primary=KeyboardInterrupt('NONSECRET_E11');cause=ValueError('NONSECRET_CAUSE')
    primary.__cause__=cause;primary.__suppress_context__=True
    def fail(cursor):raise primary
    if {fault!r}=='false':Cursor.result=Result('E11',[(b'\\x01',b'\\x00')])
    if {fault!r}=='extra':Cursor.result=Result('E11',[(b'\\x01',b'\\x01')]*2)
    if {fault!r}=='oid':Cursor.result.ftype=lambda index:17
    if {fault!r}=='close':Cursor.close_effect=fail
    if {fault!r}=='driver':Cursor.effect=fail
    if {fault!r}=='capacity':
        m.release_result(b,execution_ledger=L);b=m.reserve_result(t,1,execution_ledger=L)
    if {fault!r} in ('close','driver'):
        try:native.execute(t,b,execution_ledger=L)
        except BaseException as caught:
            assert caught is primary and caught.__cause__ is cause and caught.__suppress_context__
        else:raise AssertionError('missing primary')
    else:
        code=E.CAPACITY_EXCEEDED if {fault!r}=='capacity' else E.INVALID_OBSERVATION
        expect(code,lambda:native.execute(t,b,execution_ledger=L),{fault!r}!='capacity')
    assert m._root(r,L)[1]['failure_consumed']
    p=m._ticket(t,L)
    assert p.operation['state']=='HELD' and p.roots[t._subject]['state']=='UNKNOWN'
    assert L.uncertainty.present and m._counts['D']>=1
    print('MANAGED_BODY_COMPLETE')
    """)
