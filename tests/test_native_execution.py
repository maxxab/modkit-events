"""Source-only issuer fixtures. These never import psycopg or prove database work."""

import textwrap

import pytest
from test_managed_lifecycle import _run
from test_managed_statement_lifecycle import _SETUP

_DRIVER = """
from types import ModuleType, SimpleNamespace
from enum import IntEnum
pg=ModuleType('psycopg')
pg.__version__='3.3.8'
class TransactionStatus(IntEnum):
    IDLE=0; ACTIVE=1; INTRANS=2; INERROR=3; UNKNOWN=4
class PipelineStatus(IntEnum):
    OFF=0; ON=1; ABORTED=2
class ExecStatus(IntEnum):
    COMMAND_OK=1; TUPLES_OK=2
pg.pq=SimpleNamespace(TransactionStatus=TransactionStatus,PipelineStatus=PipelineStatus,
    ExecStatus=ExecStatus,version=lambda:180006)
class Connection:
    def __init__(self,pgconn,row_factory=None):
        self.pgconn=pgconn;self.closed=False;self.autocommit=False
        self.adapters=SimpleNamespace(dumpers={},loaders={})
pg.Connection=Connection
rows=ModuleType('psycopg.rows'); rows.tuple_row=object()
strings=ModuleType('psycopg.types.string')
class BytesBinaryDumper:pass
class ByteaBinaryLoader:pass
strings.BytesBinaryDumper=BytesBinaryDumper;strings.ByteaBinaryLoader=ByteaBinaryLoader
sys.modules.update({'psycopg':pg,'psycopg.rows':rows,
    'psycopg.types':ModuleType('psycopg.types'),'psycopg.types.string':strings})
from modkit_events.persistence import native_sync as n
from modkit_events.persistence import native_execution as native
from modkit_events.persistence.native_codec import _selected_sql_descriptor

class PG:
    transaction_status=TransactionStatus.IDLE
    pipeline_status=PipelineStatus.OFF
class Result:
    status=ExecStatus.TUPLES_OK
    binary_tuples=1
    def __init__(self,key,values):
        self.descriptor=_selected_sql_descriptor(C.get_statement(key))
        self.values=values; self.ntuples=len(values)
        self.nfields=len(self.descriptor.transport_columns)
        self.command_status=('SELECT '+str(self.ntuples)).encode()
        self.command_tuples=self.ntuples
        self.copies=[]
    def fname(self,index):return self.descriptor.transport_columns[index].name.encode()
    def ftype(self,index):return self.descriptor.transport_columns[index].oid
    def fformat(self,index):return 1
    def fsize(self,index):
        oid=self.ftype(index)
        return {16:1,5069:8,23:4,2950:16,20:8,1184:8,17:-1}[oid]
    def get_value(self,row,column):
        self.copies.append((row,column));return self.values[row][column]
class Adapters:
    def __init__(self,original):
        self.dumpers=original.dumpers.copy();self.loaders=original.loaders.copy()
    def register_dumper(self,kind,impl):self.dumpers[kind]=impl
    def register_loader(self,oid,impl):self.loaders[oid]=impl
class Cursor:
    instances=[]; result=None; effect=None; close_effect=None; extra=None
    def __init__(self,actual,*,row_factory):
        assert row_factory is rows.tuple_row
        self.connection=actual;self.adapters=Adapters(actual.adapters)
        self.closed=False;self.calls=[];self.pgresult=None
        self.instances.append(self)
    def execute(self,sql,parameters,*,prepare,binary):
        self.calls.append((sql,parameters,prepare,binary))
        if Cursor.effect is not None:Cursor.effect(self)
        self.pgresult=Cursor.result
        self.rowcount=self.pgresult.ntuples
        self.statusmessage=self.pgresult.command_status.decode()
    def nextset(self):return Cursor.extra
    def close(self):
        if Cursor.close_effect is not None:Cursor.close_effect(self)
        self.closed=True
pg.RawCursor=Cursor

def setup(key='E14',values=None,capacity=4194304):
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);actual=n.ManagedConnection(PG())
    c=n.attach_native(actual,x,execution_ledger=L)
    with m._construction(False):
        root,code=m._reserve_root(c,L);assert code is None
        actual.pgconn.transaction_status=TransactionStatus.INTRANS
        m._complete_start(root,L,known=True)
    a=native.prepare(x,C.get_statement(key),() if key=='E14' else (b'id',),execution_ledger=L)
    t=m.admit(root,a,execution_ledger=L)
    b=m.reserve_result(t,capacity,execution_ledger=L)
    Cursor.result=Result(key,[(b'\x01',(17).to_bytes(8,'big'))] if values is None else values)
    return L,x,actual,c,root,a,t,b
"""


