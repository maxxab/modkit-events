"""Complete bounded row validation using canonical statement metadata."""
from collections.abc import Sequence
from uuid import UUID
from hashlib import sha256
from dataclasses import fields, dataclass
from .errors import _observation_boundary, _reject_validation
from .catalog import (get_statement, WireType, ColumnSpec, CardinalityKind, RecordKind,
                      _validate_column_spec)
from .bindings import (_scalar, _scalar_raw, _reject_scalar, _integer, _identifier, _bytes, _constraint,
                       FrozenRequest, validate_event_replay, canonical_event, _snapshot_sequence,
                       _integer_raw, _identifier_raw, _decode_utf8,
                       _validate_event_replay_raw, _canonical_event_raw, _freeze_parameters)
from . import observations as O
# Deliberate private dependency: schema owns the sole accepted code carriers.
from .transitions import (_WORK_HISTORY_CODES, _PUBLICATION_HISTORY_CODES,
                          _ATTEMPT_OUTCOME_CODES)


def _wire_scalar_core(value, wire_type, nullable, *, _reject=None):
    if wire_type is WireType.UUID and type(value) is str:
        if _reject is not None and (
            len(value) != 36
            or any(
                char != "-"
                if index in (8, 13, 18, 23)
                else char not in "0123456789abcdef"
                for index, char in enumerate(value)
            )
        ):
            _reject_scalar(_reject)
        parsed = UUID(value)
        if str(parsed) != value:
            _reject_scalar(_reject)
        value = parsed
    elif wire_type is WireType.XID8 and type(value) is str:
        if (
            not 1 <= len(value) <= 20
            or not value.isascii()
            or not value.isdigit()
            or value[0] == "0"
        ):
            _reject_scalar(_reject)
        value = int(value)
    return (_scalar if _reject is None else _scalar_raw)(value, wire_type, nullable)


@_observation_boundary
def _wire_scalar(value, wire_type, nullable):
    return _wire_scalar_core(value, wire_type, nullable)


def _wire_scalar_raw(value, wire_type, nullable):
    """Selected raw row scalar conversion without a public sanitizer."""
    if type(nullable) is not bool:
        _reject_validation()
    return _wire_scalar_core(value, wire_type, nullable, _reject=_reject_validation)


def _decode_columns_core(columns, values, *, _reject=None):
    if (
        _reject is not None
        and columns is not get_statement("E14").result.columns
        and columns is not get_statement("E28").result.columns
    ):
        _reject_scalar(_reject)
    if (
        type(columns) is not tuple
        or len(columns) > 256
        or any(type(c) is not ColumnSpec for c in columns)
    ):
        _reject_scalar(_reject)
    if _reject is not None and type(values) is not tuple:
        _reject_scalar(_reject)
    values = (
        _snapshot_sequence(values, len(columns))
        if _reject is None
        else _snapshot_sequence(values, len(columns), _reject=_reject)
    )
    if len(values) != len(columns):
        _reject_scalar(_reject)
    for column in columns:
        if _reject is None:
            column.__post_init__()
        else:
            _validate_column_spec(column, _reject=_reject)
    return tuple(
        (_wire_scalar if _reject is None else _wire_scalar_raw)(
            value, column.wire_type, column.nullable
        )
        for column, value in zip(columns, values)
    )


@_observation_boundary
def _decode_columns(columns, values):
    return _decode_columns_core(columns, values)


def _decode_columns_raw(columns, values):
    """Decode only canonical E14/E28 column tuples without a sanitizer."""
    return _decode_columns_core(columns, values, _reject=_reject_validation)


def _bounded_rows_core(rows, maximum, *, _reject=None):
    (_integer if _reject is None else _integer_raw)(maximum, 0, 4096)
    if _reject is not None and (type(rows) is not tuple or len(rows) > maximum):
        _reject_scalar(_reject)
    result = []
    for index, row in enumerate(rows):
        if index >= maximum:
            _reject_scalar(_reject)
        if _reject is not None and type(row) is not tuple:
            _reject_scalar(_reject)
        result.append(
            _snapshot_sequence(row, 256)
            if _reject is None
            else _snapshot_sequence(row, 256, _reject=_reject)
        )
    return tuple(result)


