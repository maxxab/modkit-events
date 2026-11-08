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
        [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q", target],
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


@workers_companion
def test_listing_freeze_retains_exact_cursor_parameters_and_context():
    _run(
        _JOB_SETUP
        + """
from modkit_events.persistence.errors import _ValidationReject
statement=WC.get_statement('W03')
context=B._return_context_raw()
cursor_id=UUID(int=7)
parameters=(b'jobs',now,cursor_id,256)
request=P.freeze_request(statement,parameters,context=context)
assert request.parameters is parameters and request.context is context
assert request.parameters[1] is now and request.parameters[2] is cursor_id
P.validate_request(request,statement)
for parameters in ((b'other',None,None,1),(b'jobs',now,None,1),(b'jobs',None,cursor_id,1),(b'jobs',None,None,0),(b'jobs',None,None,257),(b'jobs',None,None,True)):
    try:P.freeze_request(statement,parameters,context=context)
    except _ValidationReject as error:assert type(error) is _ValidationReject
    else:raise AssertionError('invalid listing parameters accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


_LIST_SETUP = (
    _JOB_SETUP
    + """
Q=16777216
def listing():
    return P.WorkersNativeOperation(statement=WC.get_statement('W03'),request_type=WM.JobListRequest,build_request=WB._list_jobs_raw,decode_rows=WR._decode_list_raw,validate_result=WR._validate_list_result_raw,result_types=(WO.JobRecord,WO.JobDetails,WO.JobPayload))
def list_request(limit, after=None):
    return WB._list_jobs_raw(WM.JobListRequest(after=after,limit=limit))
"""
)


@workers_companion
def test_listing_request_bound_includes_both_pages_and_sentinel_transport():
    _run(
        _LIST_SETUP
        + """
from sys import getsizeof
from modkit_events.persistence.errors import _ValidationReject
op=listing()
# Independently derive schema scalar maxima and interpreter carriers. No
# production cap/upper/capacity helper contributes to the expected terms.
short_bytes={'subscription_id','namespace','command_type','scope_application','scope_tenant','scope_owner','idempotency_key','job_application','job_tenant','job_owner','protected_codec','protected_key_version'}
def cap(name,wire):
    if name.startswith('resolution_record_'):name=name[18:]
    if wire is C.WireType.TEXT:return 256 if name=='reason' else 32
    if name=='scope_evidence':return 781
    if name=='schema_version_decimal':return 4096
    if name in ('result_digest','completion_result_digest'):return 32
    return 256 if name in short_bytes else 1048576
def upper(wire,length=0):
    if wire is C.WireType.BYTEA:return getsizeof(b'')+length
    if wire is C.WireType.TEXT:return getsizeof(chr(0x10ffff))+4*length
    if wire is C.WireType.UUID:return getsizeof(UUID(int=0))+getsizeof(2**128-1)
    if wire is C.WireType.TIMESTAMPTZ:return getsizeof(now)
    if wire is C.WireType.BOOL:return getsizeof(True)
    return getsizeof(2**64-1)
def columns(values):
    return sum(max(getsizeof(None),upper(col.wire_type,cap(col.name,col.wire_type))) for col in values)
def carrier(cls):return getsizeof(object.__new__(cls))
work_cols=C.get_statement('E15').result.columns
R=sum(carrier(cls) for cls in (WO.JobRecord,WO.JobDetails,WO.JobPayload,O.WorkObservation,O.ResolutionObservation))
R+=columns(work_cols[:39])+columns(work_cols[40:])
R+=upper(C.WireType.TEXT,36)+5*upper(C.WireType.TEXT,256)+6*upper(C.WireType.BYTEA,1048576)+upper(C.WireType.TIMESTAMPTZ)
R+=getsizeof(M.MaterialState.PRESENT)+getsizeof(M.CleanupPolicy.RETAIN)
assert P.result_capacity(operation('W02'))==R
canonical=getsizeof((None,)*71)+columns(op.statement.result.columns)
widths={C.WireType.BOOL:1,C.WireType.INT4:4,C.WireType.INT8:8,C.WireType.XID8:8,C.WireType.UUID:16,C.WireType.TIMESTAMPTZ:8}
transport=getsizeof((None,)*72)+getsizeof(b'')+1
for col in op.statement.result.columns:
    width=widths.get(col.wire_type)
    if width is None:width=cap(col.name,col.wire_type)*(4 if col.wire_type is C.WireType.TEXT else 1)
    cell=getsizeof(b'')+width
    transport+=max(getsizeof(None),cell) if col.nullable else cell
capacity_points=[]
M=14*1048576
for budget in (1,16777216,33554432,2**31,3758096384):
    capacities=[]
    for n in (1,2,256):
        request=P.freeze_request(op.statement,(b"jobs",None,None,n),context=B._return_context_raw())
        containers=getsizeof((None,)*n)+getsizeof([None]*n)
        final=containers+n*(R-M)+min(n*M,budget)
        canonical_page=containers+n*(canonical-M)+min(n*M,budget)
        sentinel=getsizeof((None,)*(n+1))+(n+1)*(transport-M)+min((n+1)*M,budget)
        expected=final+canonical_page+sentinel
        assert P.result_capacity(op,request=request,max_page_payload_bytes=budget)==expected
        assert P._result_row_limit(request,op)==n
        capacities.append(expected)
        capacity_points.append(dict(n=n,Q=budget,F=final,Cpage=canonical_page,S=sentinel,B=expected))
    assert capacities[0]<capacities[1]<capacities[2]
assert P._result_row_limit(WB._read_job_raw(WM.JobReadRequest(work_id=str(UUID(int=1)))),operation('W02'))==1
try:P.result_capacity(op)
except _ValidationReject:pass
else:raise AssertionError('W03 capacity accepted no retained request')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
@pytest.mark.parametrize("count", [0, 1, 2, 256])
def test_listing_result_size_measures_full_tuple_graph_without_replacement(count):
    _run(
        _LIST_SETUP
        + f"count={count}\n"
        + """
from dataclasses import fields
from sys import getsizeof
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
op=listing();request=P.freeze_request(op.statement,(b"jobs",None,None,max(1,count)),context=B._return_context_raw())
rows=[]
for index in range(count):
    row=list(read_row(submit,index%2==1))
    ident=UUID(int=index+1)
    row[0]=ident;row[56]=ident
    if index%2==1:row[42]=ident
    rows.append(tuple(row))
value=tuple(WR._decode_read_raw(WB._read_job_raw(WM.JobReadRequest(work_id=str(row[0]))),(row,)) for row in rows)
independent=getsizeof(value)
for record in value:
    carriers=[record,record.work,record.details,record.payload]
    if record.work.resolution is not None:carriers.append(record.work.resolution)
    independent+=sum(getsizeof(carrier) for carrier in carriers)
    for carrier in carriers:
        for field in fields(carrier):
            scalar=getattr(carrier,field.name)
            if any(scalar is nested for nested in carriers):continue
            independent+=getsizeof(scalar)
            if type(scalar) is UUID:independent+=getsizeof(scalar.int)
assert P._result_size(request,value,op,max_page_payload_bytes=Q)==independent
assert independent<=P.result_capacity(op,request=request,max_page_payload_bytes=Q)
assert all(WO._validate_job_record_raw(record) is None for record in value)
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_listing_profile_rejects_nonexact_shapes_scalars_and_context_without_hooks():
    _run(
        _LIST_SETUP
        + """
from dataclasses import replace
from datetime import tzinfo
from modkit_events.persistence.errors import _ValidationReject
op=listing();context=B._return_context_raw()
def rejected(call):
    try:call()
    except _ValidationReject as error:assert type(error) is _ValidationReject
    else:raise AssertionError('invalid listing accepted')
class Integer(int):pass
class Zone(tzinfo):
    def utcoffset(self,value):raise AssertionError('custom timezone hook reached')
class Bytes(bytes):pass
bad_uuid=UUID(int=1);object.__setattr__(bad_uuid,'int',object())
for parameters in ((b'jobs',None,None,Integer(1)),(Bytes(b'jobs'),None,None,1),(b'jobs',datetime(2026,1,1,tzinfo=Zone()),UUID(int=1),1),(b'jobs',now,bad_uuid,1)):
    rejected(lambda:P.freeze_request(op.statement,parameters,context=context))
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
rejected(lambda:P.freeze_request(op.statement,(b'jobs',None,None,1),context=submit.context))
bad_context=object.__new__(B.ReturnContext)
object.__setattr__(bad_context,'expected',())
object.__setattr__(bad_context,'readiness',object())
rejected(lambda:P.freeze_request(op.statement,(b'jobs',None,None,1),context=bad_context))
rejected(lambda:replace(op,request_type=WM.JobReadRequest))
rejected(lambda:replace(op,build_request=WB._read_job_raw))
rejected(lambda:replace(op,result_types=(WO.JobRecord,WO.JobPayload,WO.JobDetails)))
rejected(lambda:replace(op,statement=WC.get_statement('W04')))
request=list_request(1)
rejected(lambda:P.result_capacity(replace(op,statement=replace(op.statement)),request=request,max_page_payload_bytes=Q))
loaded={name:module for name,module in tuple(sys.modules.items()) if name.startswith('modkit_workers')}
for name in loaded:del sys.modules[name]
assert P._result_row_limit(request,op)==1
assert P.result_capacity(op,request=request,max_page_payload_bytes=Q)>P.result_capacity(operation('W02'))
sys.modules.update(loaded)
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_listing_preparation_keeps_exact_cursor_scalars_and_independent_a_charge():
    _run(
        _LIST_SETUP
        + """
from sys import getsizeof
logical=WM.JobListRequest(after=M.WorkCursor(created_at=now,work_id=UUID(int=2**128-1)),limit=256)
cursor=logical.after
def forbidden(*args,**kwargs):raise AssertionError('public constructor or replacement reached')
WM.JobListRequest.__post_init__=forbidden
M.WorkCursor.__post_init__=forbidden
WB.replace=forbidden
request=WB._list_jobs_raw(logical)
assert request.parameters[1] is cursor.created_at and request.parameters[2] is cursor.work_id
assert request.context.expected==() and request.context.readiness is None
independent=sum(getsizeof(value) for value in (request,request.parameters,request.context,request.context.expected,request.context.readiness))
independent+=sum(getsizeof(value) for value in request.parameters)+getsizeof(cursor.work_id.int)
keys=('token','capacity','data','borrows','x','builder','profile')
metadata=dict.fromkeys(keys);old_size=getsizeof(metadata)
metadata['max_page_payload_bytes']=None
independent+=getsizeof(Q)+max(0,getsizeof(metadata)-old_size)
assert P._request_size(request,listing(),max_page_payload_bytes=Q)==independent
assert independent<=P._preparation_capacity(listing(),max_page_payload_bytes=Q)
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_listing_full_graph_preflight_precedes_semantics_and_preserves_primary():
    _run(
        _LIST_SETUP
        + """
from modkit_events.persistence.errors import _ValidationReject
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
read=WB._read_job_raw(WM.JobReadRequest(work_id=str(UUID(int=1))))
record=WR._decode_read_raw(read,(read_row(submit),))
op=listing();request=list_request(1)
def rejected(value):
    try:P._result_size(request,value,op,max_page_payload_bytes=Q)
    except _ValidationReject as error:assert type(error) is _ValidationReject
    else:raise AssertionError('invalid page graph accepted')
for value in (None,[],(record,record),(object(),)):
    rejected(value)
class HostileBytes(bytes):
    def __sizeof__(self):raise AssertionError('custom size hook reached')
object.__setattr__(record.payload,'semantic_input',HostileBytes(b'x'))
rejected((record,))
object.__setattr__(record.payload,'semantic_input',submit.context.expected[0].semantic_input)
primary=RuntimeError('unexpected graph size');cause=ValueError('cause');context=KeyError('context')
primary.__cause__=cause;primary.__context__=context;primary.__suppress_context__=False
saved=P.getsizeof
def sizing(value):
    if value is record:raise primary
    return saved(value)
P.getsizeof=sizing
try:P._result_size(request,(record,),op,max_page_payload_bytes=Q)
except RuntimeError as caught:
    assert caught is primary and caught.__cause__ is cause and caught.__context__ is context
    assert caught.__suppress_context__ is False
else:raise AssertionError('primary swallowed')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_listing_present_material_graphs_charge_every_scalar_and_resolution():
    _run(
        _LIST_SETUP
        + """
from dataclasses import fields
from sys import getsizeof
material=M.ProtectedBindingInput(material_state=M.MaterialState.PRESENT,codec='c'*256,key_version='k'*256,expires_at=now,cleanup_policy=M.CleanupPolicy.ERASE_AFTER_TERMINAL,sidecar=b's'*350000,reference=None,content_binding=b'c'*250000,recovery_metadata=B.canonical_json({'r':'r'*50000}),projection_metadata=B.canonical_json({'p':'p'*50000}))
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({'data':'x'*100000})))
records=[]
for resolved in (False,True):
    row=list(read_row(submit,resolved))
    ident=UUID(int=1+resolved);row[0]=ident;row[56]=ident
    if resolved:row[42]=ident
    row[62:]=('present',material.sidecar,None,b'c'*256,b'k'*256,now,material.recovery_metadata,'erase_after_terminal',material.projection_metadata)
    read=WB._read_job_raw(WM.JobReadRequest(work_id=str(ident)))
    records.append(WR._decode_read_raw(read,(tuple(row),)))
value=tuple(records);request=list_request(2)
independent=getsizeof(value)
for record in value:
    carriers=[record,record.work,record.details,record.payload]
    if record.work.resolution is not None:carriers.append(record.work.resolution)
    independent+=sum(getsizeof(carrier) for carrier in carriers)
    for carrier in carriers:
        for field in fields(carrier):
            scalar=getattr(carrier,field.name)
            if any(scalar is nested for nested in carriers):continue
            independent+=getsizeof(scalar)
            if type(scalar) is UUID:independent+=getsizeof(scalar.int)
assert P._result_size(request,value,listing(),max_page_payload_bytes=Q)==independent
assert independent<=P.result_capacity(listing(),request=request,max_page_payload_bytes=Q)
assert all(record.payload.sidecar is material.sidecar for record in value)
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_listing_budget_is_exact_bounded_scalar_without_common_default():
    _run(
        _LIST_SETUP
        + """
from modkit_events.persistence.errors import _ValidationReject
assert hasattr(P,'_validate_max_page_payload_bytes'), 'exact page budget helper missing'
assert P.DEFAULT_LIST_PAGE_PAYLOAD_BYTES==16777216
assert P.MAX_LIST_PAGE_PAYLOAD_BYTES==3758096384
class Integer(int):pass
op=listing();request=list_request(1)
for budget in (1,16777216,2**31,3758096384):
    assert P._validate_max_page_payload_bytes(budget) is budget
for budget in (None,True,Integer(1),0,-1,3758096385,1.0):
    for call in (lambda:P._validate_max_page_payload_bytes(budget),
                 lambda:P.result_capacity(op,request=request,max_page_payload_bytes=budget)):
        try:call()
        except _ValidationReject as error:assert type(error) is _ValidationReject
        else:raise AssertionError('invalid budget accepted')
for key in ('W01','W02'):
    try:P.result_capacity(operation(key),max_page_payload_bytes=1)
    except _ValidationReject:pass
    else:raise AssertionError('nonlisting budget accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
@pytest.mark.parametrize("resolved", [False, True])
def test_listing_typed_payload_counts_all_fourteen_occurrences_at_exact_budget(resolved):
    _run(
        _LIST_SETUP
        + f"resolved={resolved!r}\n"
        + """
from modkit_events.persistence.errors import _ValidationReject
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({'x':'payload'})))
row=read_row(submit,resolved)
record=WR._decode_read_raw(WB._read_job_raw(WM.JobReadRequest(work_id=str(UUID(int=1)))),(row,))
names=('intent_evidence','semantic_input','replay_input','protected_binding','result','resolution_record_result','resolution_record_evidence','resolution_record_binding','job_protected_binding','job_semantic_input','protected_sidecar','protected_reference','protected_recovery_metadata','projection_metadata')
columns=WC.get_statement('W03').result.columns
wire=dict(zip((column.name for column in columns),row))
exact=sum(len(wire[name]) for name in names if wire[name] is not None)
# Equal/shared protected and semantic fields must each count independently.
assert wire['protected_binding'] is wire['job_protected_binding']
assert wire['semantic_input'] is wire['job_semantic_input']
request=list_request(1);op=listing()
size=P._result_size(request,(record,),op,max_page_payload_bytes=exact)
assert size>exact
try:P._result_size(request,(record,),op,max_page_payload_bytes=exact-1)
except _ValidationReject as error:assert type(error) is _ValidationReject
else:raise AssertionError('Q+1 retained graph accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_find_freeze_retains_only_seven_parameters_and_admission():
    # Breaks if W04 is refused or accepts a mismatched projection/context.
    _run(
        _JOB_SETUP
        + """
from modkit_events.persistence.errors import _ValidationReject
from dataclasses import replace
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
statement=WC.get_statement('W04')
parameters=submit.parameters[:7]
request=P.freeze_request(statement,parameters,context=submit.context)
assert len(statement.result.columns)==72
assert request.parameters is parameters and request.context is submit.context
assert len(request.context.expected)==1 and request.context.readiness is None
assert statement.result.record is C.RecordKind.JOB_CANDIDATE
assert statement.result.cardinality is C.CardinalityKind.FIND_TWO
for args,context in ((parameters[:-1],submit.context), ((UUID(int=2),)+parameters[1:],submit.context), (parameters,B._return_context_raw())):
    try:P.freeze_request(statement,args,context=context)
    except _ValidationReject:pass
    else:raise AssertionError('invalid find projection/context accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


_FIND_SETUP = (
    _JOB_SETUP
    + """
from types import FunctionType
# Profile-only provenance controls while the consumer source is independently
# owned. These callback bodies are never used to build or decode W04.
def renamed(callback,name):
    result=FunctionType(callback.__code__,callback.__globals__,name)
    result.__module__=callback.__module__
    return result
def finding():
    return P.WorkersNativeOperation(statement=WC.get_statement('W04'),request_type=WM.JobFindRequest,build_request=renamed(WB._read_job_raw,'_find_jobs_raw'),decode_rows=renamed(WR._decode_read_raw,'_decode_find_raw'),validate_result=renamed(WR._validate_read_result_raw,'_validate_find_result_raw'),result_types=(WO.JobRecord,WO.JobDetails,WO.JobPayload,WO.JobCandidate,WO.JobIdentityObservation,WO.JobIdentityDecision))
def find_request():
    submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
    return P.freeze_request(WC.get_statement('W04'),submit.parameters[:7],context=submit.context)
"""
)


@workers_companion
def test_find_operation_pins_carriers_enum_and_fixed_capacities():
    # Breaks if six result types are treated as job carriers or enum hooks run.
    _run(
        _FIND_SETUP
        + """
from dataclasses import replace
from enum import Enum
from modkit_events.persistence.errors import _ValidationReject
op=finding();request=find_request()
assert P._result_row_limit(request,op)==2
assert P._preparation_capacity(op)==3156870
assert P._request_size(request,op)<=P._preparation_capacity(op)
assert P.result_capacity(op)==119667132
for change in (dict(request_type=WM.JobSubmitRequest), dict(result_types=op.result_types[:3]), dict(result_types=op.result_types[:5]+(M.WorkKind,)), dict(build_request=WB._submit_raw)):
    try:replace(op,**change)
    except _ValidationReject:pass
    else:raise AssertionError('invalid W04 operation accepted')
for call in (lambda:P.result_capacity(op,max_page_payload_bytes=1),lambda:P._preparation_capacity(op,max_page_payload_bytes=1)):
    try:call()
    except _ValidationReject:pass
    else:raise AssertionError('W04 accepted Q')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
@pytest.mark.parametrize("count,resolved", [(0, False), (1, False), (1, True), (2, True)])
def test_find_fixed_graph_charges_alias_occurrences_and_full_resolution(count, resolved):
    # Breaks when candidate.work is omitted because it aliases job.work.
    _run(
        _FIND_SETUP
        + f"count={count};resolved={resolved!r}\n"
        + """
from dataclasses import fields
from sys import getsizeof
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
candidates=[]
for index in range(count):
    row=list(read_row(submit,resolved));ident=UUID(int=index+1)
    row[0]=row[56]=ident
    if resolved:row[42]=ident
    record=WR._decode_read_raw(WB._read_job_raw(WM.JobReadRequest(work_id=str(ident))),(tuple(row),))
    candidate=object.__new__(WO.JobCandidate)
    object.__setattr__(candidate,'work',record.work);object.__setattr__(candidate,'job',record)
    candidates.append(candidate)
value=object.__new__(WO.JobIdentityObservation)
object.__setattr__(value,'decision',WO.JobIdentityDecision.NEW if not count else WO.JobIdentityDecision.CONFLICT)
object.__setattr__(value,'candidates',tuple(candidates));object.__setattr__(value,'original_work_id',None)
# Test-only independent occurrence walker over the exact fixture's dataclasses.
# Production must use its fixed graph, never this generic traversal.
def measure(value):
    size=getsizeof(value)
    if type(value) is tuple:return size+sum(measure(item) for item in value)
    if hasattr(type(value),'__dataclass_fields__'):return size+sum(measure(getattr(value,field.name)) for field in fields(value))
    return size+getsizeof(value.int) if type(value) is UUID else size
assert P._find_result_size(value,finding())==measure(value)
assert measure(value)<=P.result_capacity(finding())
if candidates:
    object.__setattr__(candidates[0],'job',None)
    # Structural preflight handles the optional half; consumer owns semantics.
    assert P._find_result_size(value,finding())==measure(value)
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_find_graph_rejects_hostile_scalars_before_size_hooks():
    _run(
        _FIND_SETUP
        + """
from modkit_events.persistence.errors import _ValidationReject
op=finding()
value=object.__new__(WO.JobIdentityObservation)
object.__setattr__(value,'decision',WO.JobIdentityDecision.NEW)
object.__setattr__(value,'candidates',())
object.__setattr__(value,'original_work_id',None)
class Hostile(str):
    def __sizeof__(self):raise AssertionError('hostile sizeof called')
for name,bad in (('original_work_id',Hostile('x'*36)),('decision',object()),('candidates',[]),('candidates',(object(),))):
    previous=getattr(value,name);object.__setattr__(value,name,bad)
    try:P._find_result_size(value,op)
    except _ValidationReject:pass
    else:raise AssertionError('malformed graph accepted')
    object.__setattr__(value,name,previous)
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_find_enum_provenance_rejects_hostile_metadata_without_comparison():
    _run(
        _FIND_SETUP
        + """
from modkit_events.persistence.errors import _ValidationReject
class Hostile(str):
    def __eq__(self,other):raise AssertionError('hostile enum metadata comparison')
    def __ne__(self,other):raise AssertionError('hostile enum metadata comparison')
WO.JobIdentityDecision.__module__=Hostile('modkit_workers.persistence.observations')
try:finding()
except _ValidationReject:pass
else:raise AssertionError('hostile enum metadata accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_find_work_only_inbox_and_maximum_resolution_occurrences_are_bounded():
    _run(
        _FIND_SETUP
        + """
from dataclasses import replace,fields
from sys import getsizeof
from modkit_events.persistence.errors import _ValidationReject
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
admission=submit.context.expected[0]
from modkit_events.models import Event
identity=replace(admission.identity,kind=M.WorkKind.INBOX,subscription_id='subscriber')
event=Event('event','task',{})
incoming=replace(admission,identity=identity,semantic_input=B.canonical_event(event).content,replay_input=b'{"event_id":"event","name":"task","schema_version":1,"payload":{},"metadata":{}}')
row=list(read_row(submit,True)[:56])
row[1],row[2]='inbox',b'subscriber'
row[13]=B.canonical_intent(incoming).content
row[14],row[15]=incoming.semantic_input,incoming.replay_input
# Complete successful resolution graph with maximum finite result/evidence/binding.
from hashlib import sha256
large=b'x'*1048576
names=[col.name for col in C.get_statement('E15').result.columns]
for name in ('result','resolution_record_result','resolution_record_evidence','resolution_record_binding'):
    row[names.index(name)]=large
row[names.index('resolution_record_result_digest')]=sha256(large).digest()
data=dict(zip(names,row))
resolution={name[18:]:data.pop(name) for name in names if name.startswith('resolution_record_')}
data.pop('resolution_present')
data['resolution']=O.ResolutionObservation(**resolution)
work=O.WorkObservation(**data)
candidate=object.__new__(WO.JobCandidate)
object.__setattr__(candidate,'work',work);object.__setattr__(candidate,'job',None)
value=object.__new__(WO.JobIdentityObservation)
object.__setattr__(value,'decision',WO.JobIdentityDecision.CONFLICT)
object.__setattr__(value,'candidates',(candidate,));object.__setattr__(value,'original_work_id',None)
def measure(value):
    size=getsizeof(value)
    if type(value) is tuple:return size+sum(measure(item) for item in value)
    if hasattr(type(value),'__dataclass_fields__'):return size+sum(measure(getattr(value,field.name)) for field in fields(value))
    return size+getsizeof(value.int) if type(value) is UUID else size
op=finding()
assert P._find_result_size(value,op)==measure(value)
assert measure(value)<=P.result_capacity(op)
class Hostile(bytes):
    def __sizeof__(self):raise AssertionError('work-only sizeof hook')
for bad in (Hostile(b'x'),b'x'*1048577):
    object.__setattr__(work.resolution,'evidence',bad)
    try:P._find_result_size(value,op)
    except _ValidationReject:pass
    else:raise AssertionError('hostile/oversized resolution accepted')
object.__setattr__(work.resolution,'evidence',large)
loaded={name:module for name,module in tuple(sys.modules.items()) if name.startswith('modkit_workers')}
for name in loaded:del sys.modules[name]
assert P._find_result_size(value,op)==measure(value)
sys.modules.update(loaded)
print('MANAGED_BODY_COMPLETE')
"""
    )


_INBOX_SETUP = (
    _JOB_SETUP
    + """
from dataclasses import replace,fields
from modkit_events.models import Event
from modkit_events.persistence.rows import _decode_work_observation_raw
from modkit_events.persistence.errors import _ValidationReject
submit=WB._submit_raw(WM.JobSubmitRequest(job=job({})))
original=submit.context.expected[0]
event=Event('event','task',{'value':1},metadata={'source':'test'})
inbox=replace(original,identity=replace(original.identity,kind=M.WorkKind.INBOX,subscription_id='subscriber',namespace='foreign'),semantic_input=B.canonical_event(event).content,replay_input=b'{"event_id":"event","name":"task","schema_version":1,"payload":{"value":1},"metadata":{"source":"test"}}')
def inbox_row(resolved=False):
    row=list(read_row(submit,resolved)[:56])
    row[1],row[2],row[3]='inbox',b'subscriber',b'foreign'
    row[13]=B.canonical_intent(inbox).content
    row[14],row[15]=inbox.semantic_input,inbox.replay_input
    return tuple(row)
def public_work(row):
    names=[col.name for col in C.get_statement('E15').result.columns]
    data=dict(zip(names,row))
    resolution={name[18:]:data.pop(name) for name in names if name.startswith('resolution_record_')}
    present=data.pop('resolution_present')
    data['resolution']=O.ResolutionObservation(**resolution) if present else None
    return O.WorkObservation(**data)
"""
)


@workers_companion
@pytest.mark.parametrize("resolved", [False, True])
def test_raw_inbox_full_observation_matches_public_without_decorated_helpers(resolved):
    # Breaks if either raw inbox gate remains or event validation uses public wrappers.
    _run(
        _INBOX_SETUP
        + f"resolved={resolved!r}\n"
        + """
row=inbox_row(resolved);expected=public_work(row)
def forbidden(*args,**kwargs):raise AssertionError('decorated event/model helper reached')
for name in ('validate_event_replay','canonical_event','canonical_json','canonical_intent'):
    setattr(B,name,forbidden)
for cls in (M.AdmissionInput,M.WorkIdentity,M.ScopeEvidence,O.WorkObservation,O.ResolutionObservation,Event):
    cls.__post_init__=forbidden
actual=_decode_work_observation_raw(row)
assert actual==expected
assert actual.work_id is row[0] and actual.semantic_input is row[14]
assert actual.kind=='inbox' and actual.subscription_id==b'subscriber'
before=tuple(getattr(actual,field.name) for field in fields(actual))
O._validate_work_observation_raw(actual)
assert all(getattr(actual,field.name) is value for field,value in zip(fields(actual),before))
assert M._validate_admission_input_raw(inbox) is None
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
@pytest.mark.parametrize(
    "case",
    [
        "schema",
        "name",
        "semantic",
        "metadata",
        "keys",
        "payload",
        "subscription",
        "kind",
        "intent",
        "protected",
        "lifecycle",
        "resolution",
    ],
)
def test_raw_inbox_rejects_same_full_invariants_as_public(case):
    _run(
        _INBOX_SETUP
        + f"case={case!r}\n"
        + """
from modkit_events.persistence.errors import PersistenceError
row=list(inbox_row(True));names=[col.name for col in C.get_statement('E15').result.columns]
def put(name,value):row[names.index(name)]=value
if case=='schema':
    put('schema_version_decimal',b'2');put('runnable_version',2)
elif case=='name':put('command_type',b'other')
elif case=='semantic':put('semantic_input',B.canonical_event(Event('event','task',{'value':1},metadata={'source':'different'})).content)
elif case=='metadata':put('replay_input',inbox.replay_input.replace(b'{"source":"test"}',b'[]'))
elif case=='keys':put('replay_input',inbox.replay_input[:-1]+b',"extra":1}')
elif case=='payload':put('replay_input',inbox.replay_input.replace(b'{"value":1}',b'{"value":NaN}'))
elif case=='subscription':put('subscription_id',None)
elif case=='kind':put('kind','other')
elif case=='intent':put('intent_evidence',b'wrong')
elif case=='protected':put('protected_binding',b'wrong')
elif case=='lifecycle':put('attempt_count',2)
elif case=='resolution':put('resolution_record_result_digest',b'x'*32)
try:public_work(tuple(row))
except PersistenceError as error:assert error.code is E.INVALID_OBSERVATION
else:raise AssertionError('public invalid fixture accepted: '+case)
try:_decode_work_observation_raw(tuple(row))
except _ValidationReject as error:assert type(error) is _ValidationReject
else:raise AssertionError('raw invalid inbox accepted: '+case)
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
@pytest.mark.parametrize("helper", ["_validate_event_replay_raw", "_canonical_event_raw"])
@pytest.mark.parametrize("cancellation", [False, True])
def test_raw_inbox_preserves_unexpected_event_helper_exception_identity(helper, cancellation):
    _run(
        _INBOX_SETUP
        + f"helper={helper!r};cancellation={cancellation!r}\n"
        + """
row=inbox_row()
class Cancelled(BaseException):pass
primary=Cancelled('cancelled') if cancellation else RuntimeError('unexpected event helper')
cause=ValueError('cause');context=KeyError('context')
primary.__cause__=cause;primary.__context__=context;primary.__suppress_context__=False
def broken(*args,**kwargs):raise primary
setattr(B,helper,broken)
try:_decode_work_observation_raw(row)
except BaseException as caught:
    assert caught is primary
    assert caught.__cause__ is cause and caught.__context__ is context
    assert caught.__suppress_context__ is False
else:raise AssertionError('primary event failure lost')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_raw_inbox_support_does_not_widen_job_only_preparations_or_records():
    _run(
        _INBOX_SETUP
        + """
context=B._return_context_raw(expected=(inbox,))
for key,parameters in (('W01',submit.parameters),('W04',submit.parameters[:7])):
    try:P.freeze_request(WC.get_statement(key),parameters,context=context)
    except _ValidationReject:pass
    else:raise AssertionError('inbox admitted into '+key)
row=inbox_row()+read_row(submit)[56:]
read=WB._read_job_raw(WM.JobReadRequest(work_id=str(UUID(int=1))))
listing=WB._list_jobs_raw(WM.JobListRequest(after=None,limit=1))
for call in (lambda:WR._decode_read_raw(read,(row,)),lambda:WR._decode_list_raw(listing,(row,))):
    try:call()
    except _ValidationReject:pass
    else:raise AssertionError('job-only record accepted inbox')
# Exact raw enum spelling guard must run before enum construction/user hooks.
class Hostile(str):
    def __eq__(self,other):raise AssertionError('kind equality hook')
    def __ne__(self,other):raise AssertionError('kind inequality hook')
row=list(inbox_row());row[1]=Hostile('inbox')
try:_decode_work_observation_raw(tuple(row))
except _ValidationReject:pass
else:raise AssertionError('hostile kind accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


_REAL_FIND_SETUP = (
    _INBOX_SETUP
    + """
from modkit_workers.persistence import native_store as WN
real_op=WN._FIND_JOBS
assert real_op.build_request is WB._find_jobs_raw
assert real_op.decode_rows is WR._decode_find_raw
assert real_op.validate_result is WR._validate_find_result_raw
logical=WM.JobFindRequest(job=replace(job({}),idempotency_key='key'))
keyed_submit=WB._submit_raw(WM.JobSubmitRequest(job=logical.job))
def real_family(case):
    if case=='new':return ()
    if case=='inbox':return (inbox_row(True)+(False,)+(None,)*15,)
    row=list(read_row(keyed_submit,True))
    if case=='two':row[0]=row[56]=row[42]=UUID(int=2)
    candidate=tuple(row[:56])+(True,)+tuple(row[56:])
    if case=='match':return (candidate,)
    return (inbox_row(True)+(False,)+(None,)*15,candidate)
"""
)


@workers_companion
@pytest.mark.parametrize("case", ["new", "match", "inbox", "two"])
def test_real_find_consumer_validates_full_family_and_matches_public(case):
    _run(
        _REAL_FIND_SETUP
        + f"case={case!r}\n"
        + """
request=WB._find_jobs_raw(logical);rows=real_family(case)
value=WR._decode_find_raw(request,rows)
public=WR.decode_find(WB.find_jobs(logical),rows)
assert value==public
assert value.decision.value=={'new':'new','match':'match','inbox':'conflict','two':'conflict'}[case]
assert len(value.candidates)==len(rows)
from sys import getsizeof
def measure(item):
    size=getsizeof(item)
    if type(item) is tuple:return size+sum(measure(child) for child in item)
    if hasattr(type(item),'__dataclass_fields__'):return size+sum(measure(getattr(item,field.name)) for field in fields(item))
    return size+getsizeof(item.int) if type(item) is UUID else size
assert P._result_size(request,value,real_op)==measure(value)
assert measure(value)<=P.result_capacity(real_op)
assert request.context.expected[0].identity.kind is M.WorkKind.JOB
assert len(request.parameters)==7 and len(request.context.expected)==1
if case in ('inbox','two'):
    assert value.candidates[0].work.kind=='inbox'
    assert value.candidates[0].job is None
if value.candidates:
    assert value.candidates[-1].work.resolution is not None
# Classification must be rechecked at the common retained-result boundary.
object.__setattr__(value,'decision',WO.JobIdentityDecision.MATCH if case=='new' else WO.JobIdentityDecision.NEW)
try:P._result_size(request,value,real_op)
except _ValidationReject:pass
else:raise AssertionError('forged classification accepted by common/consumer boundary')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_real_find_consumer_rejects_late_invalid_candidate_and_third_row():
    _run(
        _REAL_FIND_SETUP
        + """
request=WB._find_jobs_raw(logical);valid=real_family('two')
bad=list(valid[1]);bad[13]=b'bad-intent'
for rows in ((valid[0],tuple(bad)),valid+(valid[1],),tuple(reversed(valid))):
    try:WR._decode_find_raw(request,rows)
    except _ValidationReject as error:assert type(error) is _ValidationReject
    else:raise AssertionError('incomplete/invalid family published')
value=WR._decode_find_raw(request,valid)
object.__setattr__(value.candidates[1].work,'intent_evidence',b'bad-intent')
try:P._result_size(request,value,real_op)
except _ValidationReject:pass
else:raise AssertionError('late invalid retained graph accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_acquire_raw_fence_page_preserve_identity_and_public_parity():
    _run("""
from uuid import UUID
from modkit_events.persistence import models as M, observations as O
from modkit_events.persistence.errors import _ValidationReject
assert hasattr(M, '_fence_raw'), 'raw Fence missing'
assert hasattr(O, '_scan_page_raw'), 'raw ScanPage missing'
values=dict(work_id=UUID(int=1),token=UUID(int=2),ownership_revision=1,cycle=1,expected_attempt=1)
expected=M.Fence(**values)
page_expected=O.ScanPage(items=(expected,),visited=1,next_cursor=values['work_id'],pass_exhausted=False)
def forbidden(*a,**k): raise AssertionError('public constructor reached')
M.Fence.__post_init__=forbidden
O.ScanPage.__post_init__=forbidden
actual=M._fence_raw(**values)
items=(actual,)
page=O._scan_page_raw(items=items,visited=1,next_cursor=values['work_id'],pass_exhausted=False)
assert actual==expected and page==page_expected
assert actual.work_id is values['work_id'] and page.items is items
M._validate_fence_raw(actual)
O._validate_scan_page_raw(page)
for bad in (True,0,2**63):
    try: M._fence_raw(**dict(values,ownership_revision=bad))
    except _ValidationReject: pass
    else: raise AssertionError('bad fence')
try: O._scan_page_raw(items=items,visited=0,next_cursor=None,pass_exhausted=True)
except _ValidationReject: pass
else: raise AssertionError('bad page')
print('MANAGED_BODY_COMPLETE')
""")


_ACQUIRE_SETUP = (
    _WORKERS
    + """
from uuid import UUID
from modkit_events.persistence import native_profile as P, bindings as B, models as M, observations as O
# Fixed cooperative callbacks isolate common profile accounting from consumer
# implementation. They are not evidence for the real Workers decoder.
exec('def _acquire_raw(request): pass', WB.__dict__)
exec('def _decode_acquire_raw(request, rows): pass', WR.__dict__)
exec('def _validate_acquire_result_raw(request, value): pass', WR.__dict__)
def acquire_operation():
    return P.WorkersNativeOperation(statement=WC.get_statement('W05'),request_type=WM.JobAcquireRequest,build_request=WB._acquire_raw,decode_rows=WR._decode_acquire_raw,validate_result=WR._validate_acquire_result_raw,result_types=(WO.JobRecord,WO.JobDetails,WO.JobPayload,WO.JobClaimObservation))
def acquire_request(op,n=256,k=256):
    commands=tuple(('task%03d'%i).encode() for i in range(k))
    versions=tuple(1 for i in range(k))
    parameters=(b'jobs',commands,versions,n,0.125,UUID(int=1),4096)
    return P.freeze_request(op.statement,parameters,context=B._return_context_raw(expected=()))
"""
)


@workers_companion
def test_acquire_retains_seven_parameters_budget_and_bounded_capacity():
    _run(
        _ACQUIRE_SETUP
        + """
from sys import getsizeof
from modkit_events.persistence.errors import _ValidationReject
assert hasattr(P, '_validate_acquire_max_page_payload_bytes'), 'acquisition budget missing'
op=acquire_operation()
Q=16*1048576
for n in (1,16,256):
    request=acquire_request(op,n)
    P.validate_request(request,op.statement)
    assert len(request.parameters)==7 and not request.context.expected and request.context.readiness is None
    assert P._result_row_limit(request,op)==n
    assert P._request_size(request,op,max_page_payload_bytes=Q)<=P._preparation_capacity(op,max_page_payload_bytes=Q)
    fixed=P.result_capacity(op,request=request,max_page_payload_bytes=1)-3
    capacity=P.result_capacity(op,request=request,max_page_payload_bytes=Q)
    assert capacity==fixed+3*min(Q,n*14*1048576)
    assert capacity<80*1048576
    assert P.result_capacity(op,request=request,max_page_payload_bytes=Q+1)-capacity==(0 if n==1 else 3)
for bad in (None,True,0,-1,2**32+1,1.0):
    try: P._validate_acquire_max_page_payload_bytes(bad)
    except _ValidationReject: pass
    else: raise AssertionError('invalid Q accepted')
assert P._validate_acquire_max_page_payload_bytes(2**32)==2**32
request=acquire_request(op)
for index,bad in ((0,b'other'),(1,[b'task']),(1,()),(2,(True,)),(3,True),(4,1),(4,float('inf')),(4,0.0),(6,255)):
    values=list(request.parameters);values[index]=bad
    try: P.freeze_request(op.statement,tuple(values),context=request.context)
    except _ValidationReject: pass
    else: raise AssertionError(('invalid retained request',index))
print('MANAGED_BODY_COMPLETE')
"""
    )


_ACQUIRE_GRAPH = (
    _JOB_SETUP
    + _ACQUIRE_SETUP
    + """
from datetime import timedelta
from modkit_events.persistence.rows import _decode_work_observation_raw
from modkit_events.persistence.errors import _ValidationReject
def acquisition_graph(n):
    submit=WB._submit_raw(WM.JobSubmitRequest(job=job({'x':'payload'})))
    template=read_row(submit)
    names=[col.name for col in C.get_statement('E15').result.columns]
    items=[]
    canonical=[]
    for i in range(n):
        row=list(template)
        for name,val in (('work_id',UUID(int=i+1)),('state','claimed'),('token',UUID(int=1000+i)),('ownership_revision',1),('lease_until',now+timedelta(seconds=1))):
            row[names.index(name)]=val
        row[56]=row[0]
        work=_decode_work_observation_raw(tuple(row[:56]))
        record=WR._decode_job_half_raw(work,tuple(row[56:]))
        fence=M._fence_raw(work_id=work.work_id,token=work.token,ownership_revision=work.ownership_revision,cycle=work.cycle,expected_attempt=work.attempt_count)
        claim=WO.JobClaimObservation(record=record,fence=fence)
        items.append(claim)
        canonical.append(('item',None,None,None)+tuple(row))
    page=O._scan_page_raw(items=tuple(items),visited=n,next_cursor=UUID(int=n) if n else None,pass_exhausted=True)
    header=('header',n,page.next_cursor,True)+(None,)*71
    return page,(header,)+tuple(canonical)
"""
)


@workers_companion
@pytest.mark.parametrize("n", [0, 1, 16, 256])
def test_acquire_full_graph_all_variable_occurrences_exact_q(n):
    _run(
        _ACQUIRE_GRAPH
        + f"n={n!r}\n"
        + """
from dataclasses import fields, is_dataclass
from sys import getsizeof
op=acquire_operation();request=acquire_request(op,max(1,n))
page,rows=acquisition_graph(n)
q=sum(len(v) if type(v) is bytes else len(v.encode('utf-8')) if type(v) is str else 0 for row in rows for v in row)
def graph(value):
    if type(value) is tuple:return getsizeof(value)+sum(graph(v) for v in value)
    if is_dataclass(value):return getsizeof(value)+sum(graph(getattr(value,f.name)) for f in fields(value))
    return getsizeof(value)+(getsizeof(value.int) if type(value) is UUID else 0)
measured=graph(page)
assert P._result_size(request,page,op,max_page_payload_bytes=q)==measured
assert measured<=P.result_capacity(op,request=request,max_page_payload_bytes=q)
try:P._result_size(request,page,op,max_page_payload_bytes=q-1)
except _ValidationReject:pass
else:raise AssertionError('all-occurrence Q-1 accepted')
if n:
    claim=page.items[-1]
    bad=M._fence_raw(work_id=claim.fence.work_id,token=claim.fence.token,ownership_revision=claim.fence.ownership_revision,cycle=1,expected_attempt=claim.fence.expected_attempt+1)
    object.__setattr__(claim,'fence',bad)
    try:P._result_size(request,page,op,max_page_payload_bytes=q)
    except _ValidationReject:pass
    else:raise AssertionError('mismatched final fence accepted')
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_acquire_profile_preserves_original_baseexception_identity():
    _run(
        _ACQUIRE_SETUP
        + """
import asyncio
page=O._scan_page_raw(items=(),visited=0,next_cursor=None,pass_exhausted=True)
for primary in (RuntimeError('primary'),asyncio.CancelledError('cancel')):
    WR._primary=primary
    exec('def _validate_acquire_result_raw(request,value): raise _primary',WR.__dict__)
    op=acquire_operation();request=acquire_request(op,1)
    try:P._result_size(request,page,op,max_page_payload_bytes=6)
    except BaseException as error:assert error is primary
    else:raise AssertionError('primary lost')
print('MANAGED_BODY_COMPLETE')
"""
    )
