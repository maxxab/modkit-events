"""Structural E33 issuer qualification only; no actual psycopg/PostgreSQL."""
import textwrap

import pytest
from test_managed_lifecycle import _run
from test_managed_statement_lifecycle import _SETUP
from test_native_execution import _DRIVER

_READINESS = """
def pinned(profile='workers'):
    digest=b'x'*32
    return B.ReadinessExpectation(components=tuple(
        O.SchemaStatus(component=name,version=2147483647,migration_digest=digest,
            catalog_contract_id='modkit-pg-ab-2',scope_format_id='MKSC-1',intent_format_id='MKPF-1')
        for name in (('events',) if profile=='events' else ('events','workers'))))
def readiness_setup(profile='workers', capacity=16384):
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);actual=n.ManagedConnection(PG())
    c=n.attach_native(actual,x,execution_ledger=L)
    with m._construction(False):
        root,code=m._reserve_root(c,L);assert code is None
        actual.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(root,L,known=True)
    exp=pinned(profile)
    a=native.prepare_readiness(x,profile,exp,execution_ledger=L)
    t=m.admit(root,a,execution_ledger=L)
    b=m.reserve_result(t,capacity,execution_ledger=L)
    wires=[(b'\\x01',v.component.encode(),v.version.to_bytes(4,'big'),
            v.migration_digest,v.catalog_contract_id.encode(),v.scope_format_id.encode(),
            v.intent_format_id.encode()) for v in exp.components]
    Cursor.result=Result('E33',wires)
    return L,x,actual,c,root,a,t,b,exp
"""


def run(body):
    _run(_SETUP + _DRIVER + _READINESS + textwrap.dedent(body))


@pytest.mark.parametrize("profile", ["events", "workers"])
def test_readiness_publishes_exact_statuses_without_finalization(profile):
    run(f"""
    L,x,actual,c,r,a,t,b,exp=readiness_setup({profile!r})
    req=m._preparations[a._stamp]['data']
    native.execute(t,b,execution_ledger=L)
    got=m.read_result(b,execution_ledger=L)
    assert type(got) is tuple and got==exp.components
    assert all(type(v) is O.SchemaStatus for v in got)
    assert req.context.readiness is exp
    assert Cursor.instances[0].calls[0][1] is req.parameters
    assert len(Cursor.instances[0].calls)==1 and Cursor.instances[0].closed
    assert actual.pgconn.transaction_status is TransactionStatus.INTRANS
    assert m._ticket(t,L).roots[t._subject]['state']=='ACTIVE'
    assert not L.uncertainty.present and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("field,value", [
    (2, "(1).to_bytes(4,'big')"), (3, "b'y'*32"),
    (4, "b'wrong'"), (5, "b'wrong'"), (6, "b'wrong'"),
])
def test_readiness_schema_mismatch_is_detached_and_held(field, value):
    run(f"""
    L,x,actual,c,r,a,t,b,exp=readiness_setup()
    wire=list(Cursor.result.values[0]);wire[{field}]={value}
    Cursor.result.values[0]=tuple(wire)
    try:native.execute(t,b,execution_ledger=L)
    except PersistenceError as error:
        assert error.code is E.SCHEMA_MISMATCH and error.unconfirmed
        assert str(error)=='SCHEMA_MISMATCH'
        assert error.__cause__ is None and error.__context__ is None
    else:raise AssertionError('missing mismatch')
    assert m._ticket(t,L).operation['state']=='HELD'
    assert not m._results[b._stamp]['populated'] and L.uncertainty.present
    assert Cursor.instances[0].closed
    assert m._counts['A']==1 and m._counts['B']==1
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("fault", [
    "missing", "extra", "wrong_oid", "wrong_name", "text_format", "width",
    "wrong_status", "wrong_count", "nonbinary", "order", "duplicate", "extra_set",
    "cap", "bad_digest", "null", "version_zero",
])
def test_readiness_invalid_observation_never_published(fault):
    run(f"""
    L,x,actual,c,r,a,t,b,exp=readiness_setup()
    fault={fault!r}
    if fault=='missing':Cursor.result=Result('E33',Cursor.result.values[:1])
    if fault=='extra':Cursor.result=Result('E33',Cursor.result.values+[Cursor.result.values[0]])
    if fault=='wrong_oid':Cursor.result.ftype=lambda i:23
    if fault=='wrong_name':Cursor.result.fname=lambda i:b'bad'
    if fault=='text_format':Cursor.result.fformat=lambda i:0
    if fault=='width':Cursor.result.fsize=lambda i:1
    if fault=='wrong_status':Cursor.result.status=ExecStatus.COMMAND_OK
    if fault=='wrong_count':Cursor.result.command_tuples=0
    if fault=='nonbinary':Cursor.result.binary_tuples=0
    if fault=='order':Cursor.result.values.reverse()
    if fault=='duplicate':Cursor.result.values[1]=Cursor.result.values[0]
    if fault=='extra_set':Cursor.extra=object()
    if fault in ('cap','bad_digest','null','version_zero'):
        wire=list(Cursor.result.values[0])
        index,value={{'cap':(0,b'\\x00'),'bad_digest':(3,b'short'),
                     'null':(4,None),'version_zero':(2,bytes(4))}}[fault]
        wire[index]=value;Cursor.result.values[0]=tuple(wire)
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
    assert not m._results[b._stamp]['populated']
    assert m._ticket(t,L).operation['state']=='HELD' and L.uncertainty.present
    if fault in ('missing','extra','wrong_oid','wrong_name','text_format','width',
                 'wrong_status','wrong_count','nonbinary'):
        assert Cursor.result.copies==[]
    print('MANAGED_BODY_COMPLETE')
    """)


def test_readiness_close_failure_preserves_primary_and_liabilities():
    run("""
    L,x,actual,c,r,a,t,b,exp=readiness_setup()
    primary=KeyboardInterrupt('opaque')
    def fail(cursor):raise primary
    Cursor.close_effect=fail
    try:native.execute(t,b,execution_ledger=L)
    except BaseException as caught:assert caught is primary
    else:raise AssertionError('missing failure')
    assert m._ticket(t,L).operation['state']=='HELD'
    assert not m._results[b._stamp]['populated'] and L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)