@_observation_boundary
def _bounded_rows(rows, maximum):
    return _bounded_rows_core(rows, maximum)


def _request_core(request, event=False, *, _reject=None):
    if type(request) is not FrozenRequest:
        _reject_scalar(_reject)
    if _reject is None:
        request.__post_init__()
    else:
        parameters = _freeze_parameters(
            request.statement, request.parameters, request.context, _reject=_reject
        )
        object.__setattr__(request, "parameters", parameters)
    if event or request.statement.key.startswith("E"):
        if request.statement is not get_statement(request.statement.key):
            _reject_scalar(_reject)
    return dict(zip((s.name for s in request.statement.parameters), request.parameters))


def _request(request, event=False):
    return _request_core(request, event)


def _request_raw(request):
    """Revalidate selected E14/E28 requests without a public boundary."""
    return _request_core(request, event=True, _reject=_reject_validation)


def _maximum(request,p):
    c=request.statement.result.cardinality
    if c in (CardinalityKind.EXACT_ONE,CardinalityKind.OPTIONAL_ONE):return 1
    if c is CardinalityKind.LIMIT:return p['limit']
    if c is CardinalityKind.FIND_TWO:return 2
    if c is CardinalityKind.FIND_THREE:return 3
    if c is CardinalityKind.SCAN:return p['limit']+1
    if c is CardinalityKind.READINESS:return 1 if p['required_profile']=='events' else 2
    raise ValueError


def _fetch_core(request, rows, p, *, _reject=None):
    result = (
        _bounded_rows(rows, _maximum(request, p))
        if _reject is None
        else _bounded_rows_core(rows, _maximum(request, p), _reject=_reject)
    )
    if request.statement.result.cardinality in (
        CardinalityKind.EXACT_ONE,
        CardinalityKind.READINESS,
    ) and len(result) != _maximum(request, p):
        _reject_scalar(_reject)
    return tuple(
        (_decode_columns if _reject is None else _decode_columns_raw)(
            request.statement.result.columns, row
        )
        for row in result
    )


def _fetch(request, rows, p):
    return _fetch_core(request, rows, p)


@_observation_boundary
def decode_work_observation(columns,/):
    specs=get_statement('E15').result.columns
    values=_decode_columns(specs,columns);data=dict(zip((c.name for c in specs),values))
    present=data.pop('resolution_present');resolution={}
    for name in tuple(data):
        if name.startswith('resolution_record_'):resolution[name[len('resolution_record_'):]]=data.pop(name)
    if present:
        data['resolution']=O.ResolutionObservation(**resolution)
    else:
        if any(v is not None for v in resolution.values()):raise ValueError
        data['resolution']=None
    return O.WorkObservation(**data)


_RECORD_KEYS={O.AdmissionRow:'E03',O.GuardRow:'E08',O.SubscriptionRow:'E18',O.OutboxRow:'E28',O.WorkHistoryRow:'E19',O.DeliveryRow:'E20',O.PublicationRow:'E29',O.AttemptRow:'E21',O.SettlementObservation:'E32',O.RepairObservation:'E27',O.SchemaStatus:'E33'}
_RECORD_CLASSES={RecordKind.ADMISSION:O.AdmissionRow,RecordKind.GUARD:O.GuardRow,RecordKind.SUBSCRIPTION:O.SubscriptionRow,RecordKind.OUTBOX:O.OutboxRow,RecordKind.WORK_HISTORY:O.WorkHistoryRow,RecordKind.DELIVERY:O.DeliveryRow,RecordKind.PUBLICATION:O.PublicationRow,RecordKind.ATTEMPT:O.AttemptRow,RecordKind.RESOLUTION:O.ResolutionObservation,RecordKind.SETTLEMENT:O.SettlementObservation,RecordKind.REPAIR:O.RepairObservation,RecordKind.SCHEMA_STATUS:O.SchemaStatus}


