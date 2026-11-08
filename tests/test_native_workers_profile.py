"""Source-only selected Workers shared semantic regressions."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_managed_lifecycle import _run

workers_companion = pytest.mark.skipif(
    os.environ.get("MODKIT_EVENTS_WORKERS_TESTS") != "1",
    reason="set MODKIT_EVENTS_WORKERS_TESTS=1 with installed Workers or explicit PYTHONPATH",
)


def test_raw_scope_and_replay_share_pure_rules_without_public_boundaries():
    _run("""
from modkit_events.persistence import scope as S, bindings as B
from modkit_events.persistence.errors import _ValidationReject
assert hasattr(S, '_scope_raw'), 'selected raw scope missing'
assert hasattr(B, '_emit_raw'), 'selected raw replay missing'
plain=S.Scope('app', 'tenant', 'owner')
canonical=S.canonical_scope(plain)
value={'z': [1,1.0,-0.0,'é\\n'], 'a': {'x': True}}
expected=B.encode_mapping_replay(value)
def forbidden(*a,**k): raise AssertionError('public sanitizer reached')
S.Scope.__post_init__=forbidden
S.decode_scope_fields=forbidden
S.canonical_scope=forbidden
raw=S._scope_raw('app', 'tenant', 'owner')
assert S._canonical_scope_raw(raw)==canonical
assert S._decode_canonical_scope_raw(canonical)==raw
assert B._emit_raw(B._parse_canonical_json_raw(B._canonical_json_raw(value)))==expected
for args in (('',), ('x'*257,), (object(),)):
    try: S._scope_raw(*args)
    except _ValidationReject as error: assert type(error) is _ValidationReject
    else: raise AssertionError('accepted invalid scope')
print('MANAGED_BODY_COMPLETE')
""")


def test_raw_admission_protected_and_context_retain_graph_and_primary():
    _run("""
from datetime import datetime, timezone, tzinfo
from uuid import UUID
from modkit_events.persistence import scope as S, bindings as B, models as M
from modkit_events.persistence.errors import _ValidationReject
assert hasattr(M, '_admission_input_raw'), 'raw admission missing'
now=datetime(2026,1,1,tzinfo=timezone.utc)
material=M.ProtectedBindingInput(material_state=M.MaterialState.ABSENT,codec=None,key_version=None,expires_at=None,cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=None,reference=None,content_binding=b'',recovery_metadata=b'',projection_metadata={})
protected=B.canonical_protected_binding(material).content
scope=S.Scope('app')
evidence=M.ScopeEvidence(canonical_version=1,canonical=S.canonical_scope(scope),application=b'app',tenant=None,owner=None)
identity=M.WorkIdentity(work_id=UUID(int=1),kind=M.WorkKind.JOB,subscription_id=None,namespace='jobs',command_type='task',scope=evidence,idempotency_key=None)
params=dict(identity=identity,schema_version=1,semantic_input=B.canonical_json({}),replay_input=b'{}',protected_binding=protected,replay_policy=M.ReplayPolicy.DISABLED,max_attempts=1,deadline=None,original_available_at=now)
pure=M.AdmissionInput(**params)
intent=B.canonical_intent(pure)
def forbidden(*a,**k): raise AssertionError('public sanitizer reached')
for cls in (M.AdmissionInput,M.WorkIdentity,M.ScopeEvidence,M.ProtectedBindingInput): cls.__post_init__=forbidden
for name in ('canonical_intent','decode_protected_binding','canonical_protected_binding','parse_canonical_json','canonical_json','decode_mapping_replay','version_to_decimal'): setattr(B,name,forbidden)
assert B._canonical_protected_binding_raw(material).content==protected
assert B._decode_protected_binding_raw(protected)==material
actual=M._admission_input_raw(**params)
assert actual.identity is identity and actual.original_available_at is now
assert B._canonical_intent_raw(actual)==intent
expected=(actual,)
context=B._return_context_raw(expected=expected)
assert context.expected is expected and context.expected[0] is actual
M._validate_admission_input_raw(actual)
primary=RuntimeError('raw primary')
def broken(*a,**k): raise primary
S._decode_canonical_scope_raw=broken
try: M._validate_admission_input_raw(actual)
except RuntimeError as caught: assert caught is primary
else: raise AssertionError('lost primary')
print('MANAGED_BODY_COMPLETE')
""")


def test_raw_work_decoder_validates_full_shape_and_retains_nested_identities():
    _run("""