def run(body):
    _run(_SETUP + _DRIVER + textwrap.dedent(body))


def test_fixed_execute_consumes_exact_paid_request_and_preserves_identity():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    req=m._preparations[a._stamp]['data'];parameters=req.parameters;context=req.context
    assert native.execute(t,b,execution_ledger=L) is None
    cursor=Cursor.instances[0]
    assert cursor.calls==[(_selected_sql_descriptor(req.statement).sql,parameters,False,True)]
    assert cursor.calls[0][1] is parameters
    assert req.parameters is parameters and req.context is context
    assert cursor.closed and m.read_result(b,execution_ledger=L)==17
    assert not L.uncertainty.present and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_absent_e28_is_paid_and_does_not_copy_a_row():
    run("""
    L,x,actual,c,r,a,t,b=setup('E28',[])
    native.execute(t,b,execution_ledger=L)
    assert m.read_result(b,execution_ledger=L) is None
    assert Cursor.result.copies==[]
    assert Cursor.instances[0].calls[0][1] is m._preparations[a._stamp]['data'].parameters
    print('MANAGED_BODY_COMPLETE')
    """)


def test_driver_failure_preserves_primary_and_holds_active_physical_work():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    primary=KeyboardInterrupt('NONSECRET_PRIMARY');cause=ValueError('NONSECRET_CAUSE')
    primary.__cause__=cause;primary.__suppress_context__=True
    def fail(cursor):
        actual.pgconn.transaction_status=TransactionStatus.ACTIVE
        raise primary
    Cursor.effect=fail
    try:native.execute(t,b,execution_ledger=L)
    except BaseException as caught:
        assert caught is primary and caught.__cause__ is cause and caught.__suppress_context__
    else:raise AssertionError('missing error')
    p=m._ticket(t,L)
    assert p.operation['state']=='HELD' and p.operation['running']
    assert p.roots[t._subject]['state']=='UNKNOWN' and L.uncertainty.present
    assert m._counts['D']>=1 and old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_expected_adapter_hooks_are_overridden_only_on_cursor():
    run("""
    L,x,actual,c,r,a,t,b=setup('E28',[])
    sentinel=object();actual.adapters.dumpers[bytes]=sentinel
    for col in Cursor.result.descriptor.transport_columns:
        actual.adapters.loaders[col.oid]=sentinel
    def inspect(cursor):
        assert cursor.adapters.dumpers[bytes] is BytesBinaryDumper
        assert all(cursor.adapters.loaders[col.oid] is ByteaBinaryLoader
            for col in Cursor.result.descriptor.transport_columns)
    Cursor.effect=inspect
    native.execute(t,b,execution_ledger=L)
    assert actual.adapters.dumpers[bytes] is sentinel
    assert all(value is sentinel for value in actual.adapters.loaders.values())
    print('MANAGED_BODY_COMPLETE')
    """)


def test_failed_cursor_close_is_not_retried_and_remains_primary():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    primary=SystemExit('NONSECRET_CLOSE'); calls=[]
    def fail(cursor):
        calls.append(cursor);raise primary
    Cursor.close_effect=fail
    try:native.execute(t,b,execution_ledger=L)
    except BaseException as caught:assert caught is primary
    else:raise AssertionError('missing error')
    assert len(calls)==1
    p=m._ticket(t,L)
    assert p.operation['state']=='HELD' and not p.operation['running']
    assert L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)