@dataclass(slots=True)
class _OutboxDraft:
    event_id: object
    canonical_version: object
    envelope_evidence: object
    replay_input: object
    state: object
    token: object
    ownership_revision: object
    lease_until: object
    intent_id: object
    receipt: object
    outcome_evidence: object
    created_at: object
    updated_at: object


def _validate_record_common(record, *, _reject=None):
    if _reject is not None and type(record) is not _OutboxDraft:
        _reject_scalar(_reject)
    if hasattr(record, "history_id"):
        _integer(record.history_id, 1, 2**63 - 1)
    if hasattr(record, "ownership_revision"):
        (_integer if _reject is None else _integer_raw)(
            record.ownership_revision, 0, 2**63 - 1
        )
    if hasattr(record, "cycle"):
        _integer(record.cycle, 1, 1)
    if hasattr(record, "attempt"):
        _integer(
            record.attempt,
            1 if type(record) in (O.AttemptRow, O.SettlementObservation) else 0,
            1000,
        )
    for name in (
        "subscription_id",
        "consumer_group",
        "event_id",
        "effect_id",
        "provider_key_reference",
    ):
        if hasattr(record, name) and getattr(record, name) is not None:
            if _reject is None:
                _identifier(getattr(record, name).decode("utf8"))
            else:
                _identifier_raw(_decode_utf8(getattr(record, name), _reject=_reject))
    if hasattr(record, "reason"):
        from .catalog import ConstraintId

        _constraint(record.reason, ConstraintId.REASON)
    if (
        hasattr(record, "receipt")
        and record.receipt is not None
        and len(record.receipt) > 4096
    ):
        _reject_scalar(_reject)


def _validate_outbox_fields(record, *, _reject=None):
    if _reject is not None and type(record) is not _OutboxDraft:
        _reject_scalar(_reject)
    if record.canonical_version != 1:
        _reject_scalar(_reject)
    event = (validate_event_replay if _reject is None else _validate_event_replay_raw)(
        record.replay_input
    )
    if (
        record.event_id != event.event_id.encode("utf8")
        or record.envelope_evidence
        != (canonical_event if _reject is None else _canonical_event_raw)(event).content
    ):
        _reject_scalar(_reject)
    if record.state not in (
        "pending",
        "claimed",
        "publishing",
        "published",
        "rejected",
        "held",
    ):
        _reject_scalar(_reject)
    owned = record.state in ("claimed", "publishing")
    if owned:
        (_integer if _reject is None else _integer_raw)(
            record.ownership_revision, 1, 2**63 - 1
        )
    if owned != (record.token is not None) or owned != (record.lease_until is not None):
        _reject_scalar(_reject)
    if record.state in ("pending", "claimed") and record.intent_id is not None:
        _reject_scalar(_reject)
    if (
        record.state in ("publishing", "published", "rejected", "held")
        and record.intent_id is None
    ):
        _reject_scalar(_reject)


def _decode_outbox_raw(values):
    """Validate a selected Outbox draft before allocating the public row."""
    columns = get_statement("E28").result.columns
    decoded = _decode_columns_raw(columns, values)
    draft = _OutboxDraft(*decoded)
    _validate_record_common(draft, _reject=_reject_validation)
    _validate_outbox_fields(draft, _reject=_reject_validation)
    record = object.__new__(O.OutboxRow)
    for name in _OutboxDraft.__slots__:
        object.__setattr__(record, name, getattr(draft, name))
    return record


