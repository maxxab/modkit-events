"""Pure E31 occurrence accounting and fail-stop controls, not runtime proof."""

import pytest
from test_native_resolution_issuer import run


@pytest.mark.parametrize("alias", [False, True])
def test_maximum_graph_exact_capacity(alias):
    run(f"""
    L,x,actual,c,r,a,t,b,req,ac,bc=resolution_setup(large=True,alias={alias!r})
    native.execute(t,b,execution_ledger=L)
    result=m.read_result(b,execution_ledger=L)
    assert all(len(getattr(result,n))==1048576 for n in ('result','evidence','binding'))
    assert m._preparation_size(req)==ac and m._typed_result_size(req,result)==bc
    assert ac>3145728 and bc>3145728
    assert m._counts['AB']==ac and m._counts['BB']==bc
    print('MANAGED_BODY_COMPLETE')
    """)


def test_preparation_one_byte_short_before_driver():
    run("""
    try:resolution_setup(large=True,alias=True,a_short=1)
    except PersistenceError as error:assert error.code is E.CAPACITY_EXCEEDED
    else:raise AssertionError('short preparation accepted')
    assert not Cursor.instances and m._counts['A']==m._counts['AB']==0
    assert not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_result_one_byte_short_retains_full_graph():
    run("""
    L,x,actual,c,r,a,t,b,req,ac,bc=resolution_setup(large=True,alias=True,b_short=1)
    expect(E.CAPACITY_EXCEEDED,lambda:native.execute(t,b,execution_ledger=L))
    assert m._counts['AB']==ac and m._counts['BB']==bc-1
    assert m._ticket(t,L).operation['state']=='HELD' and old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_foreign_carrier_and_uncoupled_result_rejected():
    run("""
    L,x,actual,c,r,a,t,b,req,ac,bc=resolution_setup()
    from dataclasses import replace
    from modkit_events.persistence.errors import _ValidationReject
    value=R._decode_native_event_result_raw(req,(values(req),))
    for candidate in (values(req),replace(value,operation_id=UUID(int=1))):
        try:m._typed_result_size(req,candidate)
        except _ValidationReject:pass
        else:raise AssertionError('uncoupled result accepted')
    print('MANAGED_BODY_COMPLETE')
    """)


def test_foreign_ledger_and_stopped_domain_cannot_issue():
    run("""
    L,x,actual,c,r,a,t,b,req,ac,bc=resolution_setup()
    other=ExecutionLedger();m.reserve_execution(other)
    expect(E.INVALID_OBSERVATION,lambda:m.validate_ticket(t,execution_ledger=other))
    try:
        with m._construction(False):raise KeyboardInterrupt('fail-stop')
    except KeyboardInterrupt:pass
    before=dict(m._counts)
    expect(E.PROFILE_REJECTED,lambda:native.execute(t,b,execution_ledger=L))
    expect(E.PROFILE_REJECTED,lambda:m.reserve_execution(ExecutionLedger()))
    assert not Cursor.instances
    assert all(m._counts[k]==before[k] for k in ('C','R','X','A','AB','B','BB'))
    print('MANAGED_BODY_COMPLETE')
    """)


def test_result_and_preparation_release_order_preserves_borrows():
    run("""
    L,x,actual,c,r,a,t,b,req,ac,bc=resolution_setup()
    native.execute(t,b,execution_ledger=L)
    value=m.read_result(b,execution_ledger=L)
    expect(E.RESOURCE_BUSY,lambda:m.release_ticket(t,execution_ledger=L))
    expect(E.RESOURCE_BUSY,lambda:m.release_preparation(a,execution_ledger=L))
    assert m._counts['AB']==ac and m._counts['BB']==bc
    value=None
    m.release_result(b,execution_ledger=L)
    m.release_ticket(t,execution_ledger=L)
    req=None
    m.release_preparation(a,execution_ledger=L)
    assert m._counts['A']==m._counts['AB']==m._counts['B']==m._counts['BB']==0
    assert m._root(r,L)[1]['state']=='ACTIVE' and not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)