from datetime import datetime, timezone
from uuid import UUID
from modkit_events.persistence import rows as R, observations as O, bindings as B, models as M, scope as S, catalog as C
assert hasattr(R, '_decode_work_observation_raw'), 'raw full Work decoder missing'
now=datetime(2026,1,1,tzinfo=timezone.utc)
scope=S.Scope('app')
material=M.ProtectedBindingInput(material_state=M.MaterialState.ABSENT,codec=None,key_version=None,expires_at=None,cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=None,reference=None,content_binding=b'',recovery_metadata=b'',projection_metadata={})
identity=M.WorkIdentity(work_id=UUID(int=1),kind=M.WorkKind.JOB,subscription_id=None,namespace='jobs',command_type='task',scope=M.ScopeEvidence(canonical_version=1,canonical=S.canonical_scope(scope),application=b'app',tenant=None,owner=None),idempotency_key=None)
admission=M.AdmissionInput(identity=identity,schema_version=1,semantic_input=B.canonical_json({}),replay_input=b'{}',protected_binding=B.canonical_protected_binding(material).content,replay_policy=M.ReplayPolicy.DISABLED,max_attempts=1,deadline=None,original_available_at=now)
data=B._admission_values(admission)
data['schema_version_decimal']=b'1'
data.update(runnable_version=1,state='queued',cancellation_requested=False,token=None,ownership_revision=0,lease_until=None,available_at=now,cycle=1,attempt_count=0,dispatch_id=None,result=None,created_at=now,updated_at=now,success_origin=None,completion_guard_id=None,final_fence_at=None,completion_result_digest=None,resolution_operation_id=None,terminal_resolution_operation_id=None,resolution=None)
expected=O.WorkObservation(**data)
values=tuple(data.get(col.name,False if col.name=='resolution_present' else None) for col in C.get_statement('E15').result.columns)
def forbidden(*a,**k): raise AssertionError('public constructor reached')
O.WorkObservation.__post_init__=forbidden
O.ResolutionObservation.__post_init__=forbidden
M.AdmissionInput.__post_init__=forbidden
actual=R._decode_work_observation_raw(values)
assert actual==expected and actual.work_id is values[0]
before=tuple(getattr(actual,name) for name in actual.__dataclass_fields__)
O._validate_work_observation_raw(actual)
assert all(getattr(actual,name) is value for name,value in zip(actual.__dataclass_fields__,before))
print('MANAGED_BODY_COMPLETE')
""")


_WORKERS = """
import os
# _run uses -I. Forward only the explicit caller search path, without any
# repository-relative discovery or substitute package/module loader.
sys.path[1:1] = [entry for entry in os.environ.get('PYTHONPATH', '').split(os.pathsep) if entry]
import modkit_workers
from modkit_workers.settings import WorkerSettings as _WorkerSettings
assert modkit_workers.__file__ and os.path.isfile(modkit_workers.__file__)
assert modkit_workers.__spec__.origin == modkit_workers.__file__
assert modkit_workers.WorkerSettings is _WorkerSettings
from modkit_workers.persistence import catalog as WC, models as WM, bindings as WB, rows as WR, observations as WO
"""


@workers_companion
def test_selected_profile_freezes_exact_graph_and_pins_finite_capacity():
    _run(
        _WORKERS
        + """
import importlib.util
assert importlib.util.find_spec('modkit_events.persistence.native_profile'), 'selected profile missing'
from modkit_events.persistence import native_profile as P
from modkit_events.persistence.errors import _ValidationReject
from dataclasses import replace
op=P.WorkersNativeOperation(statement=WC.get_statement('W02'),request_type=WM.JobReadRequest,build_request=WB._read_job_raw,decode_rows=WR._decode_read_raw,validate_result=WR._validate_read_result_raw,result_types=(WO.JobRecord,WO.JobDetails,WO.JobPayload))
request=op.build_request(WM.JobReadRequest(work_id='00000000-0000-0000-0000-000000000001'))
parameters,context,expected=request.parameters,request.context,request.context.expected
P.validate_request(request,op.statement)
assert request.parameters is parameters and request.context is context and context.expected is expected
assert type(P.result_capacity(op)) is int and P.result_capacity(op)>14*1048576
try: P.validate_request(request,replace(op.statement))
except _ValidationReject: pass
else: raise AssertionError('descriptor identity not preserved')
assert P._request_size(request,op)>sum(len(v.bytes) for v in parameters)
print('MANAGED_BODY_COMPLETE')
"""
    )


_JOB_SETUP = (
    _WORKERS
    + """
