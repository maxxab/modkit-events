"""Pure E05 issuer tests using the existing test-only fake driver.

These prove managed ownership/accounting and issuer dispatch, not PostgreSQL locks.
"""

import textwrap

import pytest
from test_native_failure_issuer import run as base_run

_SETUP = """
from test_native_renewal_contract import request as renewal_request, occurrence_size, STAMP
from dataclasses import replace
from uuid import UUID
class Int8BinaryDumper:pass
class FloatBinaryDumper:pass
numeric_types.Int8BinaryDumper=Int8BinaryDumper
numeric_types.FloatBinaryDumper=FloatBinaryDumper

def renewal_setup(*, seconds=3600, revision=2**63-1, b_short=0):
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);actual=n.ManagedConnection(PG())
    c=n.attach_native(actual,x,execution_ledger=L)
    with m._construction(False):
        r,code=m._reserve_root(c,L);assert code is None
        actual.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(r,L,known=True)
    from test_native_renewal_contract import F
    req=renewal_request(seconds,fence=replace(F,ownership_revision=revision))
    ac=m._preparation_size(req)
    a=native.prepare(x,req.statement,req.parameters[:5]+(seconds,),execution_ledger=L,
                     context=req.context,capacity=ac)
    t=m.admit(r,a,execution_ledger=L)
    b=m.reserve_result(t,48-b_short,execution_ledger=L)
    Cursor.result=Result('E05',[(b'\\x01',bytes(8))])
    return L,x,actual,c,r,a,t,b,req,ac
"""


def run(body):
    base_run(_SETUP + textwrap.dedent(body))


