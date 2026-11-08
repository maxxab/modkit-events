"""Synthetic controller tests only: no native driver or service qualification."""

import pytest
from test_managed_lifecycle import _FIXTURE, _run
from test_native_workers_profile import _JOB_SETUP, _LIST_SETUP, _WORKERS, workers_companion

pytestmark = workers_companion

_SETUP = (
    _WORKERS
    + """
from modkit_events.persistence import native_profile as P
original_limits=limits
def limits(**overrides):
    values=dict(prepare_bytes=100000000,prepare_bytes_per_execution=50000000,result_bytes=100000000,result_bytes_per_ticket=50000000,construction_slots=4)
    values.update(overrides)
    return original_limits(**values)
def profile():
    return P.WorkersNativeOperation(statement=WC.get_statement('W02'),request_type=WM.JobReadRequest,build_request=WB._read_job_raw,decode_rows=WR._decode_read_raw,validate_result=WR._validate_read_result_raw,result_types=(WO.JobRecord,WO.JobDetails,WO.JobPayload))
logical=WM.JobReadRequest(work_id='00000000-0000-0000-0000-000000000001')
"""
)


def test_paid_component_builder_and_retained_profile_owned_by_live_issuer():
    _run(
        _FIXTURE
        + _SETUP
        + r"""
assert hasattr(m,'_prepare_component'), 'paid component entry missing'
L,x,actual,c=setup_physical()
WB._saved=WB._read_job_raw
WB._controller=m
exec('def _read_job_raw(request, /):\n    assert _controller._counts["D"] == 1\n    assert _controller._counts["A"] == 1 and _controller._counts["AB"] > 0\n    return _saved(request)', WB.__dict__)
op=profile()
a=m._prepare_component(x,op,logical,execution_ledger=L)
req=m._preparations[a._stamp]['data']
assert m._preparations[a._stamp]['profile'] is op
r=active_root(c,L)
t=m.admit(r,a,execution_ledger=L)
b=m.reserve_result(t,P.result_capacity(op),execution_ledger=L)
with m._construction(False) as issuer:
    assert m._start_operation(t,b,L,reservation=issuer) is req
    assert m._operation_profile(t,L,reservation=issuer) is op
    with m._construction(False) as wrong:
        expect(E.INVALID_OBSERVATION,lambda:m._operation_profile(t,L,reservation=wrong))
    expect(E.RESOURCE_BUSY,lambda:m.read_result(b,execution_ledger=L))
    m.set_result(b,None,execution_ledger=L)
    expect(E.RESOURCE_BUSY,lambda:m.read_result(b,execution_ledger=L))
    m._complete_operation(t,L,known=True)
assert m.read_result(b,execution_ledger=L) is None
m.release_result(b,execution_ledger=L)
m.release_ticket(t,execution_ledger=L)
m.release_preparation(a,execution_ledger=L)
assert m.capacity_snapshot(execution_ledger=L)['AB']==0
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_known_builder_rejection_refunds_only_unreturned_graph():
    _run(
        _FIXTURE
        + _SETUP
        + """
L,x,actual,c=setup_physical()
before=m.capacity_snapshot(execution_ledger=L)
bad=object.__new__(WM.JobReadRequest)
object.__setattr__(bad,'work_id','bad')
expect(E.LOCAL_INVALID_ARGUMENT,lambda:m._prepare_component(x,profile(),bad,execution_ledger=L))
assert m.capacity_snapshot(execution_ledger=L)==before
assert not old._domain.stopped
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_unexpected_builder_primary_retains_paid_backing():
    _run(
        _FIXTURE
        + _SETUP
        + r"""
L,x,actual,c=setup_physical()
WB._primary=ValueError('unexpected raw primary')
exec('def _read_job_raw(request, /):\n    raise _primary',WB.__dict__)
try:m._prepare_component(x,profile(),logical,execution_ledger=L)
except ValueError as caught: assert caught is WB._primary
else:raise AssertionError('lost primary')
snapshot=m.capacity_snapshot(execution_ledger=L)
assert snapshot['A']==1 and snapshot['AB']>0 and snapshot['D']==1
assert old._domain.stopped
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_exact_size_and_one_byte_below_full_a_and_b_graphs():
    _run(
        _FIXTURE
        + _JOB_SETUP
        + """
from sys import getsizeof
original_limits=limits
def limits(**overrides):
    return original_limits(prepare_bytes=100000000,prepare_bytes_per_execution=50000000,result_bytes=100000000,result_bytes_per_ticket=50000000)
L,x,actual,c=setup_physical()
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
submit_op=operation('W01')
size=P._request_size(submit,submit_op)
with m._construction(False) as paid:
    small,code=m._reserve_preparation_paid(x,size-1,L,paid)
    assert code is None
    assert m._set_preparation_paid(small,submit,L,paid,operation=submit_op) is E.CAPACITY_EXCEEDED
    assert m._preparations[small._stamp]['data'] is None
    assert m._release_preparation_paid(small,L,paid) is None
    exact,code=m._reserve_preparation_paid(x,size,L,paid)
    assert code is None
    assert m._set_preparation_paid(exact,submit,L,paid,operation=submit_op) is None
    assert m._preparations[exact._stamp]['data'] is submit
m.release_preparation(exact,execution_ledger=L)
read_op=operation('W02')
logical=WM.JobReadRequest(work_id=str(submit.parameters[0]))
a=m._prepare_component(x,read_op,logical,execution_ledger=L)
req=m._preparations[a._stamp]['data']
result=WR._decode_read_raw(req,(read_row(submit,True),))
size=P._result_size(req,result,read_op)
r=active_root(c,L)
t=m.admit(r,a,execution_ledger=L)
b=m.reserve_result(t,size-1,execution_ledger=L)
with m._construction(False) as issuer:
    m._start_operation(t,b,L,reservation=issuer)
    expect(E.CAPACITY_EXCEEDED,lambda:m.set_result(b,result,execution_ledger=L))
    assert not m._results[b._stamp]['populated']
    expect(E.RESOURCE_BUSY,lambda:m.read_result(b,execution_ledger=L))
    # Source harness simulates issuer failure containment, no root is reusable.
    m._fail_operation_paid(t,L,issuer,stopped=True)
assert m._results[b._stamp]['capacity']==size-1
expect(E.RESOURCE_BUSY,lambda:m.release_result(b,execution_ledger=L),True)
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_exact_b_size_publishes_same_full_graph_only_after_completion():
    _run(
        _FIXTURE
        + _JOB_SETUP
        + """
original_limits=limits
def limits(**overrides):
    return original_limits(prepare_bytes=100000000,prepare_bytes_per_execution=50000000,result_bytes=100000000,result_bytes_per_ticket=50000000)
L,x,actual,c=setup_physical()
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
op=operation('W02')
a=m._prepare_component(x,op,WM.JobReadRequest(work_id=str(submit.parameters[0])),execution_ledger=L)
req=m._preparations[a._stamp]['data']
value=WR._decode_read_raw(req,(read_row(submit,True),))
size=P._result_size(req,value,op)
r=active_root(c,L);t=m.admit(r,a,execution_ledger=L);b=m.reserve_result(t,size,execution_ledger=L)
with m._construction(False) as issuer:
    assert m._start_operation(t,b,L,reservation=issuer) is req
    m.set_result(b,value,execution_ledger=L)
    expect(E.RESOURCE_BUSY,lambda:m.read_result(b,execution_ledger=L))
    expect(E.RESOURCE_BUSY,lambda:m.release_result(b,execution_ledger=L))
    m._complete_operation(t,L,known=True)
assert m.read_result(b,execution_ledger=L) is value
assert m.capacity_snapshot(execution_ledger=L)['BB']==size
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_oversized_ordinary_job_rejects_before_unbounded_copy_with_no_leak():
    _run(
        _FIXTURE
        + _JOB_SETUP
        + """
original_limits=limits
def limits(**overrides):
    return original_limits(prepare_bytes=100000000,prepare_bytes_per_execution=50000000,result_bytes=100000000,result_bytes_per_ticket=50000000)
L,x,actual,c=setup_physical()
# Public construction intentionally succeeds before native preparation.
logical=WM.JobSubmitRequest(job=job({'items':tuple(range(65537))}))
def forbidden(*a,**kw):raise AssertionError('unbounded copy or premature replay reached')
WM._logical_json=forbidden
WB.replace=forbidden
B._emit_raw=forbidden
before=m.capacity_snapshot(execution_ledger=L)
expect(E.LOCAL_INVALID_ARGUMENT,lambda:m._prepare_component(x,operation('W01'),logical,execution_ledger=L))
assert m.capacity_snapshot(execution_ledger=L)==before
assert not old._domain.stopped
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_read_preparation_charges_readiness_none_at_exact_capacity():
    _run(
        _FIXTURE
        + _JOB_SETUP
        + """
from sys import getsizeof
original_limits=limits
def limits(**overrides):
    return original_limits(prepare_bytes=100000000,prepare_bytes_per_execution=50000000,result_bytes=100000000,result_bytes_per_ticket=50000000)
L,x,actual,c=setup_physical()
op=operation('W02')
request=WB._read_job_raw(WM.JobReadRequest(work_id='ffffffff-ffff-ffff-ffff-ffffffffffff'))
expected=sum(getsizeof(value) for value in (request,request.parameters,request.parameters[0],request.parameters[0].int,request.context,request.context.expected,request.context.readiness))
assert P._request_size(request,op)==expected
assert P._preparation_capacity(op)==expected
for capacity in (expected-1,expected):
    with m._construction(False) as paid:
        preparation,code=m._reserve_preparation_paid(x,capacity,L,paid)
        assert code is None
        code=m._set_preparation_paid(preparation,request,L,paid,operation=op)
        assert code is (E.CAPACITY_EXCEEDED if capacity<expected else None)
        assert m._preparations[preparation._stamp]['data'] is (None if capacity<expected else request)
        assert m._release_preparation_paid(preparation,L,paid) is None
assert m.capacity_snapshot(execution_ledger=L)['AB']==0
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_retained_capacity_query_uses_only_live_component_ticket():
    _run(
        _FIXTURE
        + _SETUP
        + """
assert hasattr(m,'result_capacity'), 'retained ticket capacity query missing'
L,x,actual,c=setup_physical()
op=profile()
a=m._prepare_component(x,op,logical,execution_ledger=L)
r=active_root(c,L)
t=m.admit(r,a,execution_ledger=L)
before=m.capacity_snapshot(execution_ledger=L)
assert m.result_capacity(t,execution_ledger=L)==P.result_capacity(op)
assert m.capacity_snapshot(execution_ledger=L)==before
expect(E.INVALID_OBSERVATION,lambda:m.result_capacity(t,execution_ledger=ExecutionLedger()))
expect(E.INVALID_OBSERVATION,lambda:m.result_capacity(a,execution_ledger=L))
m.release_ticket(t,execution_ledger=L)
expect(E.INVALID_OBSERVATION,lambda:m.result_capacity(t,execution_ledger=L))
assert not L.uncertainty.present and not old._domain.stopped
print('MANAGED_BODY_COMPLETE')
"""
    )


_LIST_LIFECYCLE = (
    _LIST_SETUP
    + """
original_limits=limits
def limits(**overrides):
    values=dict(prepare_bytes=100000000,prepare_bytes_per_execution=50000000,result_bytes=100000000000,result_bytes_per_ticket=100000000000,construction_slots=4)
    values.update(overrides)
    return original_limits(**values)
"""
)


def test_listing_reservation_uses_its_own_retained_limit_not_another_quote():
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + """
L,x,actual,c=setup_physical();r=active_root(c,L)
op=listing()
small=m._prepare_component(x,op,WM.JobListRequest(after=None,limit=1),execution_ledger=L,max_page_payload_bytes=Q)
large=m._prepare_component(x,op,WM.JobListRequest(after=None,limit=256),execution_ledger=L,max_page_payload_bytes=Q)
ticket=m.admit(r,small,execution_ledger=L)
quote=m.result_capacity(ticket,execution_ledger=L)
m.release_ticket(ticket,execution_ledger=L)
ticket=m.admit(r,large,execution_ledger=L)
required=m.result_capacity(ticket,execution_ledger=L)
assert required>quote
before=m.capacity_snapshot(execution_ledger=L)
for capacity in (quote,required-1):
    expect(E.CAPACITY_EXCEEDED,lambda:m.reserve_result(ticket,capacity,execution_ledger=L))
    assert m.capacity_snapshot(execution_ledger=L)==before
    assert not L.uncertainty.present and not old._domain.stopped
result=m.reserve_result(ticket,required,execution_ledger=L)
assert m.capacity_snapshot(execution_ledger=L)['BB']==required
m.release_result(result,execution_ledger=L)
m.release_ticket(ticket,execution_ledger=L)
m.release_preparation(small,execution_ledger=L)
m.release_preparation(large,execution_ledger=L)
assert m.capacity_snapshot(execution_ledger=L)['AB']==0
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_listing_start_rechecks_underfunded_result_before_running():
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + """
L,x,actual,c=setup_physical();r=active_root(c,L)
op=listing()
a=m._prepare_component(x,op,WM.JobListRequest(after=None,limit=2),execution_ledger=L,max_page_payload_bytes=Q)
t=m.admit(r,a,execution_ledger=L)
required=m.result_capacity(t,execution_ledger=L)
b=m.reserve_result(t,required,execution_ledger=L)
# Local corrupt-record control proves the issuer does not trust reserve/query.
m._results[b._stamp]['capacity']=required-1
before=m.capacity_snapshot(execution_ledger=L)
with m._construction(False) as issuer:
    expect(E.CAPACITY_EXCEEDED,lambda:m._start_operation(t,b,L,reservation=issuer))
    assert m._ticket(t,L).operation['state']=='ADMITTED'
    assert not m._ticket(t,L).operation['running']
assert m.capacity_snapshot(execution_ledger=L)==before
assert not L.uncertainty.present and not old._domain.stopped
m._results[b._stamp]['capacity']=required
with m._construction(False) as issuer:
    assert m._start_operation(t,b,L,reservation=issuer) is m._preparations[a._stamp]['data']
    expect(E.INVALID_OBSERVATION,lambda:m.result_capacity(t,execution_ledger=L))
    value=()
    m.set_result(b,value,execution_ledger=L)
    m._complete_operation(t,L,known=True)
assert m.read_result(b,execution_ledger=L) is value
assert m.capacity_snapshot(execution_ledger=L)['BB']==required
value=None
m.release_result(b,execution_ledger=L)
m.release_ticket(t,execution_ledger=L)
m.release_preparation(a,execution_ledger=L)
print('MANAGED_BODY_COMPLETE')
"""
    )


@pytest.mark.parametrize("budget", ["result_bytes", "result_bytes_per_ticket"])
def test_listing_configured_budget_rejects_without_charges_or_uncertainty(budget):
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + f"budget={budget!r}\n"
        + """
op=listing();request=list_request(2)
required=P.result_capacity(op,request=request,max_page_payload_bytes=Q)
normal_limits=limits
def limits(**overrides):
    values=({'result_bytes':2*required-1,'result_bytes_per_ticket':required}
            if budget=='result_bytes' else {'result_bytes_per_ticket':required-1})
    return normal_limits(**values)
L,x,actual,c=setup_physical();r=active_root(c,L)
a=m._prepare_component(x,op,WM.JobListRequest(after=None,limit=2),execution_ledger=L,max_page_payload_bytes=Q)
t=m.admit(r,a,execution_ledger=L)
if budget=='result_bytes':
    other_actual=Physical();other_checkout=m.attach_native(other_actual,x,execution_ledger=L)
    other_root=active_root(other_checkout,L);other_ticket=m.admit(other_root,a,execution_ledger=L)
    other_result=m.reserve_result(other_ticket,required,execution_ledger=L)
before=m.capacity_snapshot(execution_ledger=L)
expect(E.CAPACITY_EXCEEDED,lambda:m.reserve_result(t,required,execution_ledger=L))
assert m.capacity_snapshot(execution_ledger=L)==before
assert not L.uncertainty.present and not old._domain.stopped
if budget=='result_bytes':
    m.release_result(other_result,execution_ledger=L);m.release_ticket(other_ticket,execution_ledger=L)
m.release_ticket(t,execution_ledger=L);m.release_preparation(a,execution_ledger=L)
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_listing_query_rejects_mismatched_retained_request_and_record_locally():
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + """
from dataclasses import replace
L,x,actual,c=setup_physical();r=active_root(c,L)
op=listing()
a=m._prepare_component(x,op,WM.JobListRequest(after=None,limit=2),execution_ledger=L,max_page_payload_bytes=Q)
t=m.admit(r,a,execution_ledger=L)
prep=m._preparations[a._stamp];request=prep['data']
before=m.capacity_snapshot(execution_ledger=L)
prep['data']=P.freeze_request(replace(op.statement),(b'jobs',None,None,2),context=B._return_context_raw())
expect(E.PROFILE_REJECTED,lambda:m.result_capacity(t,execution_ledger=L))
prep['data']=request
physical=m._ticket(t,L)
physical.operation['prep']=dict(prep)
expect(E.INVALID_OBSERVATION,lambda:m.result_capacity(t,execution_ledger=L))
physical.operation['prep']=prep
current=physical.current
physical.current=None
expect(E.INVALID_OBSERVATION,lambda:m.result_capacity(t,execution_ledger=L))
physical.current=current
assert m.capacity_snapshot(execution_ledger=L)==before
assert not L.uncertainty.present and not old._domain.stopped
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_listing_paid_builder_preserves_exact_preparation_and_capacity_query_primary():
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + r"""
L,x,actual,c=setup_physical()
WB._saved_listing=WB._list_jobs_raw;WB._controller=m
exec('def _list_jobs_raw(request, /):\n    assert _controller._counts["A"] == 1 and _controller._counts["AB"] > 0\n    assert _controller._counts["D"] == 1\n    return _saved_listing(request)',WB.__dict__)
op=listing()
a=m._prepare_component(x,op,WM.JobListRequest(after=None,limit=1),execution_ledger=L,max_page_payload_bytes=Q)
r=active_root(c,L);t=m.admit(r,a,execution_ledger=L)
primary=RuntimeError('query primary');cause=ValueError('cause');context=KeyError('context')
primary.__cause__=cause;primary.__context__=context;primary.__suppress_context__=False
def broken(*args,**kwargs):raise primary
P.result_capacity=broken
try:m.result_capacity(t,execution_ledger=L)
except RuntimeError as caught:
    assert caught is primary and caught.__cause__ is cause and caught.__context__ is context
    assert caught.__suppress_context__ is False
else:raise AssertionError('query primary swallowed')
snapshot=m.capacity_snapshot(execution_ledger=L)
assert snapshot['A']==1 and snapshot['AB']>0 and snapshot['D']==1
assert old._domain.stopped
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_listing_known_builder_rejection_refunds_the_paid_preparation():
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + """
L,x,actual,c=setup_physical()
before=m.capacity_snapshot(execution_ledger=L)
for limit in (0,257,True):
    logical=object.__new__(WM.JobListRequest)
    object.__setattr__(logical,'after',None)
    object.__setattr__(logical,'limit',limit)
    expect(E.LOCAL_INVALID_ARGUMENT,lambda:m._prepare_component(x,listing(),logical,execution_ledger=L,max_page_payload_bytes=Q))
    assert m.capacity_snapshot(execution_ledger=L)==before
    assert not L.uncertainty.present and not old._domain.stopped
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_listing_budget_is_retained_under_paid_preparation_and_owned_by_issuer():
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + """
assert hasattr(m,'_operation_max_page_payload_bytes'), 'issuer budget lookup missing'
L,x,actual,c=setup_physical()
budget=int('2147483648')
op=listing()
a=m._prepare_component(x,op,WM.JobListRequest(after=None,limit=256),execution_ledger=L,max_page_payload_bytes=budget)
prep=m._preparations[a._stamp];request=prep['data']
assert prep['max_page_payload_bytes'] is budget
assert len(request.parameters)==4 and request.context.expected==() and request.context.readiness is None
r=active_root(c,L);t=m.admit(r,a,execution_ledger=L)
required=m.result_capacity(t,execution_ledger=L)
assert required==P.result_capacity(op,request=request,max_page_payload_bytes=budget)
b=m.reserve_result(t,required,execution_ledger=L)
with m._construction(False) as issuer:
    expect(E.INVALID_OBSERVATION,lambda:m._operation_max_page_payload_bytes(t,L,reservation=issuer))
    m._start_operation(t,b,L,reservation=issuer)
    assert m._operation_max_page_payload_bytes(t,L,reservation=issuer) is budget
    with m._construction(False) as wrong:
        expect(E.INVALID_OBSERVATION,lambda:m._operation_max_page_payload_bytes(t,L,reservation=wrong))
    m.set_result(b,(),execution_ledger=L);m._complete_operation(t,L,known=True)
expect(E.INVALID_OBSERVATION,lambda:m._operation_max_page_payload_bytes(t,L,reservation=issuer))
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_listing_invalid_common_budget_rejects_before_builder_and_refunds():
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + r"""
L,x,actual,c=setup_physical()
exec('def _list_jobs_raw(request, /):\n    raise AssertionError("builder reached for invalid budget")',WB.__dict__)
op=listing();logical=WM.JobListRequest(after=None,limit=1)
before=m.capacity_snapshot(execution_ledger=L)
class Integer(int):pass
for budget in (None,True,Integer(1),0,-1,3758096385):
    expect(E.LOCAL_INVALID_ARGUMENT,lambda:m._prepare_component(x,op,logical,execution_ledger=L,max_page_payload_bytes=budget))
    assert m.capacity_snapshot(execution_ledger=L)==before
expect(E.LOCAL_INVALID_ARGUMENT,lambda:m._prepare_component(x,op,logical,execution_ledger=L))
expect(E.LOCAL_INVALID_ARGUMENT,lambda:m._prepare_component(x,operation('W02'),WM.JobReadRequest(work_id=str(UUID(int=1))),execution_ledger=L,max_page_payload_bytes=1))
assert m.capacity_snapshot(execution_ledger=L)==before and not old._domain.stopped
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_listing_budget_metadata_is_revalidated_at_query_reserve_and_start():
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + """
L,x,actual,c=setup_physical()
a=m._prepare_component(x,listing(),WM.JobListRequest(after=None,limit=2),execution_ledger=L,max_page_payload_bytes=Q)
r=active_root(c,L);t=m.admit(r,a,execution_ledger=L)
required=m.result_capacity(t,execution_ledger=L);prep=m._preparations[a._stamp]
class Integer(int):pass
for value in (None,True,Integer(1),0,3758096385):
    prep['max_page_payload_bytes']=value
    before=m.capacity_snapshot(execution_ledger=L)
    expect(E.PROFILE_REJECTED,lambda:m.result_capacity(t,execution_ledger=L))
    expect(E.PROFILE_REJECTED,lambda:m.reserve_result(t,required,execution_ledger=L))
    assert m.capacity_snapshot(execution_ledger=L)==before
prep.pop('max_page_payload_bytes')
expect(E.PROFILE_REJECTED,lambda:m.result_capacity(t,execution_ledger=L))
prep['max_page_payload_bytes']=Q
b=m.reserve_result(t,required,execution_ledger=L)
before=m.capacity_snapshot(execution_ledger=L)
with m._construction(False) as issuer:
    for value in (None,True,Integer(1),0,3758096385):
        prep['max_page_payload_bytes']=value
        expect(E.PROFILE_REJECTED,lambda:m._start_operation(t,b,L,reservation=issuer))
        assert m._ticket(t,L).operation['state']=='ADMITTED'
    prep['max_page_payload_bytes']=Q
assert m.capacity_snapshot(execution_ledger=L)==before
assert not L.uncertainty.present and not old._domain.stopped
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_listing_exact_a_charge_includes_budget_and_only_w03_metadata_growth():
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + """
from sys import getsizeof
L,x,actual,c=setup_physical()
op=listing();budget=int('3758096384')
request=list_request(256,M.WorkCursor(created_at=now,work_id=UUID(int=2**128-1)))
keys=('token','capacity','data','borrows','x','builder','profile')
metadata=dict.fromkeys(keys);before=getsizeof(metadata);metadata['max_page_payload_bytes']=None
growth=max(0,getsizeof(metadata)-before)
exact=sum(getsizeof(value) for value in (request,request.parameters,request.context,request.context.expected,request.context.readiness))
exact+=sum(getsizeof(value) for value in request.parameters)+getsizeof(request.parameters[2].int)
exact+=getsizeof(budget)+growth
assert P._request_size(request,op,max_page_payload_bytes=budget)==exact
assert exact<=P._preparation_capacity(op,max_page_payload_bytes=budget)
for capacity in (exact-1,exact):
    with m._construction(False) as paid:
        a,code=m._reserve_preparation_paid(x,capacity,L,paid)
        assert code is None and 'max_page_payload_bytes' not in m._preparations[a._stamp]
        code=m._set_preparation_paid(a,request,L,paid,operation=op,max_page_payload_bytes=budget)
        if capacity<exact:
            assert code is E.CAPACITY_EXCEEDED
            assert m._preparations[a._stamp]['data'] is None
            assert 'max_page_payload_bytes' not in m._preparations[a._stamp]
        else:
            assert code is None
            assert m._preparations[a._stamp]['data'] is request
            assert m._preparations[a._stamp]['max_page_payload_bytes'] is budget
        assert m._release_preparation_paid(a,L,paid) is None
assert m.capacity_snapshot(execution_ledger=L)['AB']==0
a=m._prepare_component(x,operation('W02'),WM.JobReadRequest(work_id=str(UUID(int=1))),execution_ledger=L)
assert 'max_page_payload_bytes' not in m._preparations[a._stamp]
m.release_preparation(a,execution_ledger=L)
print('MANAGED_BODY_COMPLETE')
"""
    )


@pytest.mark.parametrize("over_budget", [False, True])
def test_listing_publication_uses_retained_aggregate_and_never_publishes_prefix(over_budget):
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + f"over_budget={over_budget!r}\n"
        + """
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({'x':'payload'})))
rows=[]
for ident,resolved in ((UUID(int=1),False),(UUID(int=2),True)):
    row=list(read_row(submit,resolved));row[0]=ident;row[56]=ident
    if resolved:row[42]=ident
    rows.append(tuple(row))
names=('intent_evidence','semantic_input','replay_input','protected_binding','result','resolution_record_result','resolution_record_evidence','resolution_record_binding','job_protected_binding','job_semantic_input','protected_sidecar','protected_reference','protected_recovery_metadata','projection_metadata')
columns=WC.get_statement('W03').result.columns
exact=0
for row in rows:
    wire=dict(zip((column.name for column in columns),row))
    exact+=sum(len(wire[name]) for name in names if wire[name] is not None)
budget=exact-int(over_budget)
L,x,actual,c=setup_physical();op=listing()
a=m._prepare_component(x,op,WM.JobListRequest(after=None,limit=2),execution_ledger=L,max_page_payload_bytes=budget)
request=m._preparations[a._stamp]['data'];value=WR._decode_list_raw(request,tuple(rows))
r=active_root(c,L);t=m.admit(r,a,execution_ledger=L)
required=m.result_capacity(t,execution_ledger=L);b=m.reserve_result(t,required,execution_ledger=L)
with m._construction(False) as issuer:
    m._start_operation(t,b,L,reservation=issuer)
    if over_budget:
        expect(E.INVALID_OBSERVATION,lambda:m.set_result(b,value,execution_ledger=L))
        assert m._results[b._stamp]['data'] is None and not m._results[b._stamp]['populated']
        m._fail_operation_paid(t,L,issuer,stopped=True)
    else:
        m.set_result(b,value,execution_ledger=L);m._complete_operation(t,L,known=True)
assert m.capacity_snapshot(execution_ledger=L)['BB']==required
if over_budget:
    assert m._ticket(t,L).operation['state']=='HELD'
    assert m._root(r,L)[1]['state']=='UNKNOWN' and L.uncertainty.present
else:
    assert m.read_result(b,execution_ledger=L) is value
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_listing_single_operation_configuration_fits_default_256_page_and_two_d_slots():
    _run(
        _FIXTURE
        + _LIST_LIFECYCLE
        + """
op=listing();required=P.result_capacity(op,request=list_request(256),max_page_payload_bytes=Q)
normal_limits=limits
def limits(**overrides):
    return normal_limits(retained_cells=1,admitted_live=1,checkouts=1,roots=1,roots_per_checkout=1,executions=1,preparations=1,preparations_per_execution=1,results=1,results_per_ticket=1,prepare_bytes=1024,prepare_bytes_per_execution=1024,result_bytes=required,result_bytes_per_ticket=required,construction_slots=2,cleanup_bundles=1,cleanup_bytes=1024)
L,x,actual,c=setup_physical()
a=m._prepare_component(x,op,WM.JobListRequest(after=None,limit=256),execution_ledger=L,max_page_payload_bytes=Q)
r=active_root(c,L);t=m.admit(r,a,execution_ledger=L)
b=m.reserve_result(t,required,execution_ledger=L)
snapshot=m.capacity_snapshot(execution_ledger=L)
assert all(snapshot[key]==1 for key in ('P','V','C','R','X','A','B'))
assert snapshot['AB']<=1024 and snapshot['BB']==required
with m._construction(False) as issuer:
    assert m.capacity_snapshot(execution_ledger=L)['D']==1
    with m._construction(False):
        assert m.capacity_snapshot(execution_ledger=L)['D']==2
    assert m._start_operation(t,b,L,reservation=issuer) is m._preparations[a._stamp]['data']
    m.set_result(b,(),execution_ledger=L);m._complete_operation(t,L,known=True)
assert m.read_result(b,execution_ledger=L)==()
assert m.capacity_snapshot(execution_ledger=L)['D']==0
assert m.capacity_snapshot(execution_ledger=L)['BB']==required
print('MANAGED_BODY_COMPLETE')
"""
    )
