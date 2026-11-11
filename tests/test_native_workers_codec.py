"""Fixed W01/W02/W03 source-only binary contract; never imports a real driver."""

from test_managed_lifecycle import _run
from test_native_workers_profile import _WORKERS, workers_companion

_PROFILE = r"""
from modkit_events.persistence import native_profile as P, native_codec as N, catalog as C, models as M
from modkit_events.persistence.errors import _ValidationReject
from uuid import UUID
from dataclasses import replace
def profile(key):
    if key=='W04':
        return P.WorkersNativeOperation(statement=WC.get_statement(key),request_type=WM.JobFindRequest,build_request=WB._find_jobs_raw,decode_rows=WR._decode_find_raw,validate_result=WR._validate_find_result_raw,result_types=(WO.JobRecord,WO.JobDetails,WO.JobPayload,WO.JobCandidate,WO.JobIdentityObservation,WO.JobIdentityDecision))
    if key=='W03':
        return P.WorkersNativeOperation(statement=WC.get_statement(key),request_type=WM.JobListRequest,build_request=WB._list_jobs_raw,decode_rows=WR._decode_list_raw,validate_result=WR._validate_list_result_raw,result_types=(WO.JobRecord,WO.JobDetails,WO.JobPayload))
    submit=key=='W01'
    return P.WorkersNativeOperation(statement=WC.get_statement(key),request_type=WM.JobSubmitRequest if submit else WM.JobReadRequest,build_request=WB._submit_raw if submit else WB._read_job_raw,decode_rows=WR._decode_submit_raw if submit else WR._decode_read_raw,validate_result=WR._validate_submit_result_raw if submit else WR._validate_read_result_raw,result_types=(WO.JobAdmissionObservation,) if submit else (WO.JobRecord,WO.JobDetails,WO.JobPayload))
def rejected(fn):
    try: fn()
    except _ValidationReject as error: assert type(error) is _ValidationReject
    else: raise AssertionError('invalid input accepted')
"""
_EXPECTED_W02 = (
    ("work_id", "uuid", False, 16),
    ("kind", "text", False, 3),
    ("subscription_id", "bytea", True, 256),
    ("namespace", "bytea", False, 256),
    ("command_type", "bytea", False, 256),
    ("schema_version_decimal", "bytea", False, 4096),
    ("runnable_version", "int4", True, 4),
    ("canonical_version", "int4", False, 4),
    ("scope_evidence", "bytea", False, 781),
    ("scope_application", "bytea", False, 256),
    ("scope_tenant", "bytea", True, 256),
    ("scope_owner", "bytea", True, 256),
    ("idempotency_key", "bytea", True, 256),
    ("intent_evidence", "bytea", False, 1048576),
    ("semantic_input", "bytea", False, 1048576),
    ("replay_input", "bytea", False, 1048576),
    ("protected_binding", "bytea", False, 1048576),
    ("replay_policy", "text", False, 16),
    ("max_attempts", "int4", False, 4),
    ("deadline", "timestamptz", True, 8),
    ("original_available_at", "timestamptz", False, 8),
    ("state", "text", False, 14),
    ("cancellation_requested", "bool", False, 1),
    ("token", "uuid", True, 16),
    ("ownership_revision", "int8", False, 8),
    ("lease_until", "timestamptz", True, 8),
    ("available_at", "timestamptz", False, 8),
    ("cycle", "int4", False, 4),
    ("attempt_count", "int4", False, 4),
    ("dispatch_id", "uuid", True, 16),
    ("result", "bytea", True, 1048576),
    ("created_at", "timestamptz", False, 8),
    ("updated_at", "timestamptz", False, 8),
    ("success_origin", "text", True, 10),
    ("completion_guard_id", "uuid", True, 16),
    ("final_fence_at", "timestamptz", True, 8),
    ("completion_result_digest", "bytea", True, 32),
    ("resolution_operation_id", "uuid", True, 16),
    ("terminal_resolution_operation_id", "uuid", True, 16),
    ("resolution_present", "bool", False, 1),
    ("resolution_record_operation_id", "uuid", True, 16),
    ("resolution_record_operation_kind", "text", True, 14),
    ("resolution_record_work_id", "uuid", True, 16),
    ("resolution_record_expected_revision", "int8", True, 8),
    ("resolution_record_cycle", "int4", True, 4),
    ("resolution_record_attempt", "int4", True, 4),
    ("resolution_record_dispatch_id", "uuid", True, 16),
    ("resolution_record_outcome", "text", True, 19),
    ("resolution_record_retry_at", "timestamptz", True, 8),
    ("resolution_record_result", "bytea", True, 1048576),
    ("resolution_record_result_digest", "bytea", True, 32),
    ("resolution_record_reason", "text", True, 256),
    ("resolution_record_evidence", "bytea", True, 1048576),
    ("resolution_record_binding", "bytea", True, 1048576),
    ("resolution_record_resolution_root_xid", "xid8", True, 8),
    ("resolution_record_recorded_at", "timestamptz", True, 8),
    ("job_work_id", "uuid", False, 16),
    ("job_application", "bytea", False, 256),
    ("job_tenant", "bytea", True, 256),
    ("job_owner", "bytea", True, 256),
    ("job_protected_binding", "bytea", False, 1048576),
    ("job_semantic_input", "bytea", False, 1048576),
    ("material_state", "text", False, 7),
    ("protected_sidecar", "bytea", True, 1048576),
    ("protected_reference", "bytea", True, 1048576),
    ("protected_codec", "bytea", True, 256),
    ("protected_key_version", "bytea", True, 256),
    ("protected_expires_at", "timestamptz", True, 8),
    ("protected_recovery_metadata", "bytea", False, 1048576),
    ("protected_cleanup_policy", "text", False, 20),
    ("projection_metadata", "bytea", False, 1048576),
)


