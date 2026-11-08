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
# Extend only the existing synthetic driver's official numeric symbol.
class Int8BinaryDumper:pass
numeric_types.Int8BinaryDumper=Int8BinaryDumper
_base_limits=limits
def limits(**overrides):
    values=dict(prepare_bytes=100000000,prepare_bytes_per_execution=50000000,result_bytes=100000000,result_bytes_per_ticket=50000000)
    values.update(overrides)
    return _base_limits(**values)
def setup_workers(key='W02',values=(),*,limit=1,after=None,budget=16777216):
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(result_bytes=100000000000,result_bytes_per_ticket=50000000000),execution_ledger=L)
    x=m.reserve_execution(L);actual=n.ManagedConnection(PG())
    c=n.attach_native(actual,x,execution_ledger=L)
    with m._construction(False):
        root,code=m._reserve_root(c,L);assert code is None
        actual.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(root,L,known=True)
    op=profile(key)
    if key=='W03':logical=WM.JobListRequest(after=after,limit=limit)
    elif key=='W02':logical=WM.JobReadRequest(work_id=str(UUID(int=1)))
    else:
        material=M.ProtectedBindingInput(material_state=M.MaterialState.ABSENT,codec=None,key_version=None,expires_at=None,cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=None,reference=None,content_binding=b'',recovery_metadata=b'',projection_metadata={})
        logical=WM.JobSubmitRequest(job=WM.JobInput(str(UUID(int=1)),'task',1,S.Scope('app'),{},original_available_at=datetime(2026,1,1,tzinfo=timezone.utc),protected=material))
    a=native.prepare_component(x,op,logical,execution_ledger=L,max_page_payload_bytes=budget if key=='W03' else None)
    req=m._preparations[a._stamp]['data']
    t=m.admit(root,a,execution_ledger=L)
    b=m.reserve_result(t,m.result_capacity(t,execution_ledger=L) if key=='W03' else P.result_capacity(op),execution_ledger=L)
    result=Result('E14',list(values))
    result.descriptor=N._selected_sql_descriptor(op.statement,op,request=req,max_page_payload_bytes=budget) if key=='W03' else N._selected_sql_descriptor(op.statement,op)
    result.nfields=len(result.descriptor.transport_columns)
    Cursor.result=result
    return L,x,actual,c,root,a,t,b,op,req
"""


_ROW_HELPER = r"""

def full_row(op,work_id=1,payload=None):
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    material=M.ProtectedBindingInput(material_state=M.MaterialState.ABSENT,codec=None,key_version=None,expires_at=None,cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=None,reference=None,content_binding=b'',recovery_metadata=b'',projection_metadata={})
    logical=WM.JobSubmitRequest(job=WM.JobInput(str(UUID(int=work_id)),'task',1,S.Scope('app'),{} if payload is None else payload,original_available_at=now,protected=material))
    submit=WB._submit_raw(logical)
    data=dict((p.name,value) for p,value in zip(submit.statement.parameters,submit.parameters))
    data.update(runnable_version=1,state='queued',cancellation_requested=False,token=None,ownership_revision=0,lease_until=None,available_at=now,cycle=1,attempt_count=0,dispatch_id=None,result=None,created_at=now,updated_at=now,success_origin=None,completion_guard_id=None,final_fence_at=None,completion_result_digest=None,resolution_operation_id=None,terminal_resolution_operation_id=None,resolution_present=False,job_work_id=UUID(int=work_id),job_application=b'app',job_tenant=None,job_owner=None,job_protected_binding=data['protected_binding'],job_semantic_input=data['semantic_input'])
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
    assert seen==[((execution,operation,logical),{'execution_ledger':ledger,'max_page_payload_bytes':None})]
    seen.clear();budget=object()
    assert native.prepare_component(execution,operation,logical,execution_ledger=ledger,max_page_payload_bytes=budget) is token
    assert seen==[((execution,operation,logical),{'execution_ledger':ledger,'max_page_payload_bytes':budget})]
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


