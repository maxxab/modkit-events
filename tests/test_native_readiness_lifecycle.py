"""Paid E33 graphs and cleanup, using real controller with structural driver."""

import pytest
from test_native_readiness_issuer import run


@pytest.mark.parametrize("profile", ["events", "workers"])
def test_readiness_A_exact_short_and_reserve_before_context(profile):
    run(f"""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);exp=pinned({profile!r})
    original=native._return_context_raw
    observed=[]
    def checked(**kwargs):
        assert m._counts['A']==1 and m._counts['AB']>0 and m._counts['D']==1
        observed.append(True)
        return original(**kwargs)
    native._return_context_raw=checked
    a=native.prepare_readiness(x,{profile!r},exp,execution_ledger=L)
    assert observed==[True]
    req=m._preparations[a._stamp]['data']
    exact=sum(getsizeof(v) for v in (req,req.parameters,req.parameters[0],
        req.context,req.context.expected,exp,exp.components))
    exact+=sum(getsizeof(v)+sum(getsizeof(getattr(v,name)) for name in
        ('component','version','migration_digest','catalog_contract_id','scope_format_id','intent_format_id'))
        for v in exp.components)
    assert m._preparation_size(req)==exact and exact<=4096
    assert req.context.readiness is exp
    m.release_preparation(a,execution_ledger=L)
    a=native.prepare_readiness(x,{profile!r},exp,execution_ledger=L,capacity=exact)
    assert m._counts['AB']==exact
    m.release_preparation(a,execution_ledger=L)
    before=m.capacity_snapshot(execution_ledger=L)
    expect(E.CAPACITY_EXCEEDED,lambda:native.prepare_readiness(x,{profile!r},exp,
        execution_ledger=L,capacity=exact-1))
    assert m.capacity_snapshot(execution_ledger=L)==before
    assert not old._domain.stopped and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("profile", ["events", "workers"])
@pytest.mark.parametrize("short", [False, True])
def test_readiness_B_exact_short_and_alias_occurrences(short, profile):
    run(f"""
    exp=pinned({profile!r})
    exact=getsizeof(exp.components)+sum(getsizeof(v)+sum(getsizeof(getattr(v,name))
        for name in ('component','version','migration_digest','catalog_contract_id','scope_format_id','intent_format_id'))
        for v in exp.components)
    if {profile!r}=='workers':
        assert exp.components[0].migration_digest is exp.components[1].migration_digest
    L,x,actual,c,r,a,t,b,exp=readiness_setup(profile={profile!r},capacity=exact-{int(short)})
    req=m._preparations[a._stamp]['data']
    assert m._typed_result_size(req,exp.components)==exact
    assert exact<=native.READINESS_RESULT_CAPACITY
    # Explicit publication with shared scalar references proves occurrence accounting.
    m._start_operation(t,b,L)
    if {short!r}:
        expect(E.CAPACITY_EXCEEDED,lambda:m.set_result(b,exp.components,execution_ledger=L))
        assert not m._results[b._stamp]['populated']
    else:
        m.set_result(b,exp.components,execution_ledger=L)
        assert m._results[b._stamp]['data'] is exp.components
    print('MANAGED_BODY_COMPLETE')
    """)


def test_readiness_malformed_preparation_is_local_detached_and_refunded():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);exp=pinned()
    object.__setattr__(exp.components[0],'version',True)
    before=m.capacity_snapshot(execution_ledger=L)
    try:native.prepare_readiness(x,'workers',exp,execution_ledger=L)
    except PersistenceError as error:
        assert error.code is E.LOCAL_INVALID_ARGUMENT and not error.unconfirmed
        assert error.__cause__ is None and error.__context__ is None
    else:raise AssertionError('missing rejection')
    assert m.capacity_snapshot(execution_ledger=L)==before and not Cursor.instances
    assert not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_readiness_retained_preparation_revalidation_rejects_tamper():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);exp=pinned()
    req=B._freeze_request_raw(C.get_statement('E33'),('workers',),
        context=B._return_context_raw(readiness=exp))
    object.__setattr__(exp.components[1],'scope_format_id','tampered')
    a=m.reserve_preparation(x,4096,execution_ledger=L)
    expect(E.LOCAL_INVALID_ARGUMENT,lambda:m.set_preparation(a,req,execution_ledger=L))
    assert not Cursor.instances and m._preparations[a._stamp]['data'] is None
    m.release_preparation(a,execution_ledger=L)
    assert m._counts['A']==0 and m._counts['AB']==0 and not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("profile", ["events", "workers"])
@pytest.mark.parametrize("short", [False, True])
def test_readiness_native_result_exact_capacity(short, profile):
    run(f"""
    exp=pinned({profile!r})
    exact=getsizeof(exp.components)+sum(getsizeof(v)+sum(getsizeof(getattr(v,name))
        for name in ('component','version','migration_digest','catalog_contract_id','scope_format_id','intent_format_id'))
        for v in exp.components)
    L,x,actual,c,r,a,t,b,exp=readiness_setup(profile={profile!r},capacity=exact-{int(short)})
    if {short!r}:
        expect(E.CAPACITY_EXCEEDED,lambda:native.execute(t,b,execution_ledger=L))
        assert m._ticket(t,L).operation['state']=='HELD' and L.uncertainty.present
        assert not m._results[b._stamp]['populated']
    else:
        native.execute(t,b,execution_ledger=L)
        got=m.read_result(b,execution_ledger=L)
        assert got==exp.components and not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)