def test_lost_start_acknowledgement_still_marks_started_gate_unknown():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    primary=KeyboardInterrupt('NONSECRET_START_ACK')
    start=m._start_operation
    def lose(*args,**kwargs):
        start(*args,**kwargs);raise primary
    m._start_operation=lose
    try:native.execute(t,b,execution_ledger=L)
    except BaseException as caught:assert caught is primary
    else:raise AssertionError('missing error')
    p=m._ticket(t,L)
    assert p.operation['state']=='HELD' and p.operation['running']
    assert p.roots[t._subject]['state']=='UNKNOWN' and L.uncertainty.present
    assert Cursor.instances==[]
    print('MANAGED_BODY_COMPLETE')
    """)


def test_missing_physical_ack_is_checked_before_any_result_copy():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    def active(cursor):actual.pgconn.transaction_status=TransactionStatus.ACTIVE
    Cursor.effect=active
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
    assert Cursor.result.copies==[]
    assert m._ticket(t,L).operation['running']
    print('MANAGED_BODY_COMPLETE')
    """)


def test_completion_capacity_exhaustion_uses_paid_held_transition():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    setter=m.set_result
    def paid_then_exhaust(*args,**kwargs):
        setter(*args,**kwargs)
        with old._synchronized():
            assert m._charge({'D':m._limits.construction_slots-m._counts['D']})
    m.set_result=paid_then_exhaust
    try:native.execute(t,b,execution_ledger=L)
    except PersistenceError as caught:assert caught.code is E.CAPACITY_EXCEEDED
    else:raise AssertionError('missing capacity rejection')
    p=m._ticket(t,L)
    assert p.operation['state']=='HELD' and not p.operation['running']
    assert p.roots[t._subject]['state']=='UNKNOWN' and L.uncertainty.present
    assert m._results[b._stamp]['populated']
    print('MANAGED_BODY_COMPLETE')
    """)


def test_complete_e28_row_is_validated_and_coupled_without_request_replacement():
    run("""
    row=outbox()
    from datetime import datetime,timezone
    epoch=datetime(2000,1,1,tzinfo=timezone.utc)
    def binary(value):
        if value is None or type(value) is bytes:return value
        if type(value) is str:return value.encode()
        if type(value) is datetime:return int((value-epoch).total_seconds()*1000000).to_bytes(8,'big',signed=True)
        raise AssertionError(type(value))
    values=[]
    for column in C.get_statement('E28').result.columns:
        value=getattr(row,column.name)
        if type(value) is int:value=value.to_bytes(4 if column.name=='canonical_version' else 8,'big',signed=True)
        else:value=binary(value)
        values.append(value)
    L,x,actual,c,r,a,t,b=setup('E28',[(b'\x01',*values)])
    req=m._preparations[a._stamp]['data'];parameters=req.parameters
    native.execute(t,b,execution_ledger=L)
    assert m.read_result(b,execution_ledger=L)==row
    assert req.parameters is parameters
    assert len(Cursor.result.copies)==14
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize(
    "mutation",
    [
        "Cursor.result.status=ExecStatus.COMMAND_OK",
        "Cursor.result.nfields=1",
        "Cursor.result.binary_tuples=0",
        "Cursor.result.ntuples=0",
        "Cursor.result.ntuples=2",
        "Cursor.result.ntuples=True",
        "Cursor.result.command_status=b'SELECT 2'",
        "Cursor.result.command_tuples=2",
        "Cursor.result.fname=lambda index:b'wrong'",
        "Cursor.result.ftype=lambda index:25",
        "Cursor.result.fformat=lambda index:0",
        "Cursor.result.fsize=lambda index:999",
    ],
)
def test_bad_metadata_is_rejected_before_copy(mutation):
    run(
        """
    L,x,actual,c,r,a,t,b=setup()
    """
        + mutation
        + """
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
    assert Cursor.result.copies==[]
    p=m._ticket(t,L)
    assert p.operation['state']=='HELD' and not p.operation['running']
    assert p.roots[t._subject]['state']=='UNKNOWN' and L.uncertainty.present
    assert not m._results[b._stamp]['populated']
    print('MANAGED_BODY_COMPLETE')
    """
    )