@pytest.mark.parametrize("count", [0, 1, 2, 3, 256])
@workers_companion
def test_w03_complete_page_is_published_once_after_close_on_original_root(count):
    """Breaks on single-row admission, early publication, copies, or root replacement."""
    run(
        "COUNT="
        + repr(count)
        + "\n"
        + textwrap.dedent(r"""
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W03',limit=max(1,COUNT))
    Cursor.result.values=[full_row(op,i+1) for i in range(COUNT)]
    Cursor.result.ntuples=COUNT;Cursor.result.command_tuples=COUNT
    Cursor.result.command_status=('SELECT '+str(COUNT)).encode()
    initial_capacity=m._results[b._stamp]['capacity']
    original=actual.pgconn;setter=m.set_result;published=[]
    sentinel=object()
    for kind in (bytes,UUID,str,int,datetime):actual.adapters.dumpers[kind]=sentinel
    for col in Cursor.result.descriptor.transport_columns:actual.adapters.loaders[col.oid]=sentinel
    def inspect(handle,value,**kwargs):
        assert Cursor.instances[-1].closed and Cursor.instances[-1].connection is actual
        assert actual.pgconn is original and original.transaction_status is TransactionStatus.INTRANS
        assert type(value) is tuple and len(value)==COUNT
        assert all(type(item) is WO.JobRecord for item in value)
        assert [item.work.work_id for item in value]==[UUID(int=i+1) for i in range(COUNT)]
        published.append(value);return setter(handle,value,**kwargs)
    m.set_result=inspect
    native.execute(t,b,execution_ledger=L)
    assert len(published)==1 and m.read_result(b,execution_ledger=L) is published[0]
    assert m._results[b._stamp]['capacity']==initial_capacity
    assert Cursor.result.copies==[(row,col) for row in range(COUNT) for col in range(72)]
    cursor=Cursor.instances[-1]
    assert cursor.calls==[(Cursor.result.descriptor.sql,req.parameters+(16777216,),False,True)]
    assert len(req.parameters)==4 and req.parameters[-1]==max(1,COUNT)
    assert all(cursor.calls[0][1][index] is req.parameters[index] for index in range(4))
    assert cursor.calls[0][1][4] is m._preparations[a._stamp]['max_page_payload_bytes']
    assert cursor.adapters.dumpers=={bytes:BytesBinaryDumper,UUID:UUIDBinaryDumper,str:StrBinaryDumper,int:Int8BinaryDumper,datetime:DatetimeBinaryDumper}
    assert all(cursor.adapters.loaders[col.oid] is ByteaBinaryLoader for col in Cursor.result.descriptor.transport_columns)
    assert all(value is sentinel for value in actual.adapters.dumpers.values())
    assert all(value is sentinel for value in actual.adapters.loaders.values())
    ticket=m._ticket(t,L)
    assert ticket.current is r and ticket.roots[t._subject]['state']=='ACTIVE'
    assert not L.uncertainty.present and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
""")
    )


@pytest.mark.parametrize(
    "fault",
    [
        "overflow",
        "negative",
        "bool_count",
        "command_status",
        "command_tuples",
        "rowcount",
        "statusmessage",
        "last_name",
        "last_oid",
        "last_format",
        "last_size",
        "binary",
        "status",
        "nfields",
    ],
)
@workers_companion
def test_w03_count_tag_and_complete_metadata_reject_before_cell_access(fault):
    """Breaks if any metadata or retained-limit check happens after copying cells."""
    run(
        "FAULT="
        + repr(fault)
        + "\n"
        + textwrap.dedent(r"""
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W03',limit=2)
    Cursor.result.values=[full_row(op,1),full_row(op,2)]
    Cursor.result.ntuples=2;Cursor.result.command_tuples=2;Cursor.result.command_status=b'SELECT 2'
    if FAULT=='overflow':
        Cursor.result.values.append(full_row(op,3));Cursor.result.ntuples=3
        Cursor.result.command_tuples=3;Cursor.result.command_status=b'SELECT 3'
    elif FAULT=='negative':Cursor.result.ntuples=-1
    elif FAULT=='bool_count':Cursor.result.ntuples=True
    elif FAULT=='command_status':Cursor.result.command_status=b'SELECT 02'
    elif FAULT=='command_tuples':Cursor.result.command_tuples=1
    elif FAULT in ('rowcount','statusmessage'):
        original_execute=Cursor.execute
        def execute(cursor,*args,**kwargs):
            original_execute(cursor,*args,**kwargs)
            if FAULT=='rowcount':cursor.rowcount=1
            else:cursor.statusmessage='SELECT 1'
        Cursor.execute=execute
    elif FAULT.startswith('last_'):
        method={'last_name':'fname','last_oid':'ftype','last_format':'fformat','last_size':'fsize'}[FAULT]
        original=getattr(Cursor.result,method)
        setattr(Cursor.result,method,lambda index:original(index) if index!=71 else 'bad')
    elif FAULT=='binary':Cursor.result.binary_tuples=0
    elif FAULT=='status':Cursor.result.status=ExecStatus.COMMAND_OK
    else:Cursor.result.nfields=71
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
    assert Cursor.result.copies==[] and not m._results[b._stamp]['populated']
    assert_held(t,L,b)
    print('MANAGED_BODY_COMPLETE')
""")
    )


