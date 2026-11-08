"""Source-only canonical statement lifecycle tests; no driver or database proof."""

import textwrap

from test_managed_lifecycle import _FIXTURE, _run

_SETUP = """
from dataclasses import fields
from datetime import datetime, timezone
from sys import getsizeof
from modkit_events.persistence import bindings as B, catalog as C, observations as O

original_limits = limits
def limits(**overrides):
    values = dict(prepare_bytes=8388608, prepare_bytes_per_execution=4194304,
        result_bytes=8388608, result_bytes_per_ticket=4194304)
    values.update(overrides)
    return original_limits(**values)

def request(key='E14', event_id=b'id'):
    return B._freeze_request_raw(C.get_statement(key), () if key=='E14' else (event_id,),
        context=B._return_context_raw())

def request_size(value):
    # Independent explicit graph accounting, not a production size helper.
    return (getsizeof(value) + getsizeof(value.parameters)
        + sum(getsizeof(item) for item in value.parameters)
        + getsizeof(value.context) + getsizeof(value.context.expected))

def prepared(key='E14', event_id=b'id', result_capacity=4096):
    L,x,actual,c=setup_physical()
    r=active_root(c,L)
    req=request(key,event_id)
    a=m.reserve_preparation(x,request_size(req),execution_ledger=L)
    parameters,context=req.parameters,req.context
    m.set_preparation(a,req,execution_ledger=L)
    assert req.parameters is parameters and req.context is context
    t=m.admit(r,a,execution_ledger=L)
    b=m.reserve_result(t,result_capacity,execution_ledger=L)
    return L,x,actual,c,r,req,a,t,b

def outbox():
    replay=b'{"event_id":"id","name":"event","payload":{},"schema_version":1,"metadata":{}}'
    event=B._validate_event_replay_raw(replay)
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    return O.OutboxRow(event_id=b'id',canonical_version=1,
        envelope_evidence=B._canonical_event_raw(event).content,replay_input=replay,
        state='pending',token=None,ownership_revision=0,lease_until=None,
        intent_id=None,receipt=None,outcome_evidence=None,created_at=now,updated_at=now)
"""


def run(body):
    _run(_FIXTURE + _SETUP + textwrap.dedent(body))


def test_paid_request_is_exact_typed_backing_consumed_by_start():
    """Serialization placeholders or a replacement request would fail identity."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared('E28')
    before=m.capacity_snapshot(execution_ledger=L)
    assert before['AB']==request_size(req)
    assert m._start_operation(t,b,L) is req
    assert req.parameters==(b'id',) and type(req.parameters[0]) is bytes
    assert m.capacity_snapshot(execution_ledger=L)==before
    print('MANAGED_BODY_COMPLETE')
    """)


def test_request_capacity_covers_carrier_context_and_parameter_not_only_bytes():
    """A one-byte short full backing reservation must reject without publication."""
    run("""
    L,x,actual,c=setup_physical()
    req=request('E28')
    a=m.reserve_preparation(x,request_size(req)-1,execution_ledger=L)
    expect(E.CAPACITY_EXCEEDED,lambda:m.set_preparation(a,req,execution_ledger=L))
    r=active_root(c,L)
    expect(E.INVALID_OBSERVATION,lambda:m.admit(r,a,execution_ledger=L))
    assert m.capacity_snapshot(execution_ledger=L)['AB']==request_size(req)-1
    assert not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_typed_request_rejects_noncanonical_metadata_and_mutable_parameters():
    """Frozen carrier shape alone cannot authorize forged descriptors or lists."""
    run("""
    from dataclasses import replace
    L,x,actual,c=setup_physical()
    a=m.reserve_preparation(x,4096,execution_ledger=L)
    for name,value in (('statement',replace(C.get_statement('E14'))),
                       ('parameters',[b'id'])):
        bad=request('E28') if name=='parameters' else request()
        object.__setattr__(bad,name,value)
        expect(E.LOCAL_INVALID_ARGUMENT,lambda:m.set_preparation(a,bad,execution_ledger=L))
    m.set_preparation(a,request(),execution_ledger=L)
    assert not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)


