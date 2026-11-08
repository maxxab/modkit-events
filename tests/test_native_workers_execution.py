"""Selected issuer source controls using only the synthetic RawCursor harness."""

import textwrap

import pytest
from test_managed_lifecycle import _run
from test_managed_statement_lifecycle import _SETUP
from test_native_execution import _DRIVER
from test_native_workers_codec import _PROFILE
from test_native_workers_profile import _WORKERS, workers_companion

_WORKER_SETUP = r"""
from modkit_events.persistence import models as M, scope as S
_base_limits=limits
def limits(**overrides):
    values=dict(prepare_bytes=100000000,prepare_bytes_per_execution=50000000,result_bytes=100000000,result_bytes_per_ticket=50000000)
    values.update(overrides)
    return _base_limits(**values)
def setup_workers(key='W02',values=()):
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);actual=n.ManagedConnection(PG())
    c=n.attach_native(actual,x,execution_ledger=L)
    with m._construction(False):
        root,code=m._reserve_root(c,L);assert code is None
        actual.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(root,L,known=True)
    op=profile(key)
    if key=='W02':logical=WM.JobReadRequest(work_id=str(UUID(int=1)))
    else:
        material=M.ProtectedBindingInput(material_state=M.MaterialState.ABSENT,codec=None,key_version=None,expires_at=None,cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=None,reference=None,content_binding=b'',recovery_metadata=b'',projection_metadata={})
        logical=WM.JobSubmitRequest(job=WM.JobInput(str(UUID(int=1)),'task',1,S.Scope('app'),{},original_available_at=datetime(2026,1,1,tzinfo=timezone.utc),protected=material))
    a=native.prepare_component(x,op,logical,execution_ledger=L)
    req=m._preparations[a._stamp]['data']
    t=m.admit(root,a,execution_ledger=L)
    b=m.reserve_result(t,P.result_capacity(op),execution_ledger=L)
    result=Result('E14',list(values))
    result.descriptor=N._selected_sql_descriptor(op.statement,op)
    result.nfields=len(result.descriptor.transport_columns)
    Cursor.result=result
    return L,x,actual,c,root,a,t,b,op,req
"""


_ROW_HELPER = r"""

def full_row(op):
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    material=M.ProtectedBindingInput(material_state=M.MaterialState.ABSENT,codec=None,key_version=None,expires_at=None,cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=None,reference=None,content_binding=b'',recovery_metadata=b'',projection_metadata={})
    logical=WM.JobSubmitRequest(job=WM.JobInput(str(UUID(int=1)),'task',1,S.Scope('app'),{},original_available_at=now,protected=material))
    submit=WB._submit_raw(logical)
    data=dict((p.name,value) for p,value in zip(submit.statement.parameters,submit.parameters))
    data.update(runnable_version=1,state='queued',cancellation_requested=False,token=None,ownership_revision=0,lease_until=None,available_at=now,cycle=1,attempt_count=0,dispatch_id=None,result=None,created_at=now,updated_at=now,success_origin=None,completion_guard_id=None,final_fence_at=None,completion_result_digest=None,resolution_operation_id=None,terminal_resolution_operation_id=None,resolution_present=False,job_work_id=UUID(int=1),job_application=b'app',job_tenant=None,job_owner=None,job_protected_binding=data['protected_binding'],job_semantic_input=data['semantic_input'])
    values=[]
    epoch=datetime(2000,1,1,tzinfo=timezone.utc)
    for col in op.statement.result.columns:
        value=data.get(col.name)
        if value is None: values.append(None)
        elif col.wire_type is C.WireType.BYTEA: values.append(value)
        elif col.wire_type is C.WireType.TEXT: values.append(value.encode())
        elif col.wire_type is C.WireType.UUID: values.append(value.bytes)
        elif col.wire_type is C.WireType.BOOL: values.append(bytes([value]))
        elif col.wire_type in (C.WireType.INT4,C.WireType.INT8,C.WireType.XID8):
            values.append(value.to_bytes(4 if col.wire_type is C.WireType.INT4 else 8,'big',signed=col.wire_type is not C.WireType.XID8))
        else:
            delta=value-epoch
            micros=delta.days*86400000000+delta.seconds*1000000+delta.microseconds
            values.append(micros.to_bytes(8,'big',signed=True))
    return (b'\x01',)+tuple(values)

def assert_held(t,L,b):
    ticket=m._ticket(t,L)
    assert ticket.operation['state']=='HELD'
    assert ticket.roots[t._subject]['state']=='UNKNOWN' and L.uncertainty.present
    expect(E.RESOURCE_BUSY,lambda:m.read_result(b,execution_ledger=L),True)
    expect(E.RESOURCE_BUSY,lambda:m.release_result(b,execution_ledger=L),True)
"""