@pytest.mark.parametrize("row_index", [0, 1])
@workers_companion
def test_w03_each_row_cap_precedes_its_remaining_cells(row_index):
    """Breaks if a bad row payload is copied or an earlier valid prefix is published."""
    run(
        "BAD_ROW="
        + repr(row_index)
        + "\n"
        + textwrap.dedent(r"""
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W03',limit=2)
    wire_rows=[full_row(op,1),full_row(op,2)]
    wire_rows[BAD_ROW]=(b'\x00',)+wire_rows[BAD_ROW][1:]
    Cursor.result.values=wire_rows;Cursor.result.ntuples=2
    Cursor.result.command_tuples=2;Cursor.result.command_status=b'SELECT 2'
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
    assert Cursor.result.copies==[(row,col) for row in range(BAD_ROW) for col in range(72)]+[(BAD_ROW,0)]
    assert not m._results[b._stamp]['populated']
    assert_held(t,L,b)
    print('MANAGED_BODY_COMPLETE')
""")
    )


@pytest.mark.parametrize(
    "fault",
    ["duplicate", "reverse", "cursor_equal", "cursor_before", "namespace", "suffix", "extra"],
)
@workers_companion
def test_w03_late_semantic_or_extra_result_failure_never_exposes_prefix(fault):
    """Breaks if issuer publishes before the actual raw consumer validates all rows."""
    run(
        "FAULT="
        + repr(fault)
        + "\n"
        + textwrap.dedent(r"""
    after=M.WorkCursor(created_at=datetime(2026,1,1,tzinfo=timezone.utc),work_id=UUID(int=2)) if FAULT.startswith('cursor_') else None
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W03',limit=2,after=after)
    wire_rows=[full_row(op,1),full_row(op,2)]
    if FAULT=='duplicate':wire_rows[1]=wire_rows[0]
    elif FAULT=='reverse':wire_rows.reverse()
    elif FAULT=='cursor_equal':wire_rows=[full_row(op,2),full_row(op,3)]
    elif FAULT=='cursor_before':wire_rows=[full_row(op,1),full_row(op,3)]
    elif FAULT=='namespace':
        bad=list(wire_rows[1]);bad[4]=b'other';wire_rows[1]=tuple(bad)
    elif FAULT=='suffix':wire_rows[1]=wire_rows[1][:-1]+(b'bad canonical framing',)
    else:Cursor.extra=True
    Cursor.result.values=wire_rows;Cursor.result.ntuples=2
    Cursor.result.command_tuples=2;Cursor.result.command_status=b'SELECT 2'
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
    assert not m._results[b._stamp]['populated'] and len(Cursor.result.copies)==144
    assert_held(t,L,b)
    print('MANAGED_BODY_COMPLETE')
""")
    )


@workers_companion
def test_w03_cursor_tie_advances_by_uuid():
    """Breaks if equal timestamps reject a later UUID or lose retained scalar identity."""
    run(r"""
    instant=datetime(2026,1,1,tzinfo=timezone.utc);identity=UUID(int=1)
    after=M.WorkCursor(created_at=instant,work_id=identity)
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W03',limit=2,after=after)
    Cursor.result.values=[full_row(op,2),full_row(op,3)];Cursor.result.ntuples=2
    Cursor.result.command_tuples=2;Cursor.result.command_status=b'SELECT 2'
    native.execute(t,b,execution_ledger=L)
    value=m.read_result(b,execution_ledger=L)
    assert tuple(item.work.work_id for item in value)==(UUID(int=2),UUID(int=3))
    assert req.parameters[1] is instant and req.parameters[2] is identity
    assert all(Cursor.instances[-1].calls[0][1][index] is req.parameters[index] for index in range(4))
    print('MANAGED_BODY_COMPLETE')
""")


