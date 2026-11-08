"""Synthetic controller tests only: no native driver or service qualification."""

from test_managed_lifecycle import _FIXTURE, _run
from test_native_workers_profile import _JOB_SETUP, _WORKERS, workers_companion

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
