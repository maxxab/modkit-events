"""Fake-driver E31 paid issuer; no actual native or commit qualification."""

import textwrap

import pytest
from test_native_failure_issuer import run as base_run

_SETUP = """
from test_native_resolution_contract import request as resolution_request, values, occurrence_sizes
from test_native_resolution_codec import wire
from modkit_events.persistence import rows as R
from uuid import UUID
class Int8BinaryDumper:pass
numeric_types.Int8BinaryDumper=Int8BinaryDumper

def resolution_setup(*, outcome='confirmed_success', large=False, alias=False, a_short=0, b_short=0):
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);actual=n.ManagedConnection(PG())
    c=n.attach_native(actual,x,execution_ledger=L)
    with m._construction(False):
        r,code=m._reserve_root(c,L);assert code is None
        actual.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(r,L,known=True)
    req=resolution_request(outcome,large=large,alias=alias)
    value=R._decode_native_event_result_raw(req,(values(req),))
    ac,bc=occurrence_sizes(req,value)
    arguments=dict(zip((p.name for p in req.statement.parameters),req.parameters))
    a=native.prepare_resolution(x,execution_ledger=L,capacity=ac-a_short,**arguments)
    t=m.admit(r,a,execution_ledger=L)
    b=m.reserve_result(t,bc-b_short,execution_ledger=L)
    Cursor.result=Result('E31',[wire(req)])
    return L,x,actual,c,r,a,t,b,req,ac,bc
"""


def run(body):
    base_run(_SETUP + textwrap.dedent(body))


@pytest.mark.parametrize(
    "outcome", ["confirmed_success", "confirmed_rejection", "confirmed_cancelled", "safe_retry"]
)
def test_paid_issuer_stages_exact_receipt_without_finalizing(outcome):
    run(f"""
    L,x,actual,c,r,a,t,b,req,ac,bc=resolution_setup(outcome={outcome!r})
    retained=m._preparations[a._stamp]['data'];params=retained.parameters
    native.execute(t,b,execution_ledger=L)
    cursor=Cursor.instances[-1]
    assert cursor.calls==[(_selected_sql_descriptor(req.statement).sql,params,False,True)]
    assert cursor.calls[0][1] is params and retained.parameters is params
    assert cursor.adapters.dumpers[int] is Int8BinaryDumper
    assert int not in actual.adapters.dumpers
    result=m.read_result(b,execution_ledger=L)
    assert type(result) is O.ResolutionObservation and result.outcome=={outcome!r}
    assert result.resolution_root_xid==2**64-1
    assert m._root(r,L)[1]['state']=='ACTIVE'
    assert actual.pgconn.transaction_status is TransactionStatus.INTRANS
    assert m._counts['D']==0 and not L.uncertainty.present and len(Cursor.instances)==1
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "extra",
        "oid",
        "name",
        "format",
        "width",
        "tag",
        "extra_set",
        "cap",
        "coupling",
        "driver",
        "close",
        "capacity",
    ],
)
def test_post_start_fault_holds_without_replay_or_refund(fault):
    run(f"""
    L,x,actual,c,r,a,t,b,req,ac,bc=resolution_setup(b_short=1 if {fault!r}=='capacity' else 0)
    primary=KeyboardInterrupt('E31_PRIMARY');cause=ValueError('cause')
    primary.__cause__=cause;primary.__suppress_context__=True
    def fail(cursor):raise primary
    if {fault!r}=='empty':Cursor.result=Result('E31',[])
    if {fault!r}=='extra':Cursor.result=Result('E31',[wire(req)]*2)
    if {fault!r}=='oid':Cursor.result.ftype=lambda index:17
    if {fault!r}=='name':Cursor.result.fname=lambda index:b'wrong'
    if {fault!r}=='format':Cursor.result.fformat=lambda index:0
    if {fault!r}=='width':Cursor.result.fsize=lambda index:0
    if {fault!r}=='tag':Cursor.result.command_status=b'INSERT 0 1'
    if {fault!r}=='extra_set':Cursor.extra=True
    if {fault!r} in ('cap','coupling'):
        cells=list(wire(req));cells[0 if {fault!r}=='cap' else 1]=b'\\x00' if {fault!r}=='cap' else bytes(16)
        Cursor.result=Result('E31',[tuple(cells)])
    if {fault!r}=='driver':Cursor.effect=fail
    if {fault!r}=='close':Cursor.close_effect=fail
    before=dict(m._counts)
    if {fault!r} in ('driver','close'):
        try:native.execute(t,b,execution_ledger=L)
        except BaseException as caught:
            assert caught is primary and caught.__cause__ is cause and caught.__suppress_context__
        else:raise AssertionError('missing primary')
    else:
        expect(E.CAPACITY_EXCEEDED if {fault!r}=='capacity' else E.INVALID_OBSERVATION,
               lambda:native.execute(t,b,execution_ledger=L),{fault!r}!='capacity')
    assert len(Cursor.instances)==1
    p=m._ticket(t,L)
    assert p.operation['state']=='HELD' and p.roots[t._subject]['state']=='UNKNOWN'
    assert old._domain.stopped and L.uncertainty.present and m._counts['D']>=1
    assert all(m._counts[k]==before[k] for k in ('A','AB','B','BB','R','C','X'))
    if {fault!r}=='cap':assert Cursor.result.copies==[(0,0)]
    print('MANAGED_BODY_COMPLETE')
    """)


def test_factory_constructs_only_after_paid_reservation():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);req=resolution_request()
    arguments=dict(zip((p.name for p in req.statement.parameters),req.parameters))
    original=native._freeze_request_raw;seen=[]
    def freeze(*args,**kwargs):
        assert m._counts['D']==1 and m._counts['A']==1 and m._counts['AB']==8192
        seen.append(True)
        return original(*args,**kwargs)
    native._freeze_request_raw=freeze
    def forbidden(*args,**kwargs):raise AssertionError('nested generic prepare')
    native.prepare=forbidden
    a=native.prepare_resolution(x,execution_ledger=L,capacity=8192,**arguments)
    assert seen==[True] and not Cursor.instances and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_invalid_factory_request_releases_unreturned_preparation():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);req=resolution_request()
    arguments=dict(zip((p.name for p in req.statement.parameters),req.parameters));arguments['result']=bytearray(b'x')
    expect(E.LOCAL_INVALID_ARGUMENT,lambda:native.prepare_resolution(x,execution_ledger=L,capacity=8192,**arguments))
    assert not Cursor.instances and m._counts['A']==m._counts['AB']==m._counts['D']==0
    assert not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)