@pytest.mark.parametrize("value", ["None", "b'\\x00'", "b'xx'", "1"])
def test_bad_cap_never_copies_payload(value):
    run(
        """
    L,x,actual,c,r,a,t,b=setup(values=[("""
        + value
        + """,(17).to_bytes(8,'big'))])
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L),True)
    assert Cursor.result.copies==[(0,0)]
    assert L.uncertainty.present and m._ticket(t,L).operation['state']=='HELD'
    print('MANAGED_BODY_COMPLETE')
    """
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "actual.autocommit=True",
        "actual.closed=True",
        "actual.pgconn.transaction_status=TransactionStatus.IDLE",
        "actual.pgconn.transaction_status=TransactionStatus.INERROR",
        "actual.pgconn.pipeline_status=PipelineStatus.ON",
        "pg.__version__='3.3.7'",
        "pg.pq.version=lambda:170000",
        "actual.pgconn=PG()",
    ],
)
def test_invalid_physical_profile_never_executes(mutation):
    run(
        """
    L,x,actual,c,r,a,t,b=setup()
    """
        + mutation
        + """
    expect(E.PROFILE_REJECTED,lambda:native.execute(t,b,execution_ledger=L),True)
    assert Cursor.instances==[]
    assert m._ticket(t,L).operation['state']=='HELD' and L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """
    )


def test_result_capacity_failure_after_execute_is_held_not_retryable():
    run("""
    L,x,actual,c,r,a,t,b=setup(capacity=1)
    try:native.execute(t,b,execution_ledger=L)
    except PersistenceError as caught:assert caught.code is E.CAPACITY_EXCEEDED
    else:raise AssertionError('missing capacity rejection')
    assert len(Cursor.instances)==1 and len(Cursor.instances[0].calls)==1
    assert m._ticket(t,L).operation['state']=='HELD' and L.uncertainty.present
    before=m._counts.copy()
    expect(E.RESOURCE_BUSY,lambda:m.release_result(b,execution_ledger=L),True)
    expect(E.RESOURCE_BUSY,lambda:m.release_ticket(t,execution_ledger=L),True)
    assert m._counts==before
    print('MANAGED_BODY_COMPLETE')
    """)


def test_primary_graph_survives_cleanup_and_ledger_failures_without_formatting():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    calls=[]
    class Primary(BaseException):
        def __str__(self):calls.append('str');raise AssertionError('formatted primary')
    primary=Primary();cause=ValueError();context=LookupError()
    primary.__cause__=cause;primary.__context__=context;primary.__suppress_context__=False
    suffix=[]
    def fail(cursor):
        try:raise primary
        except BaseException as caught:
            suffix.append(caught.__traceback__);raise
    def close_fail(cursor):raise SystemExit('NONSECRET_SECONDARY')
    def union_fail(self,code):raise RuntimeError('NONSECRET_UNION')
    Cursor.effect=fail;Cursor.close_effect=close_fail;ExecutionLedger.note_incident=union_fail
    try:native.execute(t,b,execution_ledger=L)
    except BaseException as caught:
        assert caught is primary and caught.__cause__ is cause
        assert caught.__context__ is context and not caught.__suppress_context__
        trace=caught.__traceback__
        while trace is not None and trace is not suffix[0]:trace=trace.tb_next
        assert trace is suffix[0]
    else:raise AssertionError('missing primary')
    assert calls==[]
    p=m._ticket(t,L)
    assert p.operation['state']=='HELD' and p.roots[t._subject]['state']=='UNKNOWN'
    assert old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_preparation_reserves_before_freeze_and_invalid_inputs_release_no_io():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L);freeze=native._freeze_request_raw;seen=[]
    def check(*args,**kwargs):
        assert m._counts['AB']==1024 and m._counts['D']>=1
        seen.append(True);return freeze(*args,**kwargs)
    native._freeze_request_raw=check
    expect(E.LOCAL_INVALID_ARGUMENT,
        lambda:native.prepare(x,C.get_statement('E28'),[b'id'],execution_ledger=L))
    assert m._counts['A']==0 and m._counts['AB']==0 and m._counts['D']==0
    a=native.prepare(x,C.get_statement('E28'),(b'a'*256,),execution_ledger=L)
    assert m._preparations[a._stamp]['data'].parameters==(b'a'*256,)
    assert len(seen)==2 and Cursor.instances==[]
    print('MANAGED_BODY_COMPLETE')
    """)


def test_cancelled_waiter_holds_without_finishing_or_refunding_actual_worker():
    run("""
    from threading import Event,Thread
    L,x,actual,c,r,a,t,b=setup()
    entered,finish=Event(),Event();errors=[]
    def delay(cursor):
        entered.set();assert finish.wait(5)
    Cursor.effect=delay
    def work():
        try:native.execute(t,b,execution_ledger=L)
        except BaseException as error:errors.append(error)
    worker=Thread(target=work);worker.start();assert entered.wait(5)
    m._hold_operation(t,L)
    assert m._ticket(t,L).operation['running']
    before=m._counts.copy()
    expect(E.RESOURCE_BUSY,lambda:m.release_result(b,execution_ledger=L),True)
    assert m._counts==before
    finish.set();worker.join(5);assert not worker.is_alive() and len(errors)==1
    assert m._ticket(t,L).operation['state']=='HELD'
    assert not m._ticket(t,L).operation['running'] and L.uncertainty.present
    assert not m._results[b._stamp]['populated']
    print('MANAGED_BODY_COMPLETE')
    """)


def test_known_invalid_result_rejects_without_poisoning_unstarted_operation():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,a,execution_ledger=L))
    assert Cursor.instances==[] and not old._domain.stopped and m._counts['D']==0
    p=m._ticket(t,L)
    assert p.operation['state']=='ADMITTED' and p.roots[t._subject]['state']=='ACTIVE'
    assert not L.uncertainty.present
    native.execute(t,b,execution_ledger=L)
    assert m.read_result(b,execution_ledger=L)==17
    print('MANAGED_BODY_COMPLETE')
    """)