@pytest.mark.parametrize(
    "seconds,revision",
    [
        (1, 1),
        (3600, 2**63 - 1),
        (0.1, 2**53 + 1),
        (5e-324, 2**31),
    ],
)
def test_paid_normalization_binary_dispatch_and_staged_timestamp(seconds, revision):
    run(f"""
    L,x,actual,c,r,a,t,b,req,ac=renewal_setup(seconds={seconds!r},revision={revision})
    retained=m._preparations[a._stamp]['data'];params=retained.parameters
    native.execute(t,b,execution_ledger=L)
    sent=Cursor.instances[-1].calls
    assert sent==[(_selected_sql_descriptor(req.statement).sql,params,False,True)]
    assert params[2]=={revision} and type(params[2]) is int
    assert type(params[5]) is float and params[5].hex()==float({seconds!r}).hex()
    assert retained.parameters is params
    assert Cursor.instances[-1].adapters.dumpers[int] is Int8BinaryDumper
    assert Cursor.instances[-1].adapters.dumpers[float] is FloatBinaryDumper
    assert int not in actual.adapters.dumpers and float not in actual.adapters.dumpers
    assert m.read_result(b,execution_ledger=L)==STAMP
    assert m._root(r,L)[1]['state']=='ACTIVE'
    assert actual.pgconn.transaction_status is TransactionStatus.INTRANS
    assert m._counts['D']==0 and not L.uncertainty.present
    assert len(Cursor.instances)==1
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
        "size",
        "tag",
        "count",
        "extra_set",
        "cap",
        "null",
        "infinity",
        "driver",
        "close",
        "capacity",
    ],
)
def test_post_start_fault_holds_all_liabilities_without_retry(fault):
    run(f"""
    L,x,actual,c,r,a,t,b,req,ac=renewal_setup(b_short=1 if {fault!r}=='capacity' else 0)
    primary=KeyboardInterrupt('NONSECRET_E05');cause=ValueError('cause')
    primary.__cause__=cause;primary.__suppress_context__=True
    def fail(cursor):raise primary
    if {fault!r}=='empty':Cursor.result=Result('E05',[])
    if {fault!r}=='extra':Cursor.result=Result('E05',[(b'\\x01',bytes(8))]*2)
    if {fault!r}=='oid':Cursor.result.ftype=lambda index:17
    if {fault!r}=='name':Cursor.result.fname=lambda index:b'wrong'
    if {fault!r}=='format':Cursor.result.fformat=lambda index:0
    if {fault!r}=='size':Cursor.result.fsize=lambda index:999
    if {fault!r}=='tag':Cursor.result.command_status=b'SELECT 2'
    if {fault!r}=='count':Cursor.result.command_tuples=2
    if {fault!r}=='extra_set':Cursor.extra=True
    if {fault!r} in ('cap','null','infinity'):
        cells=[b'\\x01',bytes(8)]
        if {fault!r}=='cap':cells[0]=b'\\x00'
        if {fault!r}=='null':cells[1]=None
        if {fault!r}=='infinity':cells[1]=(2**63-1).to_bytes(8,'big')
        Cursor.result=Result('E05',[tuple(cells)])
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
    print('MANAGED_BODY_COMPLETE')
    """)


def test_exact_preparation_and_one_byte_short_are_local_before_io():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);req=renewal_request();ac=occurrence_size(req)
    before=dict(m._counts)
    expect(E.CAPACITY_EXCEEDED,lambda:native.prepare(x,req.statement,req.parameters,
        execution_ledger=L,context=req.context,capacity=ac-1))
    assert dict(m._counts)==before and not Cursor.instances and not old._domain.stopped
    a=native.prepare(x,req.statement,req.parameters,execution_ledger=L,
        context=req.context,capacity=ac)
    assert m._counts['AB']==ac and m._counts['A']==1 and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_invalid_inputs_are_local_and_do_not_consume_preparation():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);req=renewal_request()
    before=dict(m._counts)
    for seconds in (True,0,-0.0,float('nan'),float('inf'),10**1000):
        expect(E.LOCAL_INVALID_ARGUMENT,lambda:native.prepare(
            x,req.statement,req.parameters[:5]+(seconds,),execution_ledger=L,context=req.context))
        assert dict(m._counts)==before and not L.uncertainty.present
    assert not Cursor.instances and not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_distinct_control_execution_preserves_business_handles_and_charges():
    run("""
    L,x,actual,c,r,a,t,b,req,ac=renewal_setup()
    other=ExecutionLedger();ox=m.reserve_execution(other);oa=n.ManagedConnection(PG())
    oc=n.attach_native(oa,ox,execution_ledger=other)
    with m._construction(False):
        root,code=m._reserve_root(oc,other);assert code is None
        oa.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(root,other,known=True)
    prep=native.prepare(ox,req.statement,req.parameters,execution_ledger=other,
                        context=req.context,capacity=ac)
    ticket=m.admit(root,prep,execution_ledger=other)
    result=m.reserve_result(ticket,48,execution_ledger=other)
    before=dict(m._counts)
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=other))
    native.execute(ticket,result,execution_ledger=other)
    assert m.read_result(result,execution_ledger=other)==STAMP
    assert m._root(r,L)[1]['state']=='ACTIVE' and m._ticket(t,L).operation['state']=='ADMITTED'
    assert all(m._counts[k]==before[k] for k in ('A','AB','B','BB','R','C','X'))
    assert m._counts['C']==2 and m._counts['X']==2 and m._counts['R']==2
    assert m._counts['A']==2 and m._counts['AB']==2*ac and m._counts['B']==2
    assert m._counts['BB']==96 and m._counts['D']==0
    assert not L.uncertainty.present and not other.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)


def test_two_open_roots_high_water_includes_nested_publication():
    run("""
    high={}
    charge=m._charge
    def observed_charge(delta):
        ok=charge(delta)
        if ok:
            for key,value in m._counts.items():high[key]=max(high.get(key,0),value)
        return ok
    m._charge=observed_charge
    L,x,actual,c,r,a,t,b,req,ac=renewal_setup()
    other=ExecutionLedger();ox=m.reserve_execution(other);oa=n.ManagedConnection(PG())
    oc=n.attach_native(oa,ox,execution_ledger=other)
    with m._construction(False):
        root,code=m._reserve_root(oc,other);assert code is None
        oa.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(root,other,known=True)
    prep=native.prepare(ox,req.statement,req.parameters,execution_ledger=other,
                        context=req.context,capacity=ac)
    ticket=m.admit(root,prep,execution_ledger=other)
    result=m.reserve_result(ticket,48,execution_ledger=other)
    native.execute(ticket,result,execution_ledger=other)
    assert {k:high[k] for k in ('C','X','R','A','AB','B','BB','D')} == {
        'C':2,'X':2,'R':2,'A':2,'AB':2*ac,'B':2,'BB':96,'D':2}
    print('MANAGED_BODY_COMPLETE')
    """)
