"""Pure fake-driver issuer tests: no database/native acceptance."""

import textwrap

import pytest
from test_native_failure_issuer import run as base_run

_SETUP = """
from test_native_uncertainty_contract import request as uncertain_request, values, occurrence_sizes
from test_native_uncertainty_codec import wire
from modkit_events.persistence import rows as R
from uuid import UUID
class Int8BinaryDumper:pass
numeric_types.Int8BinaryDumper=Int8BinaryDumper

def uncertain_setup(*, large=False, alias=False, xid=2**64-1, a_short=0, b_short=0):
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);actual=n.ManagedConnection(PG())
    c=n.attach_native(actual,x,execution_ledger=L)
    with m._construction(False):
        r,code=m._reserve_root(c,L);assert code is None
        actual.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(r,L,known=True)
    req=uncertain_request(large=large,alias=alias,xid=xid)
    value=R._decode_native_event_result_raw(req,(values(req),))
    ac,bc=occurrence_sizes(req,value)
    a=native.prepare(x,req.statement,req.parameters,execution_ledger=L,
                     context=req.context,capacity=ac-a_short)
    t=m.admit(r,a,execution_ledger=L)
    b=m.reserve_result(t,bc-b_short,execution_ledger=L)
    Cursor.result=Result('E32',[wire(req)])
    return L,x,actual,c,r,a,t,b,req,ac,bc
"""


def run(body):
    base_run(_SETUP + textwrap.dedent(body))


@pytest.mark.parametrize("xid", [1, 2**63 - 1, 2**63, 2**64 - 1])
def test_e32_paid_issuer_preserves_unsigned_request_and_stages_only(xid):
    run(f"""
    L,x,actual,c,r,a,t,b,req,ac,bc=uncertain_setup(xid={xid})
    retained=m._preparations[a._stamp]['data'];params=retained.parameters
    native.execute(t,b,execution_ledger=L)
    sent=Cursor.instances[-1].calls
    assert sent==[(_selected_sql_descriptor(req.statement).sql,
                  params[:5]+(str({xid}),)+params[6:],False,True)]
    assert retained.parameters is params and params[5]=={xid}
    assert Cursor.instances[-1].adapters.dumpers[int] is Int8BinaryDumper
    assert int not in actual.adapters.dumpers
    result=m.read_result(b,execution_ledger=L)
    assert type(result) is O.SettlementObservation and result.failed_business_root=={xid}
    assert result.operation_id==req.parameters[6] and result.evidence==b'e'
    assert m._root(r,L)[1]['state']=='ACTIVE'
    assert actual.pgconn.transaction_status is TransactionStatus.INTRANS
    assert m._counts['D']==0 and not L.uncertainty.present
    assert len(Cursor.instances)==1
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize(
    "fault",
    ["empty", "extra", "oid", "extra_set", "cap", "coupling", "driver", "close", "capacity"],
)
def test_e32_post_start_fault_retains_liabilities_and_never_replays(fault):
    run(f"""
    L,x,actual,c,r,a,t,b,req,ac,bc=uncertain_setup(b_short=1 if {fault!r}=='capacity' else 0)
    primary=KeyboardInterrupt('NONSECRET_E32');cause=ValueError('cause')
    primary.__cause__=cause;primary.__suppress_context__=True
    def fail(cursor):raise primary
    if {fault!r}=='empty':Cursor.result=Result('E32',[])
    if {fault!r}=='extra':Cursor.result=Result('E32',[wire(req)]*2)
    if {fault!r}=='oid':Cursor.result.ftype=lambda index:17
    if {fault!r}=='extra_set':Cursor.extra=True
    if {fault!r} in ('cap','coupling'):
        cells=list(wire(req));cells[0 if {fault!r}=='cap' else 1]=b'\\x00' if {fault!r}=='cap' else bytes(16)
        Cursor.result=Result('E32',[tuple(cells)])
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