def test_start_requires_exact_ticket_result_ledger_and_one_reserved_envelope():
    """Unrelated identities cannot start and no second B can join running work."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared()
    other=ExecutionLedger()
    expect(E.INVALID_OBSERVATION,lambda:m._start_operation(t,b,other))
    other_b=m.reserve_result(t,16,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m._start_operation(t,b,L))
    m.release_result(other_b,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m._start_operation(t,other_b,L))
    assert m._start_operation(t,b,L) is req
    expect(E.INVALID_OBSERVATION,lambda:m._start_operation(t,b,L))
    expect(E.RESOURCE_BUSY,lambda:m.reserve_result(t,1,execution_ledger=L))
    print('MANAGED_BODY_COMPLETE')
    """)


def test_running_worker_blocks_all_release_paths_until_actual_completion():
    """A waiting caller cannot refund envelopes or clear the physical gate."""
    run("""
    from threading import Event,Thread
    L,x,actual,c,r,req,a,t,b=prepared()
    started,finish=Event(),Event()
    failures=[]
    def worker():
        try:
            assert m._start_operation(t,b,L) is req
            started.set()
            assert finish.wait(5)
            m.set_result(b,7,execution_ledger=L)
            m._complete_operation(t,L,known=True)
        except BaseException as error:
            failures.append(error)
    thread=Thread(target=worker)
    thread.start()
    assert started.wait(5)
    before=m.capacity_snapshot(execution_ledger=L)
    for action in (
        lambda:m.release_result(b,execution_ledger=L),
        lambda:m.release_ticket(t,execution_ledger=L),
        lambda:m.release_preparation(a,execution_ledger=L),
        lambda:m.release_root(r,execution_ledger=L),
        lambda:m.abandon_root(r,execution_ledger=L),
        lambda:m.detach_terminal(c,execution_ledger=L),
        lambda:m.dispose_execution(x,execution_ledger=L),
    ):
        expect(E.RESOURCE_BUSY,action)
    assert m.capacity_snapshot(execution_ledger=L)==before
    finish.set();thread.join(5)
    assert not thread.is_alive() and failures==[]
    assert m.read_result(b,execution_ledger=L)==7
    m.release_result(b,execution_ledger=L)
    m.release_ticket(t,execution_ledger=L)
    m.release_preparation(a,execution_ledger=L)
    assert m.capacity_snapshot(execution_ledger=L)['AB']==0
    assert m.capacity_snapshot(execution_ledger=L)['BB']==0
    print('MANAGED_BODY_COMPLETE')
    """)


def test_typed_result_is_private_until_complete_and_complete_requires_population():
    """Starting is not completion, and a reserved empty envelope is not success."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared()
    expect(E.INVALID_OBSERVATION,lambda:m.set_result(b,7,execution_ledger=L))
    m._start_operation(t,b,L)
    expect(E.INVALID_OBSERVATION,lambda:m._complete_operation(t,L,known=True))
    expect(E.RESOURCE_BUSY,lambda:m.read_result(b,execution_ledger=L))
    for value in (True,0,None,b'7'):
        expect(E.INVALID_OBSERVATION,lambda:m.set_result(b,value,execution_ledger=L))
    m.set_result(b,7,execution_ledger=L)
    expect(E.RESOURCE_BUSY,lambda:m.read_result(b,execution_ledger=L))
    m._complete_operation(t,L,known=True)
    assert m.read_result(b,execution_ledger=L)==7
    expect(E.INVALID_OBSERVATION,lambda:m._complete_operation(t,L,known=True))
    expect(E.INVALID_OBSERVATION,lambda:m.set_result(b,8,execution_ledger=L))
    print('MANAGED_BODY_COMPLETE')
    """)