def _validate_record(record):
    key=_RECORD_KEYS.get(type(record))
    if key is None:raise ValueError
    specs=get_statement(key).result.columns
    values=_decode_columns(specs,tuple(getattr(record,c.name) for c in specs))
    for column,value in zip(specs,values):object.__setattr__(record,column.name,value)
    _validate_record_common(record)
    if type(record) is O.GuardRow:
        _integer(record.root_xid,1,2**64-1);_integer(record.ownership_revision,1,2**63-1);_integer(record.expected_attempt,1,1000)
        certificate=(record.final_fence_at,record.terminal_state,record.result_digest)
        if record.satisfied:
            if any(v is None for v in certificate) or record.terminal_state!='succeeded' or len(record.result_digest)!=32:raise ValueError
        elif any(v is not None for v in certificate):raise ValueError
    elif type(record) is O.SubscriptionRow:
        _integer(record.capacity,1,2147483647);_integer(record.nonterminal_count,0,record.capacity)
    elif type(record) is O.OutboxRow:
        _validate_outbox_fields(record)
    elif type(record) is O.WorkHistoryRow:
        code=record.transition
        if type(code) is not str or code not in _WORK_HISTORY_CODES:raise ValueError
        intake=code in ('intake_runnable','intake_blocked')
        owned=code in ('claim','renew','dispatch')
        if owned!=(record.token is not None):raise ValueError
        _integer(record.ownership_revision,0 if intake else 1,0 if intake else 2**63-1)
        if intake:bounds=(0,0)
        elif code in ('claim','defer','recover_claim'):bounds=(0,999)
        elif code in ('failure_retry','reconcile_safe_retry'):bounds=(1,999)
        elif code in ('renew','cancel_predispatch','recover_expired_predispatch'):bounds=(0,1000)
        else:bounds=(1,1000)
        _integer(record.attempt,*bounds)
        submitted_reason=code in ('failure_terminal','failure_cancelled','failure_retry','cancel_predispatch','cancel_running','cancel_held','hold_uncertain')
        if not submitted_reason:
            expected_reason='attempts_exhausted' if code=='recover_exhausted_predispatch' else code
            if record.reason!=expected_reason:raise ValueError
        submitted_evidence=code.startswith(('failure_','reconcile_')) or code=='hold_uncertain'
        if not submitted_evidence and record.evidence!=b'':raise ValueError
    elif type(record) is O.PublicationRow:
        code=record.status
        if type(code) is not str or code not in _PUBLICATION_HISTORY_CODES:raise ValueError
        repair=code in ('repair_published','repair_rejected')
        if repair!=(record.operation_id is not None):raise ValueError
        no_intent=code in ('enqueue','claim_publication','recover_publication_preintent')
        if no_intent and record.intent_id is not None:raise ValueError
        if not no_intent and code!='renew_publication' and record.intent_id is None:raise ValueError
        settlement=repair or code in ('publication_confirmed','publication_rejected','publication_uncertain')
        if not settlement and (record.receipt is not None or record.evidence!=b''):raise ValueError
        if not repair and record.binding!=b'':raise ValueError
    elif type(record) is O.AttemptRow:
        if type(record.outcome) is not str or record.outcome not in _ATTEMPT_OUTCOME_CODES:raise ValueError
        # Other outcomes have multiple possible producers; do not invent provenance.
        if record.outcome in ('dispatched','cancelled_unresolved') and record.evidence!=b'':raise ValueError
    elif type(record) in (O.SettlementObservation,O.RepairObservation):
        _integer(record.expected_revision,0,2**63-1);_integer(record.resulting_revision,1,2**63-1)
        if record.resulting_revision<=record.expected_revision:raise ValueError
        if type(record) is O.RepairObservation and record.status not in ('published','rejected'):raise ValueError
    elif type(record) is O.SchemaStatus:
        if record.component not in ('events','workers') or len(record.migration_digest)!=32:raise ValueError
        _integer(record.version,1,2147483647)
        for value in (record.catalog_contract_id,record.scope_format_id,record.intent_format_id):_identifier(value)


