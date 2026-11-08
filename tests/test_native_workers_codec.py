"""Fixed W01/W02 source-only binary contract; never imports a real driver."""

from test_managed_lifecycle import _run
from test_native_workers_profile import _WORKERS, workers_companion

_PROFILE = r"""
from modkit_events.persistence import native_profile as P, native_codec as N, catalog as C
from modkit_events.persistence.errors import _ValidationReject
from uuid import UUID
from dataclasses import replace
def profile(key):
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