def test_optional_absence_is_populated_typed_result_not_unset():
    """None must complete E28 exactly once without masquerading as empty storage."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared('E28')
    m._start_operation(t,b,L)
    m.set_result(b,None,execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m.set_result(b,None,execution_ledger=L))
    m._complete_operation(t,L,known=True)
    assert m.read_result(b,execution_ledger=L) is None
    m.release_result(b,execution_ledger=L)
    m.release_ticket(t,execution_ledger=L)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_complete_outbox_identity_and_every_field_are_paid_and_validated():
    """Wrong event binding or late malformed replay cannot publish a typed row."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared('E28')
    m._start_operation(t,b,L)
    row=outbox()
    for name,value in (('event_id',b'other'),('replay_input',b'{}'),
                       ('envelope_evidence',b'wrong')):
        bad=object.__new__(O.OutboxRow)
        for field in fields(O.OutboxRow):
            object.__setattr__(bad,field.name,value if field.name==name else getattr(row,field.name))
        expect(E.INVALID_OBSERVATION,lambda:m.set_result(b,bad,execution_ledger=L))
    m.set_result(b,row,execution_ledger=L)
    m._complete_operation(t,L,known=True)
    assert m.read_result(b,execution_ledger=L) is row
    print('MANAGED_BODY_COMPLETE')
    """)


def test_outbox_full_backing_capacity_boundary_includes_all_fields():
    """Counting only replay or variable bytes would admit an undersized envelope."""
    run("""
    row=outbox()
    size=getsizeof(row)+sum(getsizeof(getattr(row,f.name)) for f in fields(O.OutboxRow))
    L,x,actual,c,r,req,a,t,b=prepared('E28',result_capacity=size-1)
    m._start_operation(t,b,L)
    expect(E.CAPACITY_EXCEEDED,lambda:m.set_result(b,row,execution_ledger=L))
    expect(E.INVALID_OBSERVATION,lambda:m._complete_operation(t,L,known=True))
    assert m.capacity_snapshot(execution_ledger=L)['BB']==size-1
    m._complete_operation(t,L,known=False)
    assert L.uncertainty.present
    expect(E.RESOURCE_BUSY,lambda:m.release_result(b,execution_ledger=L),True)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_hold_does_not_clear_running_and_late_completion_never_becomes_success():
    """A cancelled waiter cannot refund work or convert late success to usable data."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared()
    m._start_operation(t,b,L)
    before=m.capacity_snapshot(execution_ledger=L)
    m._hold_operation(t,L)
    assert L.uncertainty.present
    p=m._ticket(t,L)
    assert p.operation['running'] and p.blocked_root
    expect(E.INVALID_OBSERVATION,lambda:m.set_result(b,7,execution_ledger=L),True)
    for action in (lambda:m.release_result(b,execution_ledger=L),
                   lambda:m.release_ticket(t,execution_ledger=L)):
        expect(E.RESOURCE_BUSY,action,True)
    m._complete_operation(t,L,known=True)
    assert not p.operation['running']
    expect(E.RESOURCE_BUSY,lambda:m.read_result(b,execution_ledger=L),True)
    expect(E.RESOURCE_BUSY,lambda:m.release_result(b,execution_ledger=L),True)
    expect(E.RESOURCE_BUSY,lambda:m.release_ticket(t,execution_ledger=L),True)
    assert m.capacity_snapshot(execution_ledger=L)==before
    print('MANAGED_BODY_COMPLETE')
    """)


def test_unknown_completion_holds_backing_and_cleanup_even_after_worker_stops():
    """A stopped driver is not a root/close receipt and cannot refund UNKNOWN."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared()
    m._start_operation(t,b,L)
    m.set_result(b,7,execution_ledger=L)
    before=m.capacity_snapshot(execution_ledger=L)
    m._complete_operation(t,L,known=False)
    assert L.uncertainty.present and not m._ticket(t,L).operation['running']
    m.retire(c,execution_ledger=L)
    for action in (lambda:m.prepare_cleanup(c,execution_ledger=L),
                   lambda:m.abandon_root(r,execution_ledger=L),
                   lambda:m.release_preparation(a,execution_ledger=L),
                   lambda:m.release_result(b,execution_ledger=L),
                   lambda:m.detach_terminal(c,execution_ledger=L)):
        expect(E.RESOURCE_BUSY,action,True)
    assert m.capacity_snapshot(execution_ledger=L)==before
    print('MANAGED_BODY_COMPLETE')
    """)


def test_unknown_ledger_failure_keeps_running_domain_stopped_and_primary_exact():
    """Secondary uncertainty bookkeeping cannot manufacture completed/refunded work."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared()
    m._start_operation(t,b,L)
    primary=RuntimeError('safe sentinel')
    original=ExecutionLedger.note_incident
    def fail(self,code):
        raise primary
    ExecutionLedger.note_incident=fail
    try:
        m._hold_operation(t,L)
    except BaseException as error:
        assert error is primary
    else:
        raise AssertionError('expected primary')
    finally:
        ExecutionLedger.note_incident=original
    assert old._domain.stopped and m._ticket(t,L).operation['running']
    assert m.capacity_snapshot(execution_ledger=L)['D']==1
    expect(E.RESOURCE_BUSY,lambda:m.release_result(b,execution_ledger=L))
    print('MANAGED_BODY_COMPLETE')
    """)