def _validate_inbox(record,present):
    names=('inbox_subscription_id','original_event_id','envelope_evidence','original_replay_input')
    if record.kind!='inbox':
        if present or any(getattr(record,n) is not None for n in names):raise ValueError
        return
    if not present:raise ValueError
    for name in names:object.__setattr__(record,name,_bytes(getattr(record,name)))
    _identifier(record.inbox_subscription_id.decode('utf8'));_identifier(record.original_event_id.decode('utf8'))
    event=validate_event_replay(record.original_replay_input)
    if record.subscription_id!=record.inbox_subscription_id or event.event_id.encode('utf8')!=record.original_event_id or canonical_event(event).content!=record.envelope_evidence or record.semantic_input!=record.envelope_evidence:raise ValueError
    if canonical_event(validate_event_replay(record.replay_input)).content!=record.envelope_evidence:raise ValueError


def _record(kind,specs,row):
    if kind is RecordKind.WORK:return decode_work_observation(row)
    if kind in (RecordKind.INBOX,RecordKind.INBOX_CANDIDATE):
        width=len(get_statement('E15').result.columns);work=decode_work_observation(row[:width])
        data={f.name:getattr(work,f.name) for f in fields(O.WorkObservation)}
        data.update(zip((c.name for c in specs[width:]),row[width:]))
        return (O.InboxObservation if kind is RecordKind.INBOX else O.InboxCandidate)(**data)
    if kind in _RECORD_CLASSES:return _RECORD_CLASSES[kind](**dict(zip((c.name for c in specs),row)))
    return _scalar_record(kind, row)


def _scalar_record(kind, row, *, _reject=None):
    if _reject is not None and kind is not RecordKind.XID:
        _reject_scalar(_reject)
    if len(row) != 1:
        _reject_scalar(_reject)
    value = row[0]
    if kind is RecordKind.UNIT and value is not True:
        _reject_scalar(_reject)
    if kind is RecordKind.ATTEMPT_NUMBER:
        _integer(value, 1, 1000)
    if kind is RecordKind.STATE and value not in (
        "queued",
        "claimed",
        "running",
        "retry_waiting",
        "succeeded",
        "failed",
        "expired",
        "cancelled",
        "blocked_schema",
        "held",
    ):
        _reject_scalar(_reject)
    return value


def _key_path(work,p):
    if p.get('idempotency_key') is None or work.idempotency_key is None:return False
    return (work.kind==p['kind'] and work.subscription_id==p['subscription_id'] and work.namespace==p['namespace'] and work.command_type==p['command_type'] and sha256(work.scope_evidence).digest()==sha256(p['scope_evidence']).digest() and sha256(work.idempotency_key).digest()==sha256(p['idempotency_key']).digest())


def _unique_order(items,key,after=None):
    prior=after
    for item in items:
        current=key(item)
        if prior is not None and current<=prior:raise ValueError
        prior=current


def _couple_event_id(p, items, *, _reject=None):
    if any(item.event_id != p["event_id"] for item in items):
        _reject_scalar(_reject)