from datetime import datetime, timezone
from uuid import UUID
from modkit_events.persistence import bindings as B, models as M, scope as S, catalog as C, observations as O, native_profile as P
now=datetime(2026,1,1,tzinfo=timezone.utc)
material=M.ProtectedBindingInput(material_state=M.MaterialState.ABSENT,codec=None,key_version=None,expires_at=None,cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=None,reference=None,content_binding=b'',recovery_metadata=b'',projection_metadata={})
def job(payload):
    return WM.JobInput('00000000-0000-0000-0000-000000000001','task',1,S.Scope('app'),payload,original_available_at=now,protected=material)
def operation(key):
    submit=key=='W01'
    return P.WorkersNativeOperation(statement=WC.get_statement(key),request_type=WM.JobSubmitRequest if submit else WM.JobReadRequest,build_request=WB._submit_raw if submit else WB._read_job_raw,decode_rows=WR._decode_submit_raw if submit else WR._decode_read_raw,validate_result=WR._validate_submit_result_raw if submit else WR._validate_read_result_raw,result_types=(WO.JobAdmissionObservation,) if submit else (WO.JobRecord,WO.JobDetails,WO.JobPayload))
def read_row(request, resolved=False):
    admission=request.context.expected[0]
    data=B._admission_values_raw(admission)
    data.update(runnable_version=1,state='queued',cancellation_requested=False,token=None,ownership_revision=0,lease_until=None,available_at=now,cycle=1,attempt_count=0,dispatch_id=None,result=None,created_at=now,updated_at=now,success_origin=None,completion_guard_id=None,final_fence_at=None,completion_result_digest=None,resolution_operation_id=None,terminal_resolution_operation_id=None,resolution_present=False)
    if resolved:
        from hashlib import sha256
        data.update(state='succeeded',attempt_count=1,dispatch_id=UUID(int=2),result=b'result',success_origin='reconciled',resolution_operation_id=UUID(int=3),terminal_resolution_operation_id=UUID(int=3),resolution_present=True)
        resolution=dict(operation_id=UUID(int=3),operation_kind='work_resolution',work_id=UUID(int=1),expected_revision=0,cycle=1,attempt=1,dispatch_id=UUID(int=2),outcome='confirmed_success',retry_at=None,result=b'result',result_digest=sha256(b'result').digest(),reason=None,evidence=b'evidence',binding=b'binding',resolution_root_xid=1,recorded_at=now)
        resolution['operation_kind']=C.MUTATION_OPERATION_KINDS['E31'].value
        data.update(('resolution_record_'+name,value) for name,value in resolution.items())
    prefix=tuple(data.get(col.name) for col in C.get_statement('E15').result.columns)
    suffix=(admission.identity.work_id,b'app',None,None,admission.protected_binding,admission.semantic_input,'absent',None,None,None,None,None,b'','retain',B._canonical_json_raw({}))
    return prefix+suffix
"""
)


@workers_companion
def test_combined_submit_parity_and_full_optional_resolution_accounting():
    _run(
        _JOB_SETUP
        + """
from dataclasses import fields
from sys import getsizeof
for payload in ({'i':1,'f':1.0,'p':0.0,'n':-0.0}, {'z':(1,'é',{'a':'x'}),'a':10**4000}):
    logical=WM.JobSubmitRequest(job=job(payload))
    pure=WB.submit(logical)
    raw=WB._submit_raw(logical)
    assert raw.parameters==pure.parameters
    assert raw.context==pure.context
    assert P._request_size(raw,operation('W01'))<=P._preparation_capacity(operation('W01'))