def test_legacy_bytes_admission_and_release_behavior_stays_compatible():
    """The typed extension must not force existing byte-envelope controls to execute."""
    run("""
    L,x,actual,c=setup_physical();r=active_root(c,L)
    a=m.reserve_preparation(x,8,execution_ledger=L)
    m.set_preparation(a,b'intent',execution_ledger=L)
    t=m.admit(r,a,execution_ledger=L)
    b=m.reserve_result(t,8,execution_ledger=L)
    m.set_result(b,b'result',execution_ledger=L)
    m.release_result(b,execution_ledger=L)
    m.release_ticket(t,execution_ledger=L)
    m.release_preparation(a,execution_ledger=L)
    assert not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """)


def test_request_graph_identity_is_preserved_through_result_validation():
    """Result checks must not replace the parameters actually consumed by execution."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared('E28')
    parameters,context,value=req.parameters,req.context,req.parameters[0]
    assert m._start_operation(t,b,L) is req
    m.set_result(b,outbox(),execution_ledger=L)
    m._complete_operation(t,L,known=True)
    assert req.parameters is parameters and req.context is context
    assert req.parameters[0] is value
    print('MANAGED_BODY_COMPLETE')
    """)


def test_owned_outbox_capacity_includes_uuid_integer_storage():
    """Charging only the UUID carrier would admit a one-byte short full graph."""
    for short in (True, False):
        run(
            "short="
            + repr(short)
            + "\n"
            + textwrap.dedent("""
        from uuid import UUID
        base=outbox()
        values={f.name:getattr(base,f.name) for f in fields(O.OutboxRow)}
        values.update(state='publishing',token=UUID(int=2**127),
            ownership_revision=1,lease_until=base.created_at,intent_id=UUID(int=2**127+1))
        row=O.OutboxRow(**values)
        size=getsizeof(row)+sum(getsizeof(getattr(row,f.name)) for f in fields(O.OutboxRow))
        size+=getsizeof(row.token.int)+getsizeof(row.intent_id.int)
        L,x,actual,c,r,req,a,t,b=prepared('E28',result_capacity=size-int(short))
        m._start_operation(t,b,L)
        if short:
            expect(E.CAPACITY_EXCEEDED,lambda:m.set_result(b,row,execution_ledger=L))
        else:
            m.set_result(b,row,execution_ledger=L)
            m._complete_operation(t,L,known=True)
            assert m.read_result(b,execution_ledger=L) is row
        print('MANAGED_BODY_COMPLETE')
        """)
        )