def _couple(request,p,items):
    key=request.statement.key
    if key=='E03' and items[0].inserted and items[0].work_id!=p['work_id']:raise ValueError
    if key=='E06' and items[0]!=p['expected_attempt']+1:raise ValueError
    if key in ('E08','E09'):
        for item in items:
            if item.satisfied:raise ValueError
            if any(getattr(item,n)!=p[n] for n in ('work_id','token','ownership_revision','cycle','expected_attempt')):raise ValueError
    if key in ('E15','E19','E20','E21'):
        if any(item.work_id!=p['work_id'] for item in items):raise ValueError
    if key=='E16':
        if any(item.inbox_subscription_id!=p['subscription_id'] or item.original_event_id!=p['event_id'] for item in items):raise ValueError
    if key in ('E17','E34'):
        _unique_order(items,lambda item:item.work_id)
        for item in items:
            direct=item.work_id==p['work_id'];scoped=_key_path(item,p)
            event=(key=='E34' and item.kind=='inbox' and item.inbox_subscription_id==p['subscription_id'] and sha256(item.original_event_id).digest()==sha256(p['original_event_id']).digest())
            if not (direct or scoped or event):raise ValueError
    if key=='E18' and any(item.subscription_id!=p['subscription_id'] for item in items):raise ValueError
    if key in ('E19','E20','E29'):_unique_order(items,lambda item:item.history_id,p['after_id'])
    if key=='E21':_unique_order(items,lambda item:(item.cycle,item.attempt),(p['after_cycle'],p['after_attempt']))
    if key in ('E28','E29'):_couple_event_id(p,items)
    if key=='E30':
        if any(item.namespace!=p['namespace'] for item in items):raise ValueError
        after=None if p['after_created_at'] is None else (p['after_created_at'],p['after_work_id'])
        _unique_order(items,lambda item:(item.created_at,item.work_id),after)
    if key in ('E27','E31','E32'):
        item=items[0]
        for name,value in p.items():
            target='expected_revision' if key=='E32' and name=='ownership_revision' else 'attempt' if key=='E32' and name=='expected_attempt' else name
            if not hasattr(item,target) or getattr(item,target)!=value:raise ValueError
    if key=='E33':
        expected=('events',) if p['required_profile']=='events' else ('events','workers')
        if tuple(item.component for item in items)!=expected:raise ValueError


@_observation_boundary
def split_scan_rows(request,rows,/):
    p=_request(request);kind=request.statement.result.record
    if request.statement.result.cardinality is not CardinalityKind.SCAN or kind not in (RecordKind.WORK_SCAN,RecordKind.OUTBOX_SCAN,RecordKind.JOB_SCAN):raise ValueError
    if request.statement.key not in ('E04','E13','E22','E26','W05'):raise ValueError
    fetched=_fetch(request,rows,p)
    if not fetched:raise ValueError
    header=fetched[0]
    if header[0]!='header' or header[1] is None or header[3] is None or any(v is not None for v in header[4:]):raise ValueError
    visited=_integer(header[1],0,p['discovery_budget']);cursor=header[2];exhausted=header[3]
    if type(exhausted) is not bool:raise ValueError
    incoming=p['scan_after'];raw_items=fetched[1:]
    if len(raw_items)>p['limit'] or len(raw_items)>visited:raise ValueError
    if visited==0:
        if raw_items or cursor!=incoming:raise ValueError
    elif cursor is None or incoming is not None and cursor<=incoming:raise ValueError
    if exhausted and (visited>=p['discovery_budget'] or len(raw_items)>=p['limit']):raise ValueError
    if kind is RecordKind.OUTBOX_SCAN and cursor is not None and len(cursor)!=32:raise ValueError
    output=[];prior=incoming
    for row in raw_items:
        if row[0]!='item' or any(v is not None for v in row[1:4]):raise ValueError
        item_columns=row[4:]
        if kind in (RecordKind.WORK_SCAN,RecordKind.JOB_SCAN):
            work=decode_work_observation(item_columns[:len(get_statement('E15').result.columns)])
            expected_kind='job' if kind is RecordKind.JOB_SCAN else p['kind']
            if work.kind!=expected_kind or work.namespace!=p['namespace']:raise ValueError
            if request.statement.key in ('E04','W05'):
                if work.state!='claimed' or (work.command_type,work.runnable_version) not in tuple(zip(p['command_types'],p['schema_versions'])):raise ValueError
            elif work.state not in ('queued','expired','failed','cancelled','held'):raise ValueError
            current=work.work_id
        else:
            item=_record(RecordKind.OUTBOX,get_statement('E28').result.columns,item_columns)
            if request.statement.key=='E22' and item.state!='claimed':raise ValueError
            if request.statement.key=='E26' and item.state not in ('pending','held'):raise ValueError
            current=sha256(item.event_id).digest()
        if prior is not None and current<=prior or cursor is None or current>cursor:raise ValueError
        prior=current;output.append(item_columns)
    return O.ScanFrame(visited=visited,next_cursor=cursor,pass_exhausted=exhausted,item_columns=tuple(output))