def run(body):
    _run(
        _SETUP + _DRIVER + _WORKERS + _PROFILE + _WORKER_SETUP + _ROW_HELPER + textwrap.dedent(body)
    )


def test_prepare_component_front_door_delegates_without_second_paid_frame():
    _run(
        _SETUP
        + _DRIVER
        + textwrap.dedent("""
    seen=[];token=object();execution=object();operation=object();logical=object();ledger=object()
    def backend(*args,**kwargs):
        seen.append((args,kwargs));return token
    m._prepare_component=backend
    assert native.prepare_component(execution,operation,logical,execution_ledger=ledger) is token
    assert seen==[((execution,operation,logical),{'execution_ledger':ledger})]
    print('MANAGED_BODY_COMPLETE')
    """)
    )


@pytest.mark.parametrize("key", ["W01", "W02"])
@workers_companion
def test_owned_profile_decodes_exact_request_before_typed_publication_and_overrides_adapters(key):
    run(
        "KEY="
        + repr(key)
        + "\n"
        + textwrap.dedent(r"""
    values=[(b'\x01',UUID(int=1).bytes,b'\x01')] if KEY=='W01' else []
    L,x,actual,c,r,a,t,b,op,req=setup_workers(KEY,values)
    sentinel=object()
    for kind in (bytes,UUID,str,int,datetime): actual.adapters.dumpers[kind]=sentinel
    for col in Cursor.result.descriptor.transport_columns: actual.adapters.loaders[col.oid]=sentinel
    def inspect(cursor):
        assert cursor.adapters.dumpers=={bytes:BytesBinaryDumper,UUID:UUIDBinaryDumper,str:StrBinaryDumper,int:Int4BinaryDumper,datetime:DatetimeBinaryDumper}
        assert all(cursor.adapters.loaders[col.oid] is ByteaBinaryLoader for col in Cursor.result.descriptor.transport_columns)
    Cursor.effect=inspect
    native.execute(t,b,execution_ledger=L)
    result=m.read_result(b,execution_ledger=L)
    if KEY=='W01': assert type(result) is WO.JobAdmissionObservation and result.inserted is True
    else: assert result is None
    assert Cursor.instances[-1].calls[0][1] is req.parameters
    assert Cursor.instances[-1].closed
    assert all(value is sentinel for value in actual.adapters.dumpers.values())
    assert all(value is sentinel for value in actual.adapters.loaders.values())
    assert not L.uncertainty.present and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)
    )


@workers_companion
def test_complete_w02_final_typed_graph_is_published_only_after_close():
    run(r"""
    L,x,actual,c,r,a,t,b,op,req=setup_workers()
    Cursor.result.values=[full_row(op)];Cursor.result.ntuples=1
    Cursor.result.command_status=b'SELECT 1';Cursor.result.command_tuples=1
    setter=m.set_result;seen=[]
    def inspect(handle,value,**kwargs):
        assert Cursor.instances[-1].closed
        assert type(value) is WO.JobRecord and type(value.details) is WO.JobDetails and type(value.payload) is WO.JobPayload
        assert value.work.work_id==req.parameters[0] and value.details.work_id==str(req.parameters[0])
        seen.append(value);return setter(handle,value,**kwargs)
    m.set_result=inspect
    native.execute(t,b,execution_ledger=L)
    assert m.read_result(b,execution_ledger=L) is seen[0]
    assert len(Cursor.result.copies)==72
    assert not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize(
    "fault",
    [
        "cap",
        "count2",
        "last_name",
        "last_oid",
        "last_format",
        "last_size",
        "extra",
        "suffix",
        "close",
        "publish",
    ],
)
@workers_companion
def test_owned_w02_errors_are_held_before_result_reuse(fault):
    run(
        "FAULT="
        + repr(fault)
        + "\n"
        + textwrap.dedent(r"""
    L,x,actual,c,r,a,t,b,op,req=setup_workers()
    row=full_row(op)
    Cursor.result.values=[row];Cursor.result.ntuples=1
    Cursor.result.command_status=b'SELECT 1';Cursor.result.command_tuples=1
    primary=RuntimeError('actual received');cause=ValueError('cause');context=LookupError('context')
    primary.__cause__=cause;primary.__context__=context;primary.__suppress_context__=True
    def fail(*args,**kwargs):raise primary
    if FAULT=='cap':Cursor.result.values=[(b'\x00',)+row[1:]]
    elif FAULT=='count2':
        Cursor.result.values=[row,row];Cursor.result.ntuples=2;Cursor.result.command_status=b'SELECT 2';Cursor.result.command_tuples=2
    elif FAULT.startswith('last_'):
        method={'last_name':'fname','last_oid':'ftype','last_format':'fformat','last_size':'fsize'}[FAULT]
        original=getattr(Cursor.result,method)
        setattr(Cursor.result,method,lambda index: original(index) if index!=71 else 'bad')
    elif FAULT=='extra':Cursor.extra=True
    elif FAULT=='suffix':Cursor.result.values=[row[:-1]+(b'bad canonical framing',)]
    elif FAULT=='close':Cursor.close_effect=fail
    else:m.set_result=fail
    try:native.execute(t,b,execution_ledger=L)
    except BaseException as caught:
        if FAULT in ('close','publish'):
            assert caught is primary and caught.__cause__ is cause and caught.__context__ is context and caught.__suppress_context__
        else:assert type(caught) is PersistenceError and caught.code is E.INVALID_OBSERVATION
    else:raise AssertionError('failure escaped')
    assert_held(t,L,b)
    if FAULT=='cap': assert Cursor.result.copies==[(0,0)]
    elif FAULT in ('count2','last_name','last_oid','last_format','last_size'):assert not Cursor.result.copies
    assert not m._results[b._stamp]['populated']
    print('MANAGED_BODY_COMPLETE')
    """)
    )


@workers_companion
def test_unexpected_full_decoder_primary_is_preserved_and_cannot_publish_primitives():
    run(r"""
    WR._primary=KeyboardInterrupt('received decoder');WR._cause=ValueError('cause');WR._context=LookupError('context')
    WR._primary.__cause__=WR._cause;WR._primary.__context__=WR._context;WR._primary.__suppress_context__=True
    WR._seen=[];WR._managed=m
    exec('def _decode_read_raw(request, rows, /):\n    assert _managed._counts["D"] == 1\n    _seen.append((request, rows))\n    raise _primary',WR.__dict__)
    L,x,actual,c,r,a,t,b,op,req=setup_workers()
    try:native.execute(t,b,execution_ledger=L)
    except KeyboardInterrupt as caught:
        assert caught is WR._primary and caught.__cause__ is WR._cause and caught.__context__ is WR._context and caught.__suppress_context__
    else:raise AssertionError('decoder bypassed')
    assert WR._seen==[(req,())] and WR._seen[0][0] is req
    assert_held(t,L,b)
    assert not m._results[b._stamp]['populated']
    print('MANAGED_BODY_COMPLETE')
    """)


@workers_companion
def test_competing_invocation_cannot_hold_the_actual_workers_issuer():
    run(r"""
    L,x,actual,c,r,a,t,b,op,req=setup_workers()
    def compete(cursor):
        expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L))
        ticket=m._ticket(t,L)
        assert ticket.operation['state']=='RUNNING'
        assert ticket.roots[t._subject]['state']=='ACTIVE'
        assert not L.uncertainty.present
    Cursor.effect=compete
    native.execute(t,b,execution_ledger=L)
    assert m.read_result(b,execution_ledger=L) is None
    assert not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)


@workers_companion
def test_primitive_decoder_return_cannot_be_published_as_workers_success():
    run(r"""
    exec('def _decode_read_raw(request, rows, /):\n    return rows',WR.__dict__)
    L,x,actual,c,r,a,t,b,op,req=setup_workers()
    # Preserve the actual setter rejection; HELD makes the ledger uncertain.
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L))
    assert_held(t,L,b)
    assert not m._results[b._stamp]['populated']
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("inserted", [False, True])
@workers_companion
def test_w01_existing_identifier_is_allowed_only_for_noninserted_result(inserted):
    run(
        "INSERTED="
        + repr(inserted)
        + "\n"
        + textwrap.dedent(r"""
    row=(b'\x01',UUID(int=2).bytes,bytes([INSERTED]))
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W01',[row])
    if INSERTED:
        expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
        assert_held(t,L,b)
    else:
        native.execute(t,b,execution_ledger=L)
        value=m.read_result(b,execution_ledger=L)
        assert value.work_id==str(UUID(int=2)) and value.inserted is False
        assert not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)
    )