def test_retained_outbox_rejects_coercible_uuid_and_timezone_before_callbacks():
    """Validating a normalized copy must not retain an unchecked original graph."""
    run("""
    from datetime import tzinfo
    from uuid import UUID
    calls=[]
    class UserZone(tzinfo):
        def utcoffset(self,dt):
            calls.append('offset')
            raise RuntimeError('must not invoke user timezone')
    base=outbox()
    values={f.name:getattr(base,f.name) for f in fields(O.OutboxRow)}
    values.update(state='publishing',token=UUID(int=1),ownership_revision=1,
        lease_until=base.created_at,intent_id=UUID(int=2))
    good=O.OutboxRow(**values)
    L,x,actual,c,r,req,a,t,b=prepared('E28')
    m._start_operation(t,b,L)
    for name,value in (('token',str(good.token)),
                       ('created_at',datetime(2026,1,1,tzinfo=UserZone()))):
        bad=object.__new__(O.OutboxRow)
        for field in fields(O.OutboxRow):
            object.__setattr__(bad,field.name,value if field.name==name else getattr(good,field.name))
        expect(E.INVALID_OBSERVATION,lambda:m.set_result(b,bad,execution_ledger=L))
    assert calls==[] and not old._domain.stopped
    m.set_result(b,good,execution_ledger=L)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_completion_requires_exact_boolean():
    """Truthy objects cannot authorize a successful completion transition."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared()
    m._start_operation(t,b,L)
    m.set_result(b,7,execution_ledger=L)
    for known in (1,0,None,'yes'):
        expect(E.LOCAL_INVALID_ARGUMENT,lambda:m._complete_operation(t,L,known=known))
    assert m._ticket(t,L).operation['running']
    m._complete_operation(t,L,known=True)
    assert m.read_result(b,execution_ledger=L)==7
    print('MANAGED_BODY_COMPLETE')
    """)


def test_completion_union_failure_keeps_held_backing_after_actual_stop():
    """Failed uncertainty publication cannot refund held data or replace primary."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared()
    m._start_operation(t,b,L)
    before=m.capacity_snapshot(execution_ledger=L)
    primary=RuntimeError('safe completion sentinel')
    original=ExecutionLedger.note_incident
    def fail(self,code):
        raise primary
    ExecutionLedger.note_incident=fail
    try:
        m._complete_operation(t,L,known=False)
    except BaseException as error:
        assert error is primary
    else:
        raise AssertionError('expected primary')
    finally:
        ExecutionLedger.note_incident=original
    p=m._ticket(t,L)
    assert old._domain.stopped and not p.operation['running'] and p.blocked_root
    assert p.operation['state']=='HELD'
    after=m.capacity_snapshot(execution_ledger=L)
    assert after==dict(before,D=before['D']+1)
    expect(E.RESOURCE_BUSY,lambda:m.release_result(b,execution_ledger=L))
    expect(E.RESOURCE_BUSY,lambda:m.release_ticket(t,execution_ledger=L))
    print('MANAGED_BODY_COMPLETE')
    """)


def test_held_ticket_no_longer_validates_for_an_operation():
    """UNKNOWN cannot leave the old public ticket-validation path usable."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared()
    m._start_operation(t,b,L)
    m._hold_operation(t,L)
    expect(E.PROFILE_REJECTED,lambda:m.validate_ticket(t,execution_ledger=L),True)
    print('MANAGED_BODY_COMPLETE')
    """)


def test_unexpected_result_validation_failure_preserves_primary_and_paid_graph():
    """Raw validator failures must escape unchanged, without success or refund."""
    run("""
    L,x,actual,c,r,req,a,t,b=prepared('E28')
    m._start_operation(t,b,L)
    row=outbox()
    before=m.capacity_snapshot(execution_ledger=L)
    primary=RuntimeError('safe validation sentinel')
    def fail(values):
        raise primary
    m._decode_outbox_raw=fail
    try:
        m.set_result(b,row,execution_ledger=L)
    except BaseException as error:
        assert error is primary
    else:
        raise AssertionError('expected primary')
    assert old._domain.stopped
    assert m.capacity_snapshot(execution_ledger=L)==dict(before,D=before['D']+1)
    expect(E.RESOURCE_BUSY,lambda:m.read_result(b,execution_ledger=L))
    expect(E.RESOURCE_BUSY,lambda:m.release_result(b,execution_ledger=L))
    print('MANAGED_BODY_COMPLETE')
    """)


def test_uuid_public_safety_metadata_cannot_hide_mutable_uncharged_backing():
    """Exact UUID class alone must not admit its unchecked public is_safe field."""
    run("""
    from uuid import UUID
    base=outbox()
    values={f.name:getattr(base,f.name) for f in fields(O.OutboxRow)}
    values.update(state='claimed',token=UUID(int=1,is_safe=bytearray(100000)),
        ownership_revision=1,lease_until=base.created_at)
    row=O.OutboxRow(**values)
    L,x,actual,c,r,req,a,t,b=prepared('E28')
    m._start_operation(t,b,L)
    before=m.capacity_snapshot(execution_ledger=L)
    expect(E.INVALID_OBSERVATION,lambda:m.set_result(b,row,execution_ledger=L))
    assert m.capacity_snapshot(execution_ledger=L)==before
    assert not old._domain.stopped
    expect(E.RESOURCE_BUSY,lambda:m.read_result(b,execution_ledger=L))
    print('MANAGED_BODY_COMPLETE')
    """)


def test_uuid_public_integer_backing_rejects_subclasses_before_size_callbacks():
    """A UUID created with an int subclass must not invoke caller __sizeof__."""
    run("""
    from uuid import UUID
    calls=[]
    class UserInt(int):
        def __sizeof__(self):
            calls.append('size')
            return int.__sizeof__(self)
    base=outbox()
    values={f.name:getattr(base,f.name) for f in fields(O.OutboxRow)}
    values.update(state='publishing',token=UUID(int=1),ownership_revision=1,
        lease_until=base.created_at,intent_id=UUID(int=UserInt(2)))
    row=O.OutboxRow(**values)
    assert calls==[]
    L,x,actual,c,r,req,a,t,b=prepared('E28')
    m._start_operation(t,b,L)
    expect(E.INVALID_OBSERVATION,lambda:m.set_result(b,row,execution_ledger=L))
    assert calls==[] and not old._domain.stopped
    print('MANAGED_BODY_COMPLETE')
    """)