@_observation_boundary
def decode_scan_page(request,rows,/,*,item_kind):
    if type(item_kind) is not RecordKind:raise ValueError
    expected={RecordKind.WORK_SCAN:RecordKind.WORK,RecordKind.OUTBOX_SCAN:RecordKind.OUTBOX}.get(request.statement.result.record)
    if item_kind is not expected:raise ValueError
    frame=split_scan_rows(request,rows)
    specs=get_statement('E15' if item_kind is RecordKind.WORK else 'E28').result.columns
    items=tuple(_record(item_kind,specs,row) for row in frame.item_columns)
    return O.ScanPage(items=items,visited=frame.visited,next_cursor=frame.next_cursor,pass_exhausted=frame.pass_exhausted)


@_observation_boundary
def _decode_event_rows_core(request,rows):
    p=_request(request,event=True);spec=request.statement.result
    if spec.cardinality is CardinalityKind.SCAN:
        kind={RecordKind.WORK_SCAN:RecordKind.WORK,RecordKind.OUTBOX_SCAN:RecordKind.OUTBOX}.get(spec.record)
        return decode_scan_page(request,rows,item_kind=kind)
    fetched=_fetch(request,rows,p)
    items=tuple(_record(spec.record,spec.columns,row) for row in fetched)
    _couple(request,p,items)
    return _finish_event_rows(spec, items)


def _finish_event_rows(spec, items):
    if spec.cardinality is CardinalityKind.EXACT_ONE:
        return items[0]
    if spec.cardinality is CardinalityKind.OPTIONAL_ONE:
        return items[0] if items else None
    return items


def _decode_event_rows_raw(request, rows):
    """Compose the selected E14/E28 row graph without public sanitizers."""
    p = _request_raw(request)
    spec = request.statement.result
    if request.statement is get_statement("E14"):
        if spec.record is not RecordKind.XID or spec.cardinality is not CardinalityKind.EXACT_ONE:
            _reject_validation()
    elif (
        request.statement is not get_statement("E28")
        or spec.record is not RecordKind.OUTBOX
        or spec.cardinality is not CardinalityKind.OPTIONAL_ONE
    ):
        _reject_validation()
    fetched = _fetch_core(request, rows, p, _reject=_reject_validation)
    if spec.record is RecordKind.OUTBOX:
        items = tuple(_decode_outbox_raw(row) for row in fetched)
        _couple_event_id(p, items, _reject=_reject_validation)
    else:
        items = tuple(
            _scalar_record(spec.record, row, _reject=_reject_validation) for row in fetched
        )
    return _finish_event_rows(spec, items)


def decode_event_rows(request,rows,/):
    result=_decode_event_rows_core(request,rows)
    if request.statement.key=='E33' and result!=request.context.readiness.components:
        from .errors import _fail,ErrorCode
        _fail(ErrorCode.SCHEMA_MISMATCH,unconfirmed=False)
    return result


def _decode_work_observation_raw(values, /):
    """Decode the complete fixed E15 prefix; no partial Work projections."""
    columns = get_statement("E15").result.columns
    if type(values) is not tuple or len(values) != 56:
        _reject_validation()
    values = tuple(
        _wire_scalar_raw(value, col.wire_type, col.nullable)
        for value, col in zip(values, columns)
    )
    data = dict(zip((col.name for col in columns), values))
    present = data.pop("resolution_present")
    resolution = {}
    for name in tuple(data):
        if name.startswith("resolution_record_"):
            resolution[name[len("resolution_record_") :]] = data.pop(name)
    if present:
        data["resolution"] = O._resolution_observation_raw(**resolution)
    else:
        if any(value is not None for value in resolution.values()):
            _reject_validation()
        data["resolution"] = None
    return O._work_observation_raw(**data)
