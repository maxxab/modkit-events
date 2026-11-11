"""Pure E32 capacity/control isolation. No native commit or W02 proof."""

import pytest
from test_native_uncertainty_issuer import run


@pytest.mark.parametrize("alias", [False, True])
def test_full_maximum_graph_exact_capacity_success(alias):
    run(f"""
    L,x,actual,c,r,a,t,b,req,ac,bc=uncertain_setup(large=True,alias={alias!r})
    assert m._counts['AB']==ac and m._counts['BB']==bc
    native.execute(t,b,execution_ledger=L)
    result=m.read_result(b,execution_ledger=L)
    assert len(result.evidence)==1048576 and len(result.binding)==1048576
    assert result.evidence==req.parameters[8] and result.binding==req.parameters[9]
    assert len(result.reason)==256
    assert m._preparation_size(req)==ac and m._typed_result_size(req,result)==bc
    assert ac>2097152 and bc>2097152
    assert m._counts['AB']==ac and m._counts['BB']==bc
    print('MANAGED_BODY_COMPLETE')
    """)


def test_maximum_request_one_byte_short_rejects_before_driver_and_refunds_new_a():
    run("""
    try:uncertain_setup(large=True,alias=True,a_short=1)
    except PersistenceError as error:assert error.code is E.CAPACITY_EXCEEDED
    else:raise AssertionError('undercharged preparation accepted')
    assert not Cursor.instances and m._counts['A']==m._counts['AB']==0
    assert not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_maximum_result_one_byte_short_holds_without_refund():
    run("""
    L,x,actual,c,r,a,t,b,req,ac,bc=uncertain_setup(large=True,alias=True,b_short=1)
    expect(E.CAPACITY_EXCEEDED,lambda:native.execute(t,b,execution_ledger=L))
    assert m._counts['AB']==ac and m._counts['BB']==bc-1
    assert m._ticket(t,L).operation['state']=='HELD' and old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_typed_result_rejects_foreign_carrier_and_forged_coupling():
    run("""
    L,x,actual,c,r,a,t,b,req,ac,bc=uncertain_setup()
    from dataclasses import replace
    from modkit_events.persistence.errors import _ValidationReject
    value=R._decode_native_event_result_raw(req,(values(req),))
    for candidate in (values(req),replace(value,operation_id=UUID(int=1))):
        try:m._typed_result_size(req,candidate)
        except _ValidationReject:pass
        else:raise AssertionError('foreign/uncoupled result accepted')
    print('MANAGED_BODY_COMPLETE')
    """)


def test_independent_control_preserves_active_domain_unknown_business_liabilities():
    run("""
    L,x,actual,c,r,a,t,b,req,ac,bc=uncertain_setup()
    other=ExecutionLedger();other_x=m.reserve_execution(other)
    business=n.ManagedConnection(PG());other_c=n.attach_native(business,other_x,execution_ledger=other)
    with m._construction(False):
        other_r,code=m._reserve_root(other_c,other);assert code is None
        business.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(other_r,other,known=True)
        op,receipt,code=m._reserve_rollback(other_r,other,commit=True);assert code is None
        m._complete_commit(other_r,other,outcome=None,observed_tag=None)
    assert not old._domain.stopped and other.uncertainty.present
    old_root=dict(m._root(other_r,other)[1])
    uncertainty=other.uncertainty
    before=dict(m._counts)
    expect(E.INVALID_OBSERVATION,lambda:m.validate_ticket(t,execution_ledger=other),True)
    native.execute(t,b,execution_ledger=L)
    assert m._root(other_r,other)[1]==old_root and other.uncertainty is uncertainty
    assert all(m._counts[k]==before[k] for k in ('C','R','X','A','AB','B','BB'))
    assert m._root(r,L)[1]['state']=='ACTIVE' and not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_precreated_control_checkout_cannot_cross_stopped_domain():
    run("""
    L,x,actual,c,r,a,t,b,req,ac,bc=uncertain_setup()
    try:
        with m._construction(False):raise KeyboardInterrupt('isolated fail-stop')
    except KeyboardInterrupt:pass
    assert old._domain.stopped
    before=dict(m._counts)
    expect(E.PROFILE_REJECTED,lambda:native.execute(t,b,execution_ledger=L))
    assert not Cursor.instances
    assert all(m._counts[k]==before[k] for k in ('C','R','X','A','AB','B','BB'))
    print('MANAGED_BODY_COMPLETE')
    """)