raw=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
read=WB._read_job_raw(WM.JobReadRequest(work_id=str(raw.parameters[0])))
for resolved in (False,True):
    result=WR._decode_read_raw(read,(read_row(raw,resolved),))
    carriers=[result,result.work,result.details,result.payload]
    if resolved: carriers.append(result.work.resolution)
    independent=sum(getsizeof(carrier) for carrier in carriers)
    for carrier in carriers:
        for field in fields(carrier):
            value=getattr(carrier,field.name)
            if any(value is nested for nested in carriers):continue
            independent+=getsizeof(value)
            if type(value) is UUID:independent+=getsizeof(value.int)
    assert P._result_size(read,result,operation('W02'))==independent
    assert independent<=P.result_capacity(operation('W02'))
    before=(result.work,result.details,result.payload,result.work.resolution)
    operation('W02').validate_result(read,result)
    assert all(a is b for a,b in zip(before,(result.work,result.details,result.payload,result.work.resolution)))
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_selected_scalar_caps_reject_before_utf8_allocation_and_hooks():
    _run(
        _JOB_SETUP
        + """
from datetime import tzinfo
from modkit_events.persistence.errors import _ValidationReject
raw=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
values=list(read_row(raw))
values[1]='x'*33
saved=B._utf8
def forbidden(*a,**k):raise AssertionError('oversized scalar encoded before cap')
B._utf8=forbidden
try:P.decode_columns(WC.get_statement('W02'),tuple(values))
except _ValidationReject as error:assert type(error) is _ValidationReject
else:raise AssertionError('oversized kind accepted')
B._utf8=saved
class EvilZone(tzinfo):
    def utcoffset(self, value):raise AssertionError('tzinfo hook reached')
for value in (datetime(2026,1,1,tzinfo=EvilZone()),):
    try:B._instant_raw(value)
    except _ValidationReject:pass
    else:raise AssertionError('custom zone accepted')
uuid=UUID(int=1)
object.__setattr__(uuid,'int',object())
try:B._uuid_raw(uuid)
except _ValidationReject:pass
else:raise AssertionError('UUID custom graph accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_trusted_profile_validation_needs_no_reverse_workers_module_lookup():
    _run(
        _JOB_SETUP
        + """
from dataclasses import replace
op=operation('W02')
loaded={name:module for name,module in tuple(sys.modules.items()) if name.startswith('modkit_workers')}
for name in loaded:del sys.modules[name]
P._validate_operation(op)
assert P.result_capacity(op)>14*1048576
sys.modules.update(loaded)
# Equivalent startup metadata can describe a profile, but cannot replace the
# descriptor returned by the selected builder during paid preparation.
copy=replace(op,statement=replace(op.statement))
request=op.build_request(WM.JobReadRequest(work_id='00000000-0000-0000-0000-000000000001'))
from modkit_events.persistence.errors import _ValidationReject
try:P._request_size(request,copy)
except _ValidationReject:pass
else:raise AssertionError('different builder descriptor accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_full_large_legal_graphs_fit_derived_bounds_and_no_broad_sanitizers():
    _run(
        _JOB_SETUP
        + """
from dataclasses import replace
from sys import getsizeof
material=M.ProtectedBindingInput(material_state=M.MaterialState.PRESENT,codec='c'*256,key_version='k'*256,expires_at=now,cleanup_policy=M.CleanupPolicy.ERASE_AFTER_TERMINAL,sidecar=b's'*350000,reference=None,content_binding=b'c'*250000,recovery_metadata=B.canonical_json({'r':'r'*50000}),projection_metadata=B.canonical_json({'p':'p'*50000}))
logical=WM.JobSubmitRequest(job=WM.JobInput('ffffffff-ffff-ffff-ffff-ffffffffffff','x'*256,10**4096-1,S.Scope('a'*256,'t'*256,'o'*256),{'x':'x'*100000},original_available_at=now,protected=material,idempotency_key='k'*256,deadline=now,max_attempts=1000))
raw=WB._submit_raw(logical)
assert P._request_size(raw,operation('W01'))<=P._preparation_capacity(operation('W01'))
# Poison every broad constructor reached by the historical call graph.
def forbidden(*args,**kwargs):raise AssertionError('broad public sanitizer reached')
for cls in (S.Scope,M.ScopeEvidence,M.WorkIdentity,M.AdmissionInput,M.ProtectedBindingInput,O.WorkObservation,O.ResolutionObservation):cls.__post_init__=forbidden
for name in ('canonical_json','parse_canonical_json','encode_mapping_replay','decode_mapping_replay','canonical_protected_binding','decode_protected_binding','canonical_intent','version_to_decimal','version_from_decimal'):setattr(B,name,forbidden)
P.validate_request(raw,operation('W01').statement)
P._request_size(raw,operation('W01'))
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_full_request_charge_includes_every_context_scalar_and_uuid_integer():
    _run(
        _JOB_SETUP
        + """
from dataclasses import fields
from sys import getsizeof
request=WB._submit_raw(WM.JobSubmitRequest(job=job({'x':1})))
admission=request.context.expected[0]
identity=admission.identity
scope=identity.scope
independent=sum(getsizeof(value) for value in (request,request.parameters,request.context,request.context.expected,request.context.readiness,admission,identity,scope))
scalars=list(request.parameters)
scalars += [getattr(admission,f.name) for f in fields(admission) if f.name!='identity']
scalars += [getattr(identity,f.name) for f in fields(identity) if f.name!='scope']
scalars += [getattr(scope,f.name) for f in fields(scope)]
independent+=sum(getsizeof(value) for value in scalars)
independent+=sum(getsizeof(value.int) for value in scalars if type(value) is UUID)
assert P._request_size(request,operation('W01'))==independent
assert independent<=P._preparation_capacity(operation('W01'))
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_maximum_opaque_work_resolution_fields_fit_fixed_b_bound():
    _run(
        _JOB_SETUP
        + """
from hashlib import sha256
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
read=WB._read_job_raw(WM.JobReadRequest(work_id=str(submit.parameters[0])))
row=list(read_row(submit,True))
columns=WC.get_statement('W02').result.columns
names=[column.name for column in columns]
for name in ('result','resolution_record_result','resolution_record_evidence','resolution_record_binding'):
    row[names.index(name)]=b'x'*1048576
row[names.index('resolution_record_result_digest')]=sha256(b'x'*1048576).digest()
result=WR._decode_read_raw(read,(tuple(row),))
assert P._result_size(read,result,operation('W02'))<=P.result_capacity(operation('W02'))
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_profile_rejects_missing_carrier_structure_deliberately():
    _run(
        _JOB_SETUP
        + """
from dataclasses import replace
from modkit_events.persistence.errors import _ValidationReject
fake=type('JobReadRequest',(),{'__module__':'modkit_workers.persistence.models'})
try:replace(operation('W02'),request_type=fake)
except _ValidationReject as error:assert type(error) is _ValidationReject
else:raise AssertionError('malformed carrier accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_unselected_companion_case_skips_without_workers_path():
    environment = os.environ.copy()
    environment.pop("MODKIT_EVENTS_WORKERS_TESTS", None)
    environment.pop("PYTHONPATH", None)
    target = (
        str(Path(__file__).resolve())
        + "::test_selected_profile_freezes_exact_graph_and_pins_finite_capacity"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", target],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 skipped" in result.stdout, result.stdout + result.stderr


def test_selected_missing_companion_is_an_import_failure_not_a_skip():
    environment = os.environ.copy()
    environment["MODKIT_EVENTS_WORKERS_TESTS"] = "1"
    environment.pop("PYTHONPATH", None)
    source = str(Path(__file__).resolve().parents[1] / "src")
    script = "import sys\nSOURCE=" + repr(source) + "\nsys.path.insert(0,SOURCE)\n" + _WORKERS
    # -S gives this negative control a genuinely package-free interpreter,
    # even when the outer test environment has an installed Workers package.
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0, "missing companion was silently supplied"
    assert "ModuleNotFoundError: No module named 'modkit_workers'" in result.stderr, result.stderr


@workers_companion
def test_selected_companion_uses_normal_package_initialization():
    _run(
        _WORKERS
        + """
from modkit_workers.settings import WorkerSettings
from pathlib import Path
assert Path(modkit_workers.__file__).name == '__init__.py'
assert Path(modkit_workers.__spec__.origin).resolve() == Path(modkit_workers.__file__).resolve()
assert modkit_workers.WorkerSettings is WorkerSettings
assert modkit_workers.JobContext.__module__ == 'modkit_workers.context'
assert 'WorkerSettings' in modkit_workers.__all__
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_selected_broken_companion_is_not_bypassed(tmp_path):
    package = tmp_path / "modkit_workers"
    package.mkdir()
    (package / "__init__.py").write_text(
        "raise RuntimeError('selected Workers initialization failed')\n"
    )
    environment = os.environ.copy()
    environment["MODKIT_EVENTS_WORKERS_TESTS"] = "1"
    environment["PYTHONPATH"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", "import sys\n" + _WORKERS],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0, "broken package initialization was bypassed"
    assert "RuntimeError: selected Workers initialization failed" in result.stderr, result.stderr