@pytest.mark.parametrize(
    "fault", ["binary", "record", "validate", "size", "close", "root_lost", "publish"]
)
@workers_companion
def test_w03_unexpected_late_failure_preserves_primary_and_paid_backing(fault):
    """Breaks on replaced exception metadata, premature refund, or prefix publication."""
    run(
        "FAULT="
        + repr(fault)
        + "\n"
        + textwrap.dedent(r"""
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W03',limit=2)
    Cursor.result.values=[full_row(op,1),full_row(op,2)];Cursor.result.ntuples=2
    Cursor.result.command_tuples=2;Cursor.result.command_status=b'SELECT 2'
    capacity=m._results[b._stamp]['capacity']
    primary=KeyboardInterrupt('received late failure');cause=ValueError('cause');context=LookupError('context')
    primary.__cause__=cause;primary.__context__=context;primary.__suppress_context__=True
    seen=[]
    def fail(*args,**kwargs):raise primary
    if FAULT=='binary':
        decoder=native._decode_binary_transport_row
        def decode(*args,**kwargs):
            seen.append(args)
            if len(seen)==2:raise primary
            return decoder(*args,**kwargs)
        native._decode_binary_transport_row=decode
    elif FAULT=='record':
        decoder=WR._decode_job_half_raw
        def decode(*args,**kwargs):
            seen.append(args)
            if len(seen)==2:raise primary
            return decoder(*args,**kwargs)
        WR._decode_job_half_raw=decode
    elif FAULT=='validate':
        validator=WO._validate_job_record_raw
        def validate(*args,**kwargs):
            seen.append(args)
            if len(seen)==2:raise primary
            return validator(*args,**kwargs)
        WO._validate_job_record_raw=validate
    elif FAULT=='size':P._result_size=fail
    elif FAULT=='close':Cursor.close_effect=fail
    elif FAULT=='root_lost':
        def close(cursor):actual.pgconn.transaction_status=TransactionStatus.UNKNOWN
        Cursor.close_effect=close
    else:m.set_result=fail
    try:native.execute(t,b,execution_ledger=L)
    except BaseException as caught:
        if FAULT=='root_lost':assert type(caught) is PersistenceError and caught.code is E.INVALID_OBSERVATION
        else:assert caught is primary and caught.__cause__ is cause and caught.__context__ is context and caught.__suppress_context__
    else:raise AssertionError('failure escaped')
    assert not m._results[b._stamp]['populated']
    assert m._results[b._stamp]['capacity']==capacity and m._counts['D']>=1
    assert_held(t,L,b)
    print('MANAGED_BODY_COMPLETE')
""")
    )


@pytest.mark.parametrize("budget", [1, 16777216, 2**31, 3758096384])
@workers_companion
def test_w03_five_argument_tuple_retains_each_scalar_and_uses_local_int8(budget):
    """Breaks if Q is replaced/narrowed or the four business arguments are changed."""
    run(
        "BUDGET="
        + repr(budget)
        + "\n"
        + textwrap.dedent(r"""
    instant=datetime(2026,1,1,tzinfo=timezone.utc);identity=UUID(int=9)
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W03',limit=256,after=M.WorkCursor(created_at=instant,work_id=identity),budget=BUDGET)
    business=req.parameters;retained=m._preparations[a._stamp]['max_page_payload_bytes']
    sentinel=object();actual.adapters.dumpers[int]=sentinel
    native.execute(t,b,execution_ledger=L)
    cursor=Cursor.instances[-1];parameters=cursor.calls[0][1]
    assert type(parameters) is tuple and len(parameters)==5 and parameters is not business
    assert all(parameters[index] is business[index] for index in range(4))
    assert parameters[4] is retained and retained is BUDGET
    assert req.parameters is business and len(business)==4
    assert business[1] is instant and business[2] is identity
    assert cursor.adapters.dumpers[int] is Int8BinaryDumper
    assert actual.adapters.dumpers[int] is sentinel
    assert m.read_result(b,execution_ledger=L)==()
    assert not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
""")
    )


@pytest.mark.parametrize("large", [False, True])
@pytest.mark.parametrize("excess", [False, True])
@workers_companion
def test_w03_canonical_exact_budget_or_late_plus_one_is_all_or_error(large, excess):
    """Breaks if repeated occurrences are deduplicated or Q is checked after the callback."""
    run(
        "LARGE="
        + repr(large)
        + "\nEXCESS="
        + repr(excess)
        + "\n"
        + textwrap.dedent(r"""
    op=profile('W03')
    payload={'blob':'x'*65536} if LARGE else None
    wire_page=[full_row(op,1,payload),full_row(op,2,payload)]
    fields=('intent_evidence','semantic_input','replay_input','protected_binding','result','resolution_record_result','resolution_record_evidence','resolution_record_binding','job_protected_binding','job_semantic_input','protected_sidecar','protected_reference','protected_recovery_metadata','projection_metadata')
    indexes=[index+1 for index,col in enumerate(op.statement.result.columns) if col.name in fields]
    expected=sum(len(row[index]) for row in wire_page for index in indexes if row[index] is not None)
    assert expected>0 and wire_page[0][15]==wire_page[0][62]
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W03',limit=2,budget=expected-int(EXCESS))
    Cursor.result.values=wire_page;Cursor.result.ntuples=2
    Cursor.result.command_status=b'SELECT 2';Cursor.result.command_tuples=2
    calls=[]
    def observe(frame,event,arg):
        if event=='call' and frame.f_code is WR._decode_list_raw.__code__:
            calls.append((frame.f_locals['request'],frame.f_locals['rows']))
    sys.setprofile(observe)
    try:
        if EXCESS:expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
        else:native.execute(t,b,execution_ledger=L)
    finally:sys.setprofile(None)
    assert len(Cursor.result.copies)==144
    if EXCESS:
        assert calls==[] and not m._results[b._stamp]['populated']
        assert_held(t,L,b)
    else:
        assert len(calls)==1 and calls[0][0] is req and type(calls[0][1]) is tuple
        value=m.read_result(b,execution_ledger=L)
        assert tuple(record.work.work_id for record in value)==(UUID(int=1),UUID(int=2))
        assert not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
""")
    )