def test_duplicate_complete_rejects_without_revoking_completed_result():
    run("""
    L,x,actual,c,r,a,t,b=setup()
    native.execute(t,b,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L))
    assert len(Cursor.instances)==1 and not old._domain.stopped and m._counts['D']==0
    assert m.read_result(b,execution_ledger=L)==17
    assert m._ticket(t,L).operation['state']=='COMPLETED' and not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)


def test_wrong_ledger_cannot_poison_original_operation():
    run("""
    L,x,actual,c,r,a,t,b=setup();other=ExecutionLedger()
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=other))
    assert not old._domain.stopped and m._counts['D']==0
    assert not L.uncertainty.present and not other.uncertainty.present
    assert m._ticket(t,L).operation['state']=='ADMITTED'
    print('MANAGED_BODY_COMPLETE')
    """)


def test_overlapping_execute_cannot_hold_another_issuers_running_operation():
    run("""
    from threading import Event,Thread
    L,x,actual,c,r,a,t,b=setup();entered,finish=Event(),Event();errors=[]
    def delay(cursor):entered.set();assert finish.wait(5)
    Cursor.effect=delay
    def work():
        try:native.execute(t,b,execution_ledger=L)
        except BaseException as error:errors.append(error)
    worker=Thread(target=work);worker.start();assert entered.wait(5)
    expect(E.INVALID_OBSERVATION,lambda:native.execute(t,b,execution_ledger=L))
    assert not old._domain.stopped and not L.uncertainty.present
    assert m._ticket(t,L).operation['state']=='RUNNING'
    finish.set();worker.join(5);assert not worker.is_alive() and errors==[]
    assert m.read_result(b,execution_ledger=L)==17 and len(Cursor.instances)==1
    print('MANAGED_BODY_COMPLETE')
    """)


def test_preparation_with_one_construction_slot_succeeds_without_extra_reservation():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(construction_slots=1),execution_ledger=L)
    x=m.reserve_execution(L)
    a=native.prepare(x,C.get_statement('E14'),(),execution_ledger=L)
    assert not old._domain.stopped and m._counts['D']==0
    assert m._counts['A']==1 and m._counts['AB']==1024
    assert m._preparations[a._stamp]['data'].statement is C.get_statement('E14')
    m.release_preparation(a,execution_ledger=L)
    assert m._counts['A']==m._counts['AB']==m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_preparation_busy_construction_rejects_before_reserving_an_envelope():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(construction_slots=1),execution_ledger=L)
    x=m.reserve_execution(L)
    with m._construction(False):
        expect(E.CAPACITY_EXCEEDED,lambda:native.prepare(x,C.get_statement('E14'),(),execution_ledger=L))
        assert m._counts['A']==m._counts['AB']==0 and m._counts['D']==1
        assert not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_preparation_survives_another_thread_using_every_remaining_construction_slot():
    run("""
    from threading import Event,Thread
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(construction_slots=2),execution_ledger=L)
    x=m.reserve_execution(L);ready,finish=Event(),Event();freeze=native._freeze_request_raw
    def hold():
        with m._construction(False):ready.set();assert finish.wait(5)
    other=Thread(target=hold)
    def freeze_under_pressure(*args,**kwargs):
        other.start();assert ready.wait(5)
        assert m._counts['D']==2
        return freeze(*args,**kwargs)
    native._freeze_request_raw=freeze_under_pressure
    try:
        a=native.prepare(x,C.get_statement('E14'),(),execution_ledger=L)
        assert m._counts['D']==1 and not old._domain.stopped
        assert m._preparations[a._stamp]['data'].statement is C.get_statement('E14')
    finally:
        finish.set();other.join(5)
    assert not other.is_alive() and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_preparation_invalid_input_and_envelope_pressure_leave_no_unreturned_charge():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(construction_slots=1,
        preparations=1,preparations_per_execution=1),execution_ledger=L)
    x=m.reserve_execution(L)
    expect(E.LOCAL_INVALID_ARGUMENT,lambda:native.prepare(x,C.get_statement('E28'),[b'id'],execution_ledger=L))
    assert m._counts['A']==m._counts['AB']==m._counts['D']==0 and not old._domain.stopped
    a=native.prepare(x,C.get_statement('E14'),(),execution_ledger=L)
    before=m._counts.copy()
    expect(E.CAPACITY_EXCEEDED,lambda:native.prepare(x,C.get_statement('E14'),(),execution_ledger=L))
    assert m._counts==before and not old._domain.stopped and len(m._preparations)==1
    print('MANAGED_BODY_COMPLETE')
    """)


@pytest.mark.parametrize("after", [False, True])
def test_unexpected_paid_setter_failure_never_refunds_uncertain_preparation(after):
    run(
        """
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(construction_slots=1),execution_ledger=L)
    x=m.reserve_execution(L);setter=m._set_preparation_paid
    primary=KeyboardInterrupt('NONSECRET_PREPARATION_SETTER');cause=ValueError()
    primary.__cause__=cause
    def fail(*args,**kwargs):
        if """
        + str(after)
        + """:assert setter(*args,**kwargs) is None
        raise primary
    m._set_preparation_paid=fail
    try:native.prepare(x,C.get_statement('E14'),(),execution_ledger=L)
    except BaseException as caught:assert caught is primary and caught.__cause__ is cause
    else:raise AssertionError('missing failure')
    assert old._domain.stopped and m._counts['D']==1
    assert m._counts['A']==1 and m._counts['AB']==1024
    assert (next(iter(m._preparations.values()))['data'] is not None) is """
        + str(after)
        + """
    print('MANAGED_BODY_COMPLETE')
    """
    )


def test_lost_paid_reserve_acknowledgement_retains_unreturned_preparation():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(construction_slots=1),execution_ledger=L)
    x=m.reserve_execution(L);reserve=m._reserve_preparation_paid
    primary=SystemExit('NONSECRET_PREPARATION_RESERVE')
    def lose(*args,**kwargs):
        token,code=reserve(*args,**kwargs);assert code is None
        raise primary
    m._reserve_preparation_paid=lose
    try:native.prepare(x,C.get_statement('E14'),(),execution_ledger=L)
    except BaseException as caught:assert caught is primary
    else:raise AssertionError('missing failure')
    assert old._domain.stopped and m._counts['D']==1
    assert m._counts['A']==1 and m._counts['AB']==1024
    print('MANAGED_BODY_COMPLETE')
    """)