@workers_companion
def test_selected_workers_plans_have_all_casts_metadata_and_precopy_caps():
    _run(
        _WORKERS
        + _PROFILE
        + "EXPECTED="
        + repr(_EXPECTED_W02)
        + "\n"
        + """
for key in ('W01','W02'):
    op=profile(key); spec=op.statement
    plan=N._selected_sql_descriptor(spec,op)
    assert plan.canonical_columns is spec.result.columns
    assert plan.cardinality is spec.result.cardinality
    assert plan.parameter_casts==tuple('pg_catalog.'+p.wire_type.value for p in spec.parameters)
    assert plan.sentinel_limit==2 and plan.sql.endswith(b'LIMIT 2')
    assert ('modkit_workers.'+key.lower()+'(').encode() in plan.sql
    for i,cast in enumerate(plan.parameter_casts,1):
        assert ('$'+str(i)+'::'+cast).encode() in plan.sql
    rejected(lambda:N._selected_sql_descriptor(replace(spec),op))
    rejected(lambda:N._selected_sql_descriptor(spec))
    rejected(lambda:N._selected_sql_descriptor(spec,profile('W02' if key=='W01' else 'W01')))
    assert len(plan.transport_columns)==(3 if key=='W01' else 72)
    assert plan.max_admitted_cell_payload_bytes==(18 if key=='W01' else 14688732)
op=profile('W02'); plan=N._selected_sql_descriptor(op.statement,op)
for col,(name,kind,nullable,cap) in zip(plan.transport_columns[1:],EXPECTED):
    assert (col.name,col.wire_type.value,col.nullable,col.max_payload_bytes)==(name,'bytea' if kind=='text' else kind,nullable,cap)
    assert col.oid=={'bytea':17,'text':17,'uuid':2950,'bool':16,'int4':23,'int8':20,'timestamptz':1184,'xid8':5069}[kind]
    if kind in ('text','bytea'):
        expr='s.'+name if kind=='bytea' else "pg_catalog.convert_to(s."+name+", 'UTF8')"
        check='(s.'+name+(' IS NULL OR ' if nullable else ' IS NOT NULL AND ')+'pg_catalog.octet_length('+expr+') OPERATOR(pg_catalog.<=) '+str(cap)+')'
        assert check.encode() in plan.sql
        expr='c.'+name if kind=='bytea' else "pg_catalog.convert_to(c."+name+", 'UTF8')"
        assert ('CASE WHEN c.cap_ok THEN '+expr+' ELSE NULL::pg_catalog.bytea END AS '+name).encode() in plan.sql
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_binary_boolean_accepts_only_zero_or_one_and_exact_uuid():
    _run(
        _WORKERS
        + _PROFILE
        + r"""
op=profile('W01');spec=op.statement
for wire,want in ((b'\x00',False),(b'\x01',True)):
    actual=N._decode_binary_transport_row(spec,(b'\x01',UUID(int=1).bytes,wire),op)
    assert actual==(UUID(int=1),want) and type(actual[1]) is bool
for bad in (b'',b'\x02',b'\xff',b'\x01\x00',True,None,bytearray(b'\x01')):
    rejected(lambda:N._decode_binary_transport_row(spec,(b'\x01',UUID(int=1).bytes,bad),op))
for bad in (bytes(15),bytes(17),None):
    rejected(lambda:N._decode_binary_transport_row(spec,(b'\x01',bad,b'\x01'),op))
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_all_w02_variable_boundaries_fixed_widths_and_full_row_preflight():
    _run(
        _WORKERS
        + _PROFILE
        + r"""
op=profile('W02'); spec=op.statement;plan=N._selected_sql_descriptor(spec,op)
row=[b'\x01']
for col in plan.transport_columns[1:]:
    row.append(None if col.nullable else (b'x' if col.wire_type is C.WireType.BYTEA else (1).to_bytes(col.max_payload_bytes,'big')))
for index,col in enumerate(plan.transport_columns[1:],1):
    current=list(row)
    if col.wire_type is C.WireType.BYTEA:
        current[index]=b'x'*col.max_payload_bytes
        assert N._decode_binary_transport_row(spec,tuple(current),op)[index-1] == (current[index].decode() if spec.result.columns[index-1].wire_type is C.WireType.TEXT else current[index])
        current[index]+=b'x'
        rejected(lambda:N._decode_binary_transport_row(spec,tuple(current),op))
    else:
        for delta in (-1,1):
            current[index]=bytes(col.max_payload_bytes+delta)
            rejected(lambda:N._decode_binary_transport_row(spec,tuple(current),op))
    if not col.nullable:
        current[index]=None
        rejected(lambda:N._decode_binary_transport_row(spec,tuple(current),op))
# Bad final suffix must stop all typed conversion, even valid leading UUID.
def forbidden(*args,**kwargs): raise AssertionError('converted before full row preflight')
N.UUID=forbidden
row[-1]=b'x'*1048577
rejected(lambda:N._decode_binary_transport_row(spec,tuple(row),op))
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_retained_request_keyword_preserves_w02_descriptor_and_decode():
    """Breaks if the issuer cannot forward its retained request through both leaves."""
    _run(
        _WORKERS
        + _PROFILE
        + r"""
op=profile('W02');request=op.build_request(WM.JobReadRequest(work_id=str(UUID(int=1))))
assert N._selected_sql_descriptor(op.statement,op,request=request)==N._selected_sql_descriptor(op.statement,op)
row=[b'\x01']
for col in N._selected_sql_descriptor(op.statement,op).transport_columns[1:]:
    row.append(None if col.nullable else (b'x' if col.wire_type is C.WireType.BYTEA else (1).to_bytes(col.max_payload_bytes,'big')))
assert N._decode_binary_transport_row(op.statement,tuple(row),op,request=request)==N._decode_binary_transport_row(op.statement,tuple(row),op)
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_w03_fixed_five_parameter_plan_binds_sentinel_to_validated_request():
    """Breaks on limit rewriting, unordered SQL, missing request or lost job caps."""
    _run(
        _WORKERS
        + _PROFILE
        + r"""
from datetime import datetime, timezone
op=profile('W03');spec=op.statement
point=profile('W02');point_plan=N._selected_sql_descriptor(point.statement,point)
instant=datetime(2026,1,1,tzinfo=timezone.utc);identity=UUID(int=7)
after=M.WorkCursor(created_at=instant,work_id=identity)
for limit in (1,2,256):
    request=op.build_request(WM.JobListRequest(after=after,limit=limit))
    parameters=request.parameters
    plan=N._selected_sql_descriptor(spec,op,request=request,max_page_payload_bytes=16777216)
    assert plan.parameter_casts==('pg_catalog.bytea','pg_catalog.timestamptz','pg_catalog.uuid','pg_catalog.int4','pg_catalog.int8')
    assert plan.cardinality is C.CardinalityKind.LIMIT and plan.sentinel_limit==limit+1
    assert plan.canonical_columns is spec.result.columns
    assert plan.transport_columns is point_plan.transport_columns
    assert plan.max_admitted_cell_payload_bytes==14688732
    assert b'FROM modkit_workers.w03($1::pg_catalog.bytea, $2::pg_catalog.timestamptz, $3::pg_catalog.uuid, $4::pg_catalog.int4, $5::pg_catalog.int8) AS s' in plan.sql
    assert plan.sql.endswith(b'ORDER BY c.created_at, c.work_id\nLIMIT ($4::pg_catalog.int4 + 1)')
    assert b'w02(' not in plan.sql and b'w03($1' in plan.sql
    assert parameters is request.parameters and parameters==(b'jobs',instant,identity,limit)
    assert parameters[1] is instant and parameters[2] is identity
    assert plan.sql.split(b'\nSELECT c.cap_ok,',1)[1].split(b'\nORDER BY',1)[0]==point_plan.sql.split(b'\nSELECT c.cap_ok,',1)[1].rsplit(b'\nLIMIT',1)[0]
rejected(lambda:N._selected_sql_descriptor(spec,op))
rejected(lambda:N._selected_sql_descriptor(spec,op,request=object(),max_page_payload_bytes=16777216))
rejected(lambda:N._selected_sql_descriptor(spec,op,request=point.build_request(WM.JobReadRequest(work_id=str(identity))),max_page_payload_bytes=16777216))
request=op.build_request(WM.JobListRequest(after=None,limit=1))
object.__setattr__(request,'parameters',(b'jobs',None,None,0))
rejected(lambda:N._selected_sql_descriptor(spec,op,request=request,max_page_payload_bytes=16777216))
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_w03_binary_row_requires_request_and_retains_complete_w02_wire_contract():
    """Breaks if listing bypasses request validation or diverges from protected decoding."""
    _run(
        _WORKERS
        + _PROFILE
        + r"""
op=profile('W03');point=profile('W02')
request=op.build_request(WM.JobListRequest(after=None,limit=2))
plan=N._selected_sql_descriptor(op.statement,op,request=request,max_page_payload_bytes=16777216)
row=[b'\x01']
for col in plan.transport_columns[1:]:
    row.append(None if col.nullable else (b'x' if col.wire_type is C.WireType.BYTEA else (1).to_bytes(col.max_payload_bytes,'big')))
wire=tuple(row)
expected=N._decode_binary_transport_row(point.statement,wire,point)
assert N._decode_binary_transport_row(op.statement,wire,op,request=request,max_page_payload_bytes=16777216)==expected
rejected(lambda:N._decode_binary_transport_row(op.statement,wire,op))
rejected(lambda:N._decode_binary_transport_row(op.statement,wire,op,request=object(),max_page_payload_bytes=16777216))
row[-1]=b'x'*1048577
def forbidden(*args,**kwargs):raise AssertionError('typed conversion before suffix preflight')
N.UUID=forbidden
rejected(lambda:N._decode_binary_transport_row(op.statement,tuple(row),op,request=request,max_page_payload_bytes=16777216))
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_w03_sql_bounds_source_before_whole_page_fourteen_field_aggregate():
    """Breaks on unbounded four-arg source, prefix budgeting, or omitted occurrences."""
    _run(r"""
import re
from modkit_events.persistence import native_codec as N
sql=N._W03_SQL
source,checked=sql.split(b'), checked AS (',1)
assert b'FROM modkit_workers.w03($1::pg_catalog.bytea, $2::pg_catalog.timestamptz, $3::pg_catalog.uuid, $4::pg_catalog.int4, $5::pg_catalog.int8) AS s' in source
assert source.endswith(b'LIMIT ($4::pg_catalog.int4 + 1)\n')
assert sql.count(b'LIMIT ($4::pg_catalog.int4 + 1)')==2
guard,projection=checked.split(b'\nSELECT c.cap_ok,',1)
assert b'pg_catalog.sum(' in guard
assert b') OVER () OPERATOR(pg_catalog.<=) $5::pg_catalog.int8::pg_catalog.numeric' in guard
expected=('intent_evidence','semantic_input','replay_input','protected_binding','result','resolution_record_result','resolution_record_evidence','resolution_record_binding','job_protected_binding','job_semantic_input','protected_sidecar','protected_reference','protected_recovery_metadata','projection_metadata')
operands=tuple(name.decode() for name in re.findall(rb'COALESCE\(pg_catalog.octet_length\(s\.([a-z_]+)\)::pg_catalog.int8, 0::pg_catalog.int8\)',guard))
assert operands==expected
assert b' IS TRUE AS cap_ok' in guard and b'FROM source AS s' in guard
assert b'page_budget_ok' not in sql and b'pg_catalog.numeric' not in projection
assert projection.split(b'\nORDER BY',1)[0]==N._W02_SQL.split(b'\nSELECT c.cap_ok,',1)[1].rsplit(b'\nLIMIT',1)[0]
assert sql.endswith(b'ORDER BY c.created_at, c.work_id\nLIMIT ($4::pg_catalog.int4 + 1)')
print('MANAGED_BODY_COMPLETE')
""")


@workers_companion
def test_w03_descriptor_rejects_invalid_budget_and_keeps_sql_fixed_above_int4():
    """Breaks if Q is defaulted/coerced, narrowed, or accepted on another profile."""
    _run(
        _WORKERS
        + _PROFILE
        + r"""
op=profile('W03');request=op.build_request(WM.JobListRequest(after=None,limit=256))
class Integer(int):pass
for bad in (None,True,False,Integer(1),0,-1,3758096385,1.0,'1'):
    rejected(lambda:N._selected_sql_descriptor(op.statement,op,request=request,max_page_payload_bytes=bad))
for budget in (1,16777216,2**31,3758096384):
    plan=N._selected_sql_descriptor(op.statement,op,request=request,max_page_payload_bytes=budget)
    assert plan.sql is N._W03_SQL and plan.sentinel_limit==257
    assert plan.parameter_casts[-1]=='pg_catalog.int8' and len(plan.transport_columns)==72
point=profile('W02')
rejected(lambda:N._selected_sql_descriptor(point.statement,point,max_page_payload_bytes=1))
rejected(lambda:N._selected_sql_descriptor(C.get_statement('E14'),max_page_payload_bytes=1))
print('MANAGED_BODY_COMPLETE')
"""
    )


# Literal W04 ABI: independent of SQL generation and descriptors.
_EXPECTED_W04 = (
    _EXPECTED_W02[0],
    ("kind", "text", False, 5),
    *_EXPECTED_W02[2:56],
    ("job_half_present", "bool", False, 1),
    *((name, kind, True, cap) for name, kind, nullable, cap in _EXPECTED_W02[56:]),
)


def test_w04_fixed_sql_and_transport_literal_contract():
    """Breaks on W02 job-only guards, a shifted flag, or uncapped output."""
    _run(
        "EXPECTED="
        + repr(_EXPECTED_W04)
        + "\n"
        + r"""
import re
from modkit_events.persistence import native_codec as N
assert hasattr(N, '_W04_SQL'), 'fixed W04 SQL missing'
assert hasattr(N, '_W04_COLUMNS'), 'fixed W04 columns missing'
sql=N._W04_SQL
assert len(EXPECTED)==72 and len(N._W04_COLUMNS)==73
assert sql.startswith(b'WITH source AS MATERIALIZED (')
assert b'FROM modkit_workers.w04($1::pg_catalog.uuid, $2::pg_catalog.text, $3::pg_catalog.bytea, $4::pg_catalog.bytea, $5::pg_catalog.bytea, $6::pg_catalog.bytea, $7::pg_catalog.bytea) AS s' in sql
assert sql.endswith(b'ORDER BY c.work_id\nLIMIT 3')
assert b'$8' not in sql and b'w02(' not in sql and b'pg_catalog.sum' not in sql
assert b's.job_half_present' in sql and b'c.job_half_present,\n       c.job_work_id' in sql
oids={'uuid':2950,'text':17,'bytea':17,'bool':16,'int4':23,'int8':20,'xid8':5069,'timestamptz':1184}
for col,(name,kind,nullable,cap) in zip(N._W04_COLUMNS[1:],EXPECTED):
    assert (col.name,col.wire_type.value,col.oid,col.nullable,col.max_payload_bytes)==(name,'bytea' if kind=='text' else kind,oids[kind],nullable,cap)
    if kind in ('text','bytea'):
        expr='s.'+name if kind=='bytea' else "pg_catalog.convert_to(s."+name+", 'UTF8')"
        check='(s.'+name+(' IS NULL OR ' if nullable else ' IS NOT NULL AND ')+'pg_catalog.octet_length('+expr+') OPERATOR(pg_catalog.<=) '+str(cap)+')'
        assert check.encode() in sql, name
        expr='c.'+name if kind=='bytea' else "pg_catalog.convert_to(c."+name+", 'UTF8')"
        assert ('CASE WHEN c.cap_ok THEN '+expr+' ELSE NULL::pg_catalog.bytea END AS '+name).encode() in sql, name
assert sum(c.max_payload_bytes for c in N._W04_COLUMNS)==14688734
print('MANAGED_BODY_COMPLETE')
"""
    )


@workers_companion
def test_w04_descriptor_and_binary_preflight_with_real_consumer_request():
    """Real consumer request feeds the fixed descriptor and complete binary preflight."""
    from test_native_workers_profile import _JOB_SETUP

    _run(
        _JOB_SETUP
        + _PROFILE
        + r"""
from modkit_events.persistence import native_codec as N
from modkit_events.persistence.errors import _ValidationReject
def reject(fn):
    try:fn()
    except _ValidationReject:pass
    else:raise AssertionError('invalid wire accepted')
op=profile('W04');request=op.build_request(WM.JobFindRequest(job=job({})));spec=op.statement
plan=N._selected_sql_descriptor(spec,op,request=request)
assert plan.sql is N._W04_SQL and plan.transport_columns is N._W04_COLUMNS
assert plan.canonical_columns is spec.result.columns
assert plan.parameter_casts==('pg_catalog.uuid','pg_catalog.text')+('pg_catalog.bytea',)*5
assert plan.cardinality is C.CardinalityKind.FIND_TWO and plan.sentinel_limit==3
assert plan.max_admitted_cell_payload_bytes==14688735
reject(lambda:N._selected_sql_descriptor(spec,op,max_page_payload_bytes=1))
row=[b'\x01']
for col in plan.transport_columns[1:]:
    row.append(None if col.nullable else (b'x' if col.wire_type is C.WireType.BYTEA else (1).to_bytes(col.max_payload_bytes,'big')))
row[2]=b'inbox';row[57]=b'\x00'
decoded=N._decode_binary_transport_row(spec,tuple(row),op,request=request)
assert len(decoded)==72 and decoded[1]=='inbox' and decoded[56] is False
assert decoded[57:]==(None,)*15
for i,col in enumerate(plan.transport_columns[1:],1):
    changed=list(row)
    if col.wire_type is C.WireType.BYTEA:
        changed[i]=b'x'*col.max_payload_bytes
        N._decode_binary_transport_row(spec,tuple(changed),op,request=request)
        changed[i]+=b'x'
        reject(lambda:N._decode_binary_transport_row(spec,tuple(changed),op,request=request))
    else:
        for size in (col.max_payload_bytes-1,col.max_payload_bytes+1):
            changed[i]=bytes(size)
            reject(lambda:N._decode_binary_transport_row(spec,tuple(changed),op,request=request))
for value in (None,b'',b'\x02',b'\xff'):
    changed=list(row);changed[57]=value
    reject(lambda:N._decode_binary_transport_row(spec,tuple(changed),op,request=request))
changed=list(row);changed[2]=b'\xff'
reject(lambda:N._decode_binary_transport_row(spec,tuple(changed),op,request=request))
def forbidden(*a,**k):raise AssertionError('conversion before suffix preflight')
N.UUID=forbidden
changed=list(row);changed[-1]=b'x'*1048577
reject(lambda:N._decode_binary_transport_row(spec,tuple(changed),op,request=request))
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_w05_transport_exists():
    _run(
        "from modkit_events.persistence import native_codec as N; assert hasattr(N, '_W05_SQL'), 'W05 transport missing'; print('MANAGED_BODY_COMPLETE')"
    )


# These isolate the transport from the separately owned consumer/profile validation.
_W05_TRANSPORT = r"""
from types import SimpleNamespace
from modkit_events.persistence import native_codec as N, native_profile as P, catalog as C
from modkit_events.persistence.errors import _ValidationReject
from uuid import UUID
header=(
    C.ColumnSpec(name='record_type',wire_type=C.WireType.TEXT,nullable=False),
    C.ColumnSpec(name='visited',wire_type=C.WireType.INT4,nullable=True),
    C.ColumnSpec(name='next_cursor',wire_type=C.WireType.UUID,nullable=True),
    C.ColumnSpec(name='pass_exhausted',wire_type=C.WireType.BOOL,nullable=True),
)
text_names={'kind','replay_policy','state','success_origin','resolution_record_operation_kind','resolution_record_outcome','resolution_record_reason','material_state','protected_cleanup_policy'}
cols=header+tuple(C.ColumnSpec(name=c.name,wire_type=C.WireType.TEXT if c.name in text_names else c.wire_type,nullable=True) for c in N._W02_COLUMNS[1:])
spec=SimpleNamespace(key='W05',result=SimpleNamespace(columns=cols))
seen=[]
op=SimpleNamespace(statement=spec,decode_rows=lambda request,rows: seen.append(rows) or rows)
request=SimpleNamespace(statement=spec,parameters=(b'jobs',(b'a',b'b'),(1,2147483647),256,0.0000005,None,4096))
P._validate_operation=lambda operation: None
P._result_row_limit=lambda request,operation: request.parameters[3]
P.decode_columns=lambda statement,values: values
def descriptor(q=16777216):
    return N._selected_sql_descriptor(spec,op,request=request,max_page_payload_bytes=q)
def header_row():
    return (b'\x01',b'header',(0).to_bytes(4,'big'),None,b'\x01')+(None,)*71
def rejected(fn):
    try: fn()
    except _ValidationReject as error: assert type(error) is _ValidationReject
    else: raise AssertionError('invalid transport accepted')
"""


def test_w05_exact_nullable_frame_metadata_and_eight_casts():
    _run(
        _W05_TRANSPORT
        + """
d=descriptor()
assert len(d.canonical_columns)==75 and len(d.transport_columns)==76
assert d.sentinel_limit==258 and d.cardinality is C.CardinalityKind.SCAN
assert d.parameter_casts==('pg_catalog.bytea','pg_catalog.bytea[]','pg_catalog.int4[]','pg_catalog.int4','pg_catalog.float8','pg_catalog.uuid','pg_catalog.int4','pg_catalog.int8')
assert tuple(c.name for c in d.transport_columns[1:])==tuple(c.name for c in cols)
assert all(c.nullable for c in d.transport_columns[2:])
assert [c.oid for c in d.transport_columns[:6]]==[16,17,23,2950,16,2950]
assert N._decode_binary_transport_row(spec,header_row(),op,request=request,max_page_payload_bytes=6)==('header',0,None,True)+(None,)*71
for q in (None,True,0,2**32+1):
    rejected(lambda: descriptor(q))
assert descriptor(2**32).sentinel_limit==258
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_w05_sql_preserves_source_ordinal_and_charges_every_variable_occurrence():
    _run(
        _W05_TRANSPORT
        + """
sql=descriptor().sql.decode()
assert 'WITH ORDINALITY' in sql and 'source_ordinal' in sql
assert 'LIMIT ($4::pg_catalog.int4 + 2)' in sql
assert sql.count('LIMIT ')==1, 'final LIMIT must not hide source overflow'
assert 'ORDER BY c.record_type' in sql
assert 'lag(s.work_id)' in sql
assert 's.source_ordinal OPERATOR(pg_catalog.=) 1' in sql
assert 'pg_catalog.bool_and' in sql and 'OVER ()' in sql
for col in cols:
    if col.wire_type in (C.WireType.BYTEA,C.WireType.TEXT):
        expression='s.'+col.name if col.wire_type is C.WireType.BYTEA else "pg_catalog.convert_to(s."+col.name+", 'UTF8')"
        assert 'COALESCE(pg_catalog.octet_length('+expression+')::pg_catalog.int8, 0::pg_catalog.int8)' in sql,col.name
assert '$8::pg_catalog.int8::pg_catalog.numeric' in sql
print('MANAGED_BODY_COMPLETE')
"""
    )


def test_w05_exact_all_75_positions_match_independent_contract():
    # _EXPECTED_W02 is the independently enumerated Work56 + Job15 ABI above.
    expected = (
        ("record_type", "text", False, 6),
        ("visited", "int4", True, 4),
        ("next_cursor", "uuid", True, 16),
        ("pass_exhausted", "bool", True, 1),
    ) + tuple((name, wire, True, cap) for name, wire, nullable, cap in _EXPECTED_W02)
    _run(
        _W05_TRANSPORT
        + "expected="
        + repr(expected)
        + "\n"
        + """
d=descriptor()
oids={'bytea':17,'text':17,'int4':23,'int8':20,'xid8':5069,'uuid':2950,'timestamptz':1184,'bool':16}
assert len(expected)==75
for canonical,transport,(name,wire,nullable,cap) in zip(d.canonical_columns,d.transport_columns[1:],expected):
    assert (canonical.name,canonical.wire_type.value,canonical.nullable)==(name,wire,nullable)
    assert (transport.name,transport.oid,transport.nullable,transport.max_payload_bytes)==(name,oids[wire],nullable,cap)
print('MANAGED_BODY_COMPLETE')
"""
    )