@pytest.mark.parametrize(
    "field",
    [
        "intent_evidence",
        "semantic_input",
        "replay_input",
        "protected_binding",
        "result",
        "resolution_record_result",
        "resolution_record_evidence",
        "resolution_record_binding",
        "job_protected_binding",
        "job_semantic_input",
        "protected_sidecar",
        "protected_reference",
        "protected_recovery_metadata",
        "projection_metadata",
    ],
)
@workers_companion
def test_w03_canonical_budget_counts_each_large_occurrence_before_semantics(field):
    """Breaks if any of fourteen fields can bypass the canonical aggregate gate."""
    run(
        "FIELD="
        + repr(field)
        + "\n"
        + textwrap.dedent(r"""
    op=profile('W03')
    wire_page=[full_row(op,1),full_row(op,2)]
    large_fields=('intent_evidence','semantic_input','replay_input','protected_binding','result','resolution_record_result','resolution_record_evidence','resolution_record_binding','job_protected_binding','job_semantic_input','protected_sidecar','protected_reference','protected_recovery_metadata','projection_metadata')
    indexes={col.name:index+1 for index,col in enumerate(op.statement.result.columns) if col.name in large_fields}
    changed=list(wire_page[1]);changed[indexes[FIELD]]=b'x'*1024;wire_page[1]=tuple(changed)
    total=sum(len(row[index]) for row in wire_page for index in indexes.values() if row[index] is not None)
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W03',limit=2,budget=total-1)
    Cursor.result.values=wire_page;Cursor.result.ntuples=2
    Cursor.result.command_status=b'SELECT 2';Cursor.result.command_tuples=2
    calls=[]
    def observe(frame,event,arg):
        if event=='call' and frame.f_code is WR._decode_list_raw.__code__:calls.append(True)
    sys.setprofile(observe)
    try:expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
    finally:sys.setprofile(None)
    assert calls==[] and not m._results[b._stamp]['populated']
    assert len(Cursor.result.copies)==144
    assert_held(t,L,b)
    print('MANAGED_BODY_COMPLETE')
""")
    )


@workers_companion
def test_w03_received_pz013_preserves_driver_identity_and_held_lifetime():
    """Breaks if ordinary server budget overflow is sanitized or treated as safe retry."""
    run(r"""
    L,x,actual,c,r,a,t,b,op,req=setup_workers('W03',limit=2)
    capacity=m._results[b._stamp]['capacity']
    class DriverError(Exception):
        sqlstate='PZ013'
    primary=DriverError('W03 page payload budget exceeded');cause=ValueError('cause');context=LookupError('context')
    primary.__cause__=cause;primary.__context__=context;primary.__suppress_context__=True
    primary.diag=object();diag=primary.diag
    def overflow(cursor):
        actual.pgconn.transaction_status=TransactionStatus.INERROR
        raise primary
    Cursor.effect=overflow
    try:native.execute(t,b,execution_ledger=L)
    except DriverError as caught:
        assert caught is primary and caught.sqlstate=='PZ013' and caught.diag is diag
        assert caught.__cause__ is cause and caught.__context__ is context and caught.__suppress_context__
    else:raise AssertionError('server overflow converted to success')
    assert Cursor.instances[-1].closed and Cursor.result.copies==[]
    assert not m._results[b._stamp]['populated'] and m._results[b._stamp]['capacity']==capacity
    assert m._counts['D']>=1
    assert_held(t,L,b)
    print('MANAGED_BODY_COMPLETE')
""")