def test_preparation_invalid_freeze_cleans_up_while_all_other_slots_are_busy():
    run("""
    from threading import Event,Thread
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(construction_slots=2),execution_ledger=L)
    x=m.reserve_execution(L);ready,finish=Event(),Event();freeze=native._freeze_request_raw
    def hold():
        with m._construction(False):ready.set();assert finish.wait(5)
    other=Thread(target=hold)
    def freeze_under_pressure(*args,**kwargs):
        other.start();assert ready.wait(5)
        return freeze(*args,**kwargs)
    native._freeze_request_raw=freeze_under_pressure
    try:
        expect(E.LOCAL_INVALID_ARGUMENT,lambda:native.prepare(x,C.get_statement('E28'),[b'id'],execution_ledger=L))
        assert m._counts['D']==1 and m._counts['A']==m._counts['AB']==0
        assert not old._domain.stopped
    finally:
        finish.set();other.join(5)
    assert not other.is_alive() and m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_preparation_byte_pressure_and_small_reserved_buffer_refund_known_rejections():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(construction_slots=1,
        prepare_bytes=512,prepare_bytes_per_execution=512),execution_ledger=L)
    x=m.reserve_execution(L)
    expect(E.CAPACITY_EXCEEDED,lambda:native.prepare(x,C.get_statement('E14'),(),execution_ledger=L))
    assert m._counts['A']==m._counts['AB']==m._counts['D']==0 and not old._domain.stopped
    native._PREPARATION_BYTES=1
    expect(E.CAPACITY_EXCEEDED,lambda:native.prepare(x,C.get_statement('E14'),(),execution_ledger=L))
    assert m._counts['A']==m._counts['AB']==m._counts['D']==0 and not old._domain.stopped
    assert m._executions[x._stamp]['preparations']==0 and m._executions[x._stamp]['prepare_bytes']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_paid_preparation_rejects_foreign_dead_and_cross_thread_owners():
    run("""
    from threading import Thread
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(),execution_ledger=L)
    x=m.reserve_execution(L)
    with m._construction(False) as owner:
        a,code=m._reserve_preparation_paid(x,1024,L,owner);assert code is None
        before=m._counts.copy()
        with m._construction(False) as other:
            assert m._set_preparation_paid(a,b'foreign',L,other,unreturned=True) is E.INVALID_OBSERVATION
            assert m._release_preparation_paid(a,L,other,unreturned=True) is E.INVALID_OBSERVATION
        assert m._counts==before and m._preparations[a._stamp]['data'] is None
        errors=[]
        def foreign_thread():
            for call in (lambda:m._reserve_preparation_paid(x,1,L,owner),
                         lambda:m._set_preparation_paid(a,b'foreign',L,owner,unreturned=True),
                         lambda:m._release_preparation_paid(a,L,owner,unreturned=True)):
                try:call()
                except PersistenceError as error:errors.append(error)
        thread=Thread(target=foreign_thread);thread.start();thread.join(5)
        assert not thread.is_alive() and len(errors)==3
        assert all(error.code is E.INVALID_OBSERVATION and error.unconfirmed for error in errors)
        assert m._counts==before and m._preparations[a._stamp]['data'] is None
    before=m._counts.copy()
    for call in (lambda:m._reserve_preparation_paid(x,1,L,owner),
                 lambda:m._set_preparation_paid(a,b'dead',L,owner,unreturned=True),
                 lambda:m._release_preparation_paid(a,L,owner,unreturned=True)):
        expect(E.INVALID_OBSERVATION,call,True)
    assert m._counts==before and not old._domain.stopped
    m.set_preparation(a,b'public',execution_ledger=L)
    m.release_preparation(a,execution_ledger=L)
    assert m._counts['A']==m._counts['AB']==m._counts['D']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_unexpected_setter_persistence_error_is_not_a_known_rejection():
    run("""
    L=ExecutionLedger();m.configure_managed_registry(limits=limits(construction_slots=1),execution_ledger=L)
    x=m.reserve_execution(L);primary=None
    try:m._reject(E.CAPACITY_EXCEEDED,False)
    except PersistenceError as caught:primary=caught
    def fail(*args,**kwargs):raise primary
    m._set_preparation_paid=fail
    try:native.prepare(x,C.get_statement('E14'),(),execution_ledger=L)
    except PersistenceError as caught:assert caught is primary
    else:raise AssertionError('missing failure')
    assert old._domain.stopped and m._counts['A']==m._counts['D']==1 and m._counts['AB']==1024
    print('MANAGED_BODY_COMPLETE')
    """)
