"""Bounded synchronous foundation controls; run by the inspected trapped runner."""


def test_codec_surface():
    assert B is not None, 'bindings source is not implemented'
    for name in ('canonical_json', 'parse_canonical_json', 'encode_mapping_replay',
                 'decode_mapping_replay', 'version_to_decimal', 'version_from_decimal',
                 'canonical_protected_binding', 'decode_protected_binding',
                 'validate_event_replay', 'canonical_event'):
        assert callable(getattr(B, name, None)), name


def test_json_types_and_golden_bytes():
    assert B is not None, 'bindings source is not implemented'
    assert B.canonical_json(None) == b'n'
    assert B.canonical_json(1) == b'i'+(1).to_bytes(8,'big')+b'1'
    assert B.canonical_json(-0.0) == b'd'+(9).to_bytes(8,'big')+b'-0x0.0p+0'
    assert B.canonical_json({'z': [1,True,None], 'a':'\0'}) == B.canonical_json({'a':'\0','z':(1,True,None)})
    value={'x':(1,1.0,-0.0,'é\0')}
    raw=B.canonical_json(value)
    assert B.canonical_json(B.parse_canonical_json(raw)) == raw
    assert B.canonical_json(1) != B.canonical_json(1.0)


def test_versions_and_replay():
    assert B is not None, 'bindings source is not implemented'
    for v in (1,2147483647,2147483648,2**13600-1):
        assert B.version_from_decimal(B.version_to_decimal(v)) == v
    for raw in (b'0',b'01',b'-1',b'1 '*3,b'9'*4097):
        rejects(lambda: B.version_from_decimal(raw))
    for v in (True,0,-1): rejects(lambda: B.version_to_decimal(v))
    original={'a':(-0.0,1.0,5e-324,1e308,'\0é')}
    replay=B.encode_mapping_replay(original)
    assert B.canonical_json(B.decode_mapping_replay(replay)) == B.canonical_json(original)
    for raw in (b'\xef\xbb\xbf{}', '{}'.encode('utf-16'), b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999999}', b'{"a":"\\ud800"}'):
        rejects(lambda: B.decode_mapping_replay(raw))
    assert B.canonical_json(B.decode_mapping_replay(b'{"a":1e0}')) == B.canonical_json({'a':1.0})


def test_depth_and_malformed_frames():
    assert B is not None, 'bindings source is not implemented'
    v=None
    for _ in range(32): v=[v]
    B.canonical_json(v)
    rejects(lambda:B.canonical_json([v]))
    for raw in (b'',b'i'+(2).to_bytes(8,'big')+b'01',b'njunk',b'a'+(999999).to_bytes(4,'big'),b's'+(1).to_bytes(8,'big')+b'\xff'):
        rejects(lambda:B.parse_canonical_json(raw))


def test_protected_material_roundtrip():
    assert B is not None and M is not None, 'foundation source is not implemented'
    m=M.ProtectedBindingInput(material_state=M.MaterialState.PRESENT,codec='c',key_version='k',expires_at=None,
        cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=b'cipher',reference=None,content_binding=b'bound',recovery_metadata={},projection_metadata={})
    ev=B.canonical_protected_binding(m)
    decoded=B.decode_protected_binding(ev.content)
    assert decoded.sidecar == b'cipher' and decoded.content_binding == b'bound'
    assert B.canonical_protected_binding(decoded) == ev
    assert B.validate_protected_binding(ev.content,m) == ev
    rejects(lambda:B.decode_protected_binding(ev.content+b'x'))
    rejects(lambda:M.ProtectedBindingInput(material_state=M.MaterialState.PRESENT,codec='c',key_version='k',expires_at=None,cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=None,reference=None,content_binding=b'bound',recovery_metadata={},projection_metadata={}))


def test_error_ambient_detachment():
    assert B is not None and E is not None, 'foundation source is not implemented'
    try:
        raise RuntimeError('sensitive ambient')
    except RuntimeError:
        try: B.version_from_decimal(b'0')
        except E.PersistenceError as exc:
            assert exc.__cause__ is None and exc.__context__ is None
            assert exc.__suppress_context__ is True
            assert exc.code is E.ErrorCode.LOCAL_INVALID_ARGUMENT
        else: assert False


def rejects(call):
    try: call()
    except E.PersistenceError: return
    assert False, 'expected sanitized rejection'


def test_identity_admission_and_intent():
    assert hasattr(M,'AdmissionInput'), 'AdmissionInput is not implemented'
    from modkit_events.persistence.scope import Scope,canonical_scope,encode_scope_fields
    from uuid import UUID
    from datetime import datetime,timezone
    scope=Scope('app',None,'owner\0');app,tenant,owner=encode_scope_fields(scope)
    se=M.ScopeEvidence(canonical_version=1,canonical=canonical_scope(scope),application=app,tenant=tenant,owner=owner)
    identity=M.WorkIdentity(work_id=UUID(int=1),kind=M.WorkKind.JOB,subscription_id=None,namespace='jobs',command_type='run',scope=se,idempotency_key='key')
    material=M.ProtectedBindingInput(material_state=M.MaterialState.ABSENT,codec=None,key_version=None,expires_at=None,cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=None,reference=None,content_binding=b'',recovery_metadata=b'',projection_metadata={})
    kw=dict(identity=identity,schema_version=2147483648,semantic_input=B.canonical_json({'a':1}),replay_input=B.encode_mapping_replay({'a':1}),protected_binding=B.canonical_protected_binding(material).content,replay_policy=M.ReplayPolicy.DISABLED,max_attempts=3,deadline=None,original_available_at=datetime(2026,1,1,tzinfo=timezone.utc))
    admission=M.AdmissionInput(**kw);evidence=B.canonical_intent(admission)
    assert evidence.content.startswith(b'MKPF\x01')
    identity2=M.WorkIdentity(work_id=UUID(int=2),kind=M.WorkKind.JOB,subscription_id=None,namespace='jobs',command_type='run',scope=se,idempotency_key='key')
    assert B.canonical_intent(M.AdmissionInput(**{**kw,'identity':identity2})) == evidence
    rejects(lambda:M.WorkIdentity(work_id=UUID(int=1),kind=M.WorkKind.INBOX,subscription_id=None,namespace='jobs',command_type='run',scope=se,idempotency_key='key'))
    rejects(lambda:M.AdmissionInput(**{**kw,'replay_input':b'{"a":2}'}))


def test_fence_cursor_capability_validation():
    assert hasattr(M,'Fence'), 'Fence is not implemented'
    from uuid import UUID
    from datetime import datetime,timezone
    args=dict(work_id=UUID(int=1),token=UUID(int=2),ownership_revision=1,cycle=1,expected_attempt=0)
    assert M.Fence(**args).expected_attempt==0
    rejects(lambda:M.Fence(**{**args,'cycle':0}))
    rejects(lambda:M.Fence(**{**args,'ownership_revision':True}))
    rejects(lambda:M.Capability(command_type='run',schema_version=2147483648))
    assert M.AttemptCursor(after_cycle=0,after_attempt=0).after_cycle==0
    assert M.WorkCursor(created_at=datetime(2026,1,1,tzinfo=timezone.utc),work_id=UUID(int=1)).work_id==UUID(int=1)


def test_observation_incident_sticky():
    assert O is not None,'observations source is not implemented'
    a=O.Uncertainty(present=False,categories=frozenset())
    b=O.Uncertainty(present=True,categories=frozenset({E.ErrorCode.OUTCOME_UNKNOWN}))
    assert O.join_uncertainty(a,b)==b
    assert O.join_uncertainty(b,a)==b
    rejects(lambda:O.Uncertainty(present=False,categories=b.categories))


def test_mapping_snapshot_reads_once():
    # A mapping may compute reads; admission must snapshot it once, not reread later.
    assert B is not None
    from collections.abc import Mapping
    class Once(Mapping):
        def __init__(self):self.reads=0
        def __iter__(self):return iter(('x',))
        def __len__(self):return 1
        def __getitem__(self,key):
            self.reads+=1
            if self.reads>1:raise RuntimeError('second read')
            return ['value']
    value=Once();assert B.decode_mapping_replay(B.encode_mapping_replay(value))['x']==('value',)
    assert value.reads==1


def test_large_version_and_float_exact_vectors():
    assert B is not None
    text=b'9'*4096
    assert B.version_to_decimal(B.version_from_decimal(text))==text
    rejects(lambda:B.version_to_decimal(10**4096))
    vectors=[(b'{"x":9007199254740993.0}',9007199254740992.0),(b'{"x":-1e-999999}',-0.0),(b'{"x":2.4703282292062327e-324}',0.0),(b'{"x":4.9406564584124654e-324}',5e-324)]
    for raw,expected in vectors:
        assert B.canonical_json(B.decode_mapping_replay(raw))==B.canonical_json({'x':expected})


def test_cancellation_identity():
    assert B is not None
    from collections.abc import Mapping
    failure=KeyboardInterrupt()
    class Cancelled(Mapping):
        def __len__(self):return 1
        def __iter__(self):raise failure
        def __getitem__(self,key):raise failure
    try:B.canonical_json(Cancelled())
    except KeyboardInterrupt as caught:assert caught is failure
    else:assert False


def test_replay_collection_budget_prevents_excess_decode():
    # Substituted counting control, not SQL/integration evidence: the excess
    # element must be rejected before its numeric conversion or allocation.
    count=0;original=B._json_number
    def counted(text):
        nonlocal count
        count+=1
        return original(text)
    B._json_number=counted
    try:
        rejects(lambda:B.decode_mapping_replay(b'{"x":['+b'0,'*65536+b'0]}'))
        assert count<=65536, 'excess collection member was decoded'
    finally:B._json_number=original


def _work_observation_fields():
    from modkit_events.persistence.scope import Scope,canonical_scope,encode_scope_fields
    from uuid import UUID
    from datetime import datetime,timezone
    now=datetime(2026,1,1,tzinfo=timezone.utc);scope=Scope('app');app,tenant,owner=encode_scope_fields(scope)
    se=M.ScopeEvidence(canonical_version=1,canonical=canonical_scope(scope),application=app,tenant=tenant,owner=owner)
    ident=M.WorkIdentity(work_id=UUID(int=1),kind=M.WorkKind.JOB,subscription_id=None,namespace='jobs',command_type='run',scope=se,idempotency_key=None)
    material=M.ProtectedBindingInput(material_state=M.MaterialState.ABSENT,codec=None,key_version=None,expires_at=None,cleanup_policy=M.CleanupPolicy.RETAIN,sidecar=None,reference=None,content_binding=b'',recovery_metadata=b'',projection_metadata={})
    admission=M.AdmissionInput(identity=ident,schema_version=1,semantic_input=B.canonical_json({}),replay_input=b'{}',protected_binding=B.canonical_protected_binding(material).content,replay_policy=M.ReplayPolicy.DISABLED,max_attempts=3,deadline=None,original_available_at=now)
    fields=dict(work_id=ident.work_id,kind='job',subscription_id=None,namespace=b'jobs',command_type=b'run',schema_version_decimal=b'1',runnable_version=1,canonical_version=1,scope_evidence=se.canonical,scope_application=app,scope_tenant=None,scope_owner=None,idempotency_key=None,intent_evidence=B.canonical_intent(admission).content,semantic_input=admission.semantic_input,replay_input=admission.replay_input,protected_binding=admission.protected_binding,replay_policy='disabled',max_attempts=3,deadline=None,original_available_at=now,state='queued',cancellation_requested=False,token=None,ownership_revision=0,lease_until=None,available_at=now,cycle=1,attempt_count=0,dispatch_id=None,result=None,created_at=now,updated_at=now,success_origin=None,completion_guard_id=None,final_fence_at=None,completion_result_digest=None,resolution_operation_id=None,terminal_resolution_operation_id=None,resolution=None)
    return fields


def test_work_observation_validates_full_identity_and_state():
    fields = _work_observation_fields()
    assert O.WorkObservation(**fields).schema_version==1
    for change in ({'state':'running'},{'intent_evidence':b'wrong'},{'scope_application':b'other'},{'success_origin':'guarded'}):
        try:O.WorkObservation(**{**fields,**change})
        except E.PersistenceError as exc:assert exc.code is E.ErrorCode.INVALID_OBSERVATION and exc.unconfirmed
        else:assert False


def test_replay_emission_stops_at_budget():
    # Reduced-budget counting control: only two ~1KiB expansions, never a huge allocation.
    old_limit=B._MAX;old_float=B._float_decimal;calls=[]
    def counted(value):
        calls.append(value)
        return old_float(value)
    B._MAX=128;B._float_decimal=counted
    try:
        rejects(lambda:B.encode_mapping_replay({'x':[5e-324,5e-324]}))
        assert len(calls)==1, 'emitter expanded remaining floats after budget exhaustion'
    finally:B._MAX=old_limit;B._float_decimal=old_float


def test_owned_cancellation_observation_rejected():
    from uuid import UUID
    fields=_work_observation_fields()
    for state in ('claimed','running'):
        owned={**fields,'state':state,'token':UUID(int=2),'ownership_revision':1,'lease_until':fields['created_at'],
               'attempt_count':1 if state=='running' else 0,'dispatch_id':UUID(int=3) if state=='running' else None}
        O.WorkObservation(**owned)
        try:O.WorkObservation(**{**owned,'cancellation_requested':True})
        except E.PersistenceError as exc:
            assert exc.code is E.ErrorCode.INVALID_OBSERVATION and exc.unconfirmed
        else:assert False, 'cancelled owned observation accepted'


def test_observation_text_fields_require_builtin_str():
    class Text(str):pass
    fields=_work_observation_fields()
    for name in ('kind','state','replay_policy'):
        try:O.WorkObservation(**{**fields,name:Text(fields[name])})
        except E.PersistenceError as exc:assert exc.code is E.ErrorCode.INVALID_OBSERVATION
        else:assert False, name+' accepted a str subclass'


def test_replay_depth_rejects_before_leaf_conversion():
    original=B._json_number;calls=[]
    def counted(text):calls.append(text);return original(text)
    B._json_number=counted
    try:
        for event in (False,True):
            calls.clear()
            nested=b'{"x":'+b'['*32+b'0'+b']'*32+b'}'
            raw=(b'{"event_id":"id","name":"event","schema_version":1,"payload":'+nested+b',"metadata":{}}') if event else nested
            rejects(lambda:(B.validate_event_replay(raw) if event else B.decode_mapping_replay(raw)))
            assert calls==(['1'] if event else []), 'depth33 leaf was converted'
        # Event payload depth32 is valid despite outer envelope, as is mapping32.
        nested=b'{"x":'+b'['*31+b'0'+b']'*31+b'}'
        B.decode_mapping_replay(nested)
        B.validate_event_replay(b'{"event_id":"id","name":"event","schema_version":1,"payload":'+nested+b',"metadata":'+nested+b'}')
    finally:B._json_number=original


def test_exhausted_claim_and_cancelled_terminal_rules():
    from uuid import UUID
    from hashlib import sha256
    from modkit_events.persistence.catalog import MUTATION_OPERATION_KINDS
    fields=_work_observation_fields();dispatch=UUID(int=3);operation=UUID(int=4)
    claimed={**fields,'state':'claimed','token':UUID(int=2),'ownership_revision':1,'lease_until':fields['created_at'],'attempt_count':1}
    O.WorkObservation(**claimed) # Positive prior count with NULL current pointer.
    try:O.WorkObservation(**{**claimed,'attempt_count':fields['max_attempts']})
    except E.PersistenceError as exc:assert exc.code is E.ErrorCode.INVALID_OBSERVATION and exc.unconfirmed
    else:assert False, 'exhausted claim accepted'
    O.WorkObservation(**{**fields,'state':'held','cancellation_requested':True,'attempt_count':1,'dispatch_id':dispatch})
    resolution=O.ResolutionObservation(operation_id=operation,operation_kind=MUTATION_OPERATION_KINDS['E31'].value,
        work_id=fields['work_id'],expected_revision=1,cycle=1,attempt=1,dispatch_id=dispatch,outcome='confirmed_success',
        retry_at=None,result=b'out',result_digest=sha256(b'out').digest(),reason=None,evidence=b'evidence',binding=b'binding',resolution_root_xid=1,recorded_at=fields['created_at'])
    O.WorkObservation(**{**fields,'state':'succeeded','cancellation_requested':True,'attempt_count':1,'dispatch_id':dispatch,
        'result':b'out','success_origin':'reconciled','resolution_operation_id':operation,'terminal_resolution_operation_id':operation,'resolution':resolution})


def test_discriminator_equality_hooks_and_tampering():
    from uuid import UUID
    from modkit_events.persistence.catalog import MUTATION_OPERATION_KINDS
    calls=[]
    class Equal:
        def __eq__(self,other):calls.append(other);return True
        def __hash__(self):calls.append('hash');return hash('job')
    class Text(str):pass
    fields=_work_observation_fields()
    for name in ('kind','state','replay_policy','success_origin'):
        for value in (Equal(),Text('guarded' if name=='success_origin' else fields[name])):
            calls.clear();rejects(lambda:O.WorkObservation(**{**fields,name:value}));assert not calls
    work=O.WorkObservation(**fields);object.__setattr__(work,'state',Equal())
    calls.clear();rejects(work.__post_init__);assert not calls
    args=dict(operation_id=UUID(int=4),operation_kind=MUTATION_OPERATION_KINDS['E31'].value,
        work_id=fields['work_id'],expected_revision=1,cycle=1,attempt=1,dispatch_id=UUID(int=3),outcome='confirmed_rejection',retry_at=None,result=None,result_digest=None,reason=None,evidence=b'e',binding=b'b',resolution_root_xid=1,recorded_at=fields['created_at'])
    O.ResolutionObservation(**args)
    for name in ('operation_kind','outcome'):
        for value in (Equal(),Text(args[name])):
            calls.clear();rejects(lambda:O.ResolutionObservation(**{**args,name:value}));assert not calls
    record=O.ResolutionObservation(**args);object.__setattr__(record,'outcome',Equal())
    calls.clear();rejects(record.__post_init__);assert not calls
    rejects(lambda:O.ResolutionObservation(**{**args,'operation_kind':MUTATION_OPERATION_KINDS['E27'].value}))


def test_emit_utf8_escaping_budget_exact_boundary():
    old=B._MAX
    try:
        for text,expected in (('é',b'"\xc3\xa9"'),('\0',b'"\\u0000"'),('"\\',b'"\\"\\\\"')):
            B._MAX=len(expected);assert B._emit(text)==expected
            B._MAX=len(expected)-1
            try:B._emit(text)
            except ValueError:pass
            else:assert False, 'emission exceeded exact byte limit'
    finally:B._MAX=old


def test_predispatch_cancelled_states_rejected():
    fields=_work_observation_fields()
    for state in ('queued','retry_waiting','blocked_schema'):
        O.WorkObservation(**{**fields,'state':state})
        try:O.WorkObservation(**{**fields,'state':state,'cancellation_requested':True})
        except E.PersistenceError as exc:assert exc.code is E.ErrorCode.INVALID_OBSERVATION and exc.unconfirmed
        else:assert False, 'predispatch cancellation was not terminalized'


def test_neutral_factory_scalar_and_snapshot():
    assert hasattr(B,'freeze_request'), 'neutral factory not implemented'
    from modkit_events.persistence.catalog import get_statement,WireType
    from uuid import UUID
    context=B.ReturnContext(expected=(),readiness=None)
    request=B.freeze_request(get_statement('E14'),(),context=context)
    assert request.parameters==() and request.statement is get_statement('E14')
    commands=[bytearray(b'run')];versions=[1]
    params=[b'jobs','job',commands,versions,2,30,None,4]
    request=B.freeze_request(get_statement('E04'),params,context=context)
    commands[0][0]=120;versions[0]=2
    assert request.parameters[2:4]==((b'run',),(1,))
    rejects(lambda:B.freeze_request(get_statement('E04'),[b'jobs','job',[b'run',b'run'],[1,1],2,30,None,4],context=context))
    rejects(lambda:B.freeze_request(get_statement('E04'),[b'jobs','job',[b'run'],[1],2,30,None,1],context=context))
    rejects(lambda:B._scalar(True,WireType.INT4,False))
    rejects(lambda:B._scalar(str(UUID(int=1)),WireType.UUID,False))


def test_factory_context_and_constraints():
    assert hasattr(B,'freeze_request'), 'neutral factory not implemented'
    from modkit_events.persistence.catalog import get_statement
    from uuid import UUID
    empty=B.ReturnContext(expected=(),readiness=None)
    rejects(lambda:B.freeze_request(get_statement('E02'),[b'id',1,b'bad',b'bad'],context=empty))
    rejects(lambda:B.freeze_request(get_statement('E12'),[UUID(int=1),None,1,'reason'],context=empty))
    rejects(lambda:B.freeze_request(get_statement('E30'),[b'jobs',None,UUID(int=1),1],context=empty))
    rejects(lambda:B.freeze_request(get_statement('E33'),['workers'],context=empty))
    f=M.Fence(work_id=UUID(int=1),token=UUID(int=2),ownership_revision=1,cycle=1,expected_attempt=0)
    ctx=B.ReturnContext(expected=(f,),readiness=None)
    params=[f.work_id,f.token,1,1,0,UUID(int=3),b'effect',b'request',None]
    request=B.freeze_request(get_statement('E06'),params,context=ctx)
    assert request.parameters[4]==0
    rejects(lambda:B.freeze_request(get_statement('E06'),params[:4]+[1]+params[5:],context=ctx))


def _work_wire(fields=None):
    from modkit_events.persistence.catalog import get_statement
    data=_work_observation_fields() if fields is None else fields
    return tuple(False if c.name=='resolution_present' else None if c.name.startswith('resolution_record_') else data[c.name] for c in get_statement('E15').result.columns)


def test_work_row_scalar_and_request_coupling():
    assert R is not None,'rows source not implemented'
    from modkit_events.persistence.catalog import get_statement,WireType
    from uuid import UUID
    row=_work_wire();request=B.freeze_request(get_statement('E15'),[UUID(int=1)],context=B.ReturnContext(expected=(),readiness=None))
    assert R.decode_work_observation(row).work_id==UUID(int=1)
    assert R.decode_event_rows(request,[row]).work_id==UUID(int=1)
    assert R.decode_event_rows(request,[]) is None
    assert R._wire_scalar(str(UUID(int=1)),WireType.UUID,False)==UUID(int=1)
    assert R._wire_scalar('123',WireType.XID8,False)==123
    for rows in ([row,row],[row[:-1]],[(UUID(int=2),)+row[1:]]):
        try:R.decode_event_rows(request,rows)
        except E.PersistenceError as exc:assert exc.code is E.ErrorCode.INVALID_OBSERVATION and exc.unconfirmed
        else:assert False


def test_scan_header_and_scalar_result_guards():
    assert R is not None,'rows source not implemented'
    from modkit_events.persistence.catalog import get_statement
    from uuid import UUID
    empty=B.ReturnContext(expected=(),readiness=None)
    request=B.freeze_request(get_statement('E04'),[b'jobs','job',[b'run'],[1],2,30,None,4],context=empty)
    header=('header',3,UUID(int=3),False)+(None,)*56
    page=R.decode_event_rows(request,[header])
    assert page.items==() and page.visited==3 and page.next_cursor==UUID(int=3)
    for rows in ([],[header,header],[('header',0,UUID(int=3),True)+(None,)*56]):
        try:R.decode_event_rows(request,rows)
        except E.PersistenceError as exc:assert exc.code is E.ErrorCode.INVALID_OBSERVATION
        else:assert False
    f=M.Fence(work_id=UUID(int=1),token=UUID(int=2),ownership_revision=1,cycle=1,expected_attempt=0)
    req=B.freeze_request(get_statement('E06'),[f.work_id,f.token,1,1,0,UUID(int=3),b'effect',b'request',None],context=B.ReturnContext(expected=(f,),readiness=None))
    assert R.decode_event_rows(req,[(1,)])==1
    try:R.decode_event_rows(req,[(2,)])
    except E.PersistenceError as exc:assert exc.code is E.ErrorCode.INVALID_OBSERVATION and exc.unconfirmed
    else:assert False


def _admission_from_work_fields(data):
    identity=M.WorkIdentity(work_id=data['work_id'],kind=M.WorkKind(data['kind']),subscription_id=None if data['subscription_id'] is None else data['subscription_id'].decode(),namespace=data['namespace'].decode(),command_type=data['command_type'].decode(),scope=M.ScopeEvidence(canonical_version=data['canonical_version'],canonical=data['scope_evidence'],application=data['scope_application'],tenant=data['scope_tenant'],owner=data['scope_owner']),idempotency_key=None if data['idempotency_key'] is None else data['idempotency_key'].decode())
    return M.AdmissionInput(identity=identity,schema_version=B.version_from_decimal(data['schema_version_decimal']),semantic_input=data['semantic_input'],replay_input=data['replay_input'],protected_binding=data['protected_binding'],replay_policy=M.ReplayPolicy(data['replay_policy']),max_attempts=data['max_attempts'],deadline=data['deadline'],original_available_at=data['original_available_at'])


def test_worker_catalog_factory_and_scan_shared_seam():
    from modkit_workers.persistence.catalog import get_statement
    from uuid import UUID
    data=_work_observation_fields();admission=_admission_from_work_fields(data)
    data.update(material_state='absent',protected_sidecar=None,protected_reference=None,protected_codec=None,protected_key_version=None,protected_expires_at=None,protected_recovery_metadata=b'',protected_cleanup_policy='retain',projection_metadata=B.canonical_json({}))
    params=[data[p.name] for p in get_statement('W01').parameters]
    req=B.freeze_request(get_statement('W01'),params,context=B.ReturnContext(expected=(admission,),readiness=None))
    assert len(req.parameters)==29 and req.statement is get_statement('W01')
    wrong=list(params);wrong[-1]=B.canonical_json({'changed':True})
    rejects(lambda:B.freeze_request(get_statement('W01'),wrong,context=req.context))
    empty=B.ReturnContext(expected=(),readiness=None)
    scan=B.freeze_request(get_statement('W05'),[b'jobs',[b'run'],[1],2,30,None,4],context=empty)
    work={**_work_observation_fields(),'state':'claimed','token':UUID(int=2),'ownership_revision':1,'lease_until':data['created_at']}
    suffix=(work['work_id'],work['scope_application'],None,None,work['protected_binding'],work['semantic_input'],'absent',None,None,None,None,None,b'','retain',B.canonical_json({}))
    row=('item',None,None,None)+_work_wire(work)+suffix
    header=('header',1,work['work_id'],True)+(None,)*71
    frame=R.split_scan_rows(scan,[header,row])
    assert frame.visited==1 and len(frame.item_columns)==1 and len(frame.item_columns[0])==71
    for bad in ([header,row,row],[header,('item',1,None,None)+row[4:]]):
        try:R.split_scan_rows(scan,bad)
        except E.PersistenceError as exc:assert exc.code is E.ErrorCode.INVALID_OBSERVATION
        else:assert False


def test_readiness_observation_mismatch_category():
    from modkit_events.persistence.catalog import get_statement
    # Synthetic expected digest exercises pure comparison only, no installed-schema claim.
    args=dict(component='events',version=1,migration_digest=b'x'*32,catalog_contract_id='modkit-pg-ab-2',scope_format_id='MKSC-1',intent_format_id='MKPF-1')
    expected=O.SchemaStatus(**args)
    req=B.freeze_request(get_statement('E33'),['events'],context=B.ReturnContext(expected=(),readiness=B.ReadinessExpectation(components=(expected,))))
    row=tuple(args[c.name] for c in get_statement('E33').result.columns)
    assert R.decode_event_rows(req,[row])==(expected,)
    changed=row[:2]+(b'y'*32,)+row[3:]
    try:R.decode_event_rows(req,[changed])
    except E.PersistenceError as exc:assert exc.code is E.ErrorCode.SCHEMA_MISMATCH
    else:assert False


def _round2_reject(fn, observed=True, code=None):
    try:fn()
    except E.PersistenceError as exc:
        assert exc.code is (code or (E.ErrorCode.INVALID_OBSERVATION if observed else E.ErrorCode.LOCAL_INVALID_ARGUMENT)), exc.code
        assert exc.unconfirmed is observed
        return
    raise AssertionError('invalid accepted')


def test_round2_actual_sequence_snapshots():
    from collections.abc import Sequence
    from modkit_events.persistence.catalog import get_statement
    from uuid import UUID
    class Input(Sequence):
        def __init__(self,values,declared):self.values=values;self.declared=declared;self.reads=[]
        def __len__(self):return self.declared
        def __getitem__(self,i):
            if i>=len(self.values):raise IndexError
            self.reads.append(i);return self.values[i]
    spec=get_statement('E15');context=B.ReturnContext(expected=(),readiness=None)
    for values in ([],[UUID(int=1),UUID(int=2)]):
        value=Input(values,1)
        _round2_reject(lambda:B.freeze_request(spec,value,context=context),False)
        assert len(value.reads)<=2
    value=Input([UUID(int=1)],999)
    assert B.freeze_request(spec,value,context=context).parameters==(UUID(int=1),)
    assert value.reads==[0]


def test_round2_bounded_inner_rows():
    from collections.abc import Sequence
    from modkit_events.persistence.catalog import get_statement
    class Input(Sequence):
        def __init__(self,n):self.n=n;self.reads=0
        def __len__(self):return 1
        def __getitem__(self,i):
            if i>=self.n:raise IndexError
            self.reads+=1;return 1
    value=Input(1000)
    _round2_reject(lambda:R._bounded_rows([value],1))
    assert value.reads==257
    cols=get_statement('E06').result.columns
    for size in (0,2,1000):
        value=Input(size)
        _round2_reject(lambda:R._decode_columns(cols,value))
        assert value.reads<=2
    value=Input(1)
    assert R._decode_columns(cols,value)==(1,) and value.reads==1
    assert R._bounded_rows([(1,)],1)==((1,),)


def _round2_outbox(state,revision):
    from uuid import UUID
    from datetime import datetime,timezone
    raw=b'{"event_id":"id","name":"event","schema_version":1,"payload":{},"metadata":{}}'
    event=B.validate_event_replay(raw);now=datetime(2026,1,1,tzinfo=timezone.utc)
    return dict(event_id=b'id',canonical_version=1,envelope_evidence=B.canonical_event(event).content,replay_input=raw,state=state,token=UUID(int=1) if state in ('claimed','publishing') else None,ownership_revision=revision,lease_until=now if state in ('claimed','publishing') else None,intent_id=None if state in ('pending','claimed') else UUID(int=2),receipt=None,outcome_evidence=None,created_at=now,updated_at=now)


def test_round2_owned_outbox_revision():
    from modkit_events.persistence.catalog import get_statement
    context=B.ReturnContext(expected=(),readiness=None)
    for state in ('claimed','publishing'):
        data=_round2_outbox(state,0)
        _round2_reject(lambda:O.OutboxRow(**data))
        request=B.freeze_request(get_statement('E28'),[b'id'],context=context)
        row=lambda:tuple(data[c.name] for c in get_statement('E28').result.columns)
        _round2_reject(lambda:R.decode_event_rows(request,[row()]))
        data['ownership_revision']=1
        assert O.OutboxRow(**data).ownership_revision==1
        assert R.decode_event_rows(request,[row()]).ownership_revision==1
    for state in ('pending','held','published','rejected'):
        assert O.OutboxRow(**_round2_outbox(state,0)).state==state


def test_round2_readiness_classification():
    from modkit_events.persistence.catalog import get_statement
    args=dict(component='events',version=1,migration_digest=b'x'*32,catalog_contract_id='modkit-pg-ab-2',scope_format_id='MKSC-1',intent_format_id='MKPF-1')
    expected=O.SchemaStatus(**args)
    request=B.freeze_request(get_statement('E33'),['events'],context=B.ReturnContext(expected=(),readiness=B.ReadinessExpectation(components=(expected,))))
    def decode(data):return R.decode_event_rows(request,[tuple(data[c.name] for c in get_statement('E33').result.columns)])
    for name,value in [('version',2),('migration_digest',b'y'*32),('catalog_contract_id','other-1'),('scope_format_id','MKSC-2'),('intent_format_id','MKPF-2')]:
        _round2_reject(lambda:decode(args|{name:value}),False,E.ErrorCode.SCHEMA_MISMATCH)
    for name,value in [('component','other'),('version',True),('migration_digest',b'x'),('scope_format_id',''),('intent_format_id',None)]:
        _round2_reject(lambda:decode(args|{name:value}))
    changed=O.SchemaStatus(**(args|{'scope_format_id':'MKSC-2'}))
    _round2_reject(lambda:B.ReadinessExpectation(components=(changed,)),False)


def test_round2_outbox_scan_whole_page():
    from modkit_events.persistence.catalog import get_statement
    from hashlib import sha256
    data=_round2_outbox('claimed',0)
    req=B.freeze_request(get_statement('E22'),[2,30,None,4],context=B.ReturnContext(expected=(),readiness=None))
    header=('header',1,sha256(b'id').digest(),True)+(None,)*13
    def row():return ('item',None,None,None)+tuple(data[c.name] for c in get_statement('E28').result.columns)
    _round2_reject(lambda:R.decode_event_rows(req,[header,row()]))
    data['ownership_revision']=1
    assert R.decode_event_rows(req,[header,row()]).items[0].ownership_revision==1
    # Second full row shares event envelope but is revision-invalid. With larger
    # limit and matching visited count, cardinality cannot mask item validation.
    req=B.freeze_request(get_statement('E22'),[3,30,None,4],context=req.context)
    header=('header',2,sha256(b'id').digest(),True)+(None,)*13
    good=row();data['ownership_revision']=0
    _round2_reject(lambda:R.decode_event_rows(req,[header,good,row()]))


# Independent literal test oracle from accepted record-code design/correction1.
_ROUND2_HISTORY_BOUNDS={
 'intake_runnable':(0,0),'intake_blocked':(0,0),'claim':(0,999),
 'defer':(0,999),'recover_claim':(0,999),'failure_retry':(1,999),
 'reconcile_safe_retry':(1,999),'renew':(0,1000),'cancel_predispatch':(0,1000),
 'recover_expired_predispatch':(0,1000),'dispatch':(1,1000),'complete':(1,1000),
 'failure_terminal':(1,1000),'failure_cancelled':(1,1000),'cancel_running':(1,1000),
 'cancel_held':(1,1000),'recover_exhausted_predispatch':(1,1000),
 'recover_dispatched':(1,1000),'reconcile_success':(1,1000),
 'reconcile_rejection':(1,1000),'reconcile_cancelled':(1,1000),'hold_uncertain':(1,1000)}

def _round2_history(code):
    from uuid import UUID
    from datetime import datetime,timezone
    return dict(history_id=1,work_id=UUID(int=1),cycle=1,attempt=_ROUND2_HISTORY_BOUNDS[code][0],transition=code,reason='attempts_exhausted' if code=='recover_exhausted_predispatch' else code,token=UUID(int=2) if code in ('claim','renew','dispatch') else None,ownership_revision=0 if code.startswith('intake_') else 1,evidence=b'',recorded_at=datetime(2026,1,1,tzinfo=timezone.utc))

def _round2_record_path(key,cls,data,parameters):
    from modkit_events.persistence.catalog import get_statement
    request=B.freeze_request(get_statement(key),parameters,context=B.ReturnContext(expected=(),readiness=None))
    def decode(d):return R.decode_event_rows(request,[tuple(d[c.name] for c in get_statement(key).result.columns)])
    assert decode(data)==(cls(**data),)
    return decode


def test_round2_domains_history():
    from uuid import UUID
    for code,(low,high) in _ROUND2_HISTORY_BOUNDS.items():
        data=_round2_history(code)
        decode=_round2_record_path('E19',O.WorkHistoryRow,data,[data['work_id'],0,2])
        for bad in ('not_a_protocol_code',code.upper(),''):
            _round2_reject(lambda:O.WorkHistoryRow(**(data|{'transition':bad})))
            _round2_reject(lambda:decode(data|{'transition':bad}))
        for count in (low,high):assert O.WorkHistoryRow(**(data|{'attempt':count})).attempt==count
        for count in (low-1,high+1,True):_round2_reject(lambda:decode(data|{'attempt':count}))
        _round2_reject(lambda:decode(data|{'token':None if data['token'] else UUID(int=3)}))
        _round2_reject(lambda:decode(data|{'ownership_revision':1 if data['ownership_revision']==0 else 0}))
        for name,value in [('cycle',2),('evidence',None),('work_id',UUID(int=9)),('history_id',0)]:
            _round2_reject(lambda:decode(data|{name:value}))
        submitted=code in ('failure_terminal','failure_cancelled','failure_retry','cancel_predispatch','cancel_running','cancel_held','hold_uncertain')
        if submitted:assert decode(data|{'reason':'user_reason'})
        else:_round2_reject(lambda:decode(data|{'reason':'user_reason'}))
        if code.startswith(('failure_','reconcile_')) or code=='hold_uncertain':assert decode(data|{'evidence':b'provided'})
        else:_round2_reject(lambda:decode(data|{'evidence':b'provided'}))
    class Sub(str):pass
    data=_round2_history('claim')
    _round2_reject(lambda:O.WorkHistoryRow(**(data|{'transition':Sub('claim')})))


_ROUND2_PUBLICATION={
 'enqueue':('none',False,False),'claim_publication':('none',False,False),
 'renew_publication':('either',False,False),'publication_intent':('required',False,False),
 'publication_confirmed':('required',False,True),'publication_rejected':('required',False,True),
 'publication_uncertain':('required',False,True),'recover_publication_preintent':('none',False,False),
 'recover_publication_intent':('required',False,False),'repair_published':('required',True,True),
 'repair_rejected':('required',True,True)}

def test_round2_domains_publication():
    from uuid import UUID
    from datetime import datetime,timezone
    for code,(intent,repair,settled) in _ROUND2_PUBLICATION.items():
        data=dict(history_id=1,event_id=b'id',intent_id=UUID(int=1) if intent=='required' else None,operation_id=UUID(int=2) if repair else None,status=code,receipt=None,evidence=b'',binding=b'',recorded_at=datetime(2026,1,1,tzinfo=timezone.utc))
        decode=_round2_record_path('E29',O.PublicationRow,data,[b'id',0,2])
        for bad in ('not_a_protocol_code',code.upper(),''):
            _round2_reject(lambda:O.PublicationRow(**(data|{'status':bad})))
            _round2_reject(lambda:decode(data|{'status':bad}))
        if intent=='either':assert decode(data|{'intent_id':UUID(int=3)})
        else:_round2_reject(lambda:decode(data|{'intent_id':None if intent=='required' else UUID(int=3)}))
        _round2_reject(lambda:decode(data|{'operation_id':None if repair else UUID(int=3)}))
        for name in ('receipt','evidence','binding'):
            allowed=(settled if name!='binding' else repair)
            if allowed:assert decode(data|{name:b'provided'})
            else:_round2_reject(lambda:decode(data|{name:b'provided'}))
        for name,value in [('receipt',b'x'*4097),('evidence',None),('binding',None),('event_id',b'other'),('history_id',0)]:
            _round2_reject(lambda:decode(data|{name:value}))
    class Sub(str):pass
    _round2_reject(lambda:O.PublicationRow(**(data|{'status':Sub(code)})))


def test_round2_domains_attempt():
    from uuid import UUID
    from datetime import datetime,timezone
    for code in ('dispatched','succeeded','failed','cancelled','uncertain','cancelled_unresolved','safe_retry'):
        data=dict(work_id=UUID(int=1),cycle=1,attempt=1,dispatch_id=UUID(int=2),effect_id=b'effect',request_evidence=b'request',provider_key_reference=None,dispatch_root_xid=1,outcome=code,evidence=b'',recorded_at=datetime(2026,1,1,tzinfo=timezone.utc))
        decode=_round2_record_path('E21',O.AttemptRow,data,[data['work_id'],0,0,2])
        for bad in ('not_a_protocol_code',code.upper(),''):
            _round2_reject(lambda:O.AttemptRow(**(data|{'outcome':bad})))
            _round2_reject(lambda:decode(data|{'outcome':bad}))
        if code in ('dispatched','cancelled_unresolved'):_round2_reject(lambda:decode(data|{'evidence':b'provided'}))
        else:assert decode(data|{'evidence':b'provided'})
        assert decode(data|{'attempt':1000,'provider_key_reference':b'key'})
        for name,value in [('attempt',0),('attempt',1001),('attempt',True),('cycle',2),('dispatch_root_xid',0),('evidence',None),('work_id',UUID(int=9))]:
            _round2_reject(lambda:decode(data|{name:value}))
    class Sub(str):pass
    _round2_reject(lambda:O.AttemptRow(**(data|{'outcome':Sub(code)})))


def test_round2_domains_parent_cursor_batch():
    from modkit_events.persistence.catalog import get_statement
    from uuid import UUID
    from datetime import datetime,timezone
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    fixtures=[
      ('E19',_round2_history('dispatch'),[UUID(int=1),1,2],'history_id',2),
      ('E29',dict(history_id=1,event_id=b'id',intent_id=None,operation_id=None,status='enqueue',receipt=None,evidence=b'',binding=b'',recorded_at=now),[b'id',1,2],'history_id',2),
      ('E21',dict(work_id=UUID(int=1),cycle=1,attempt=1,dispatch_id=UUID(int=2),effect_id=b'effect',request_evidence=b'',provider_key_reference=None,dispatch_root_xid=1,outcome='dispatched',evidence=b'',recorded_at=now),[UUID(int=1),1,1,2],'attempt',2)]
    for key,data,params,ordinal,next_ordinal in fixtures:
        spec=get_statement(key)
        request=B.freeze_request(spec,params,context=B.ReturnContext(expected=(),readiness=None))
        def wire(d):return tuple(d[c.name] for c in spec.result.columns)
        _round2_reject(lambda:R.decode_event_rows(request,[wire(data)]))
        data=data|{ordinal:next_ordinal}
        assert len(R.decode_event_rows(request,[wire(data)]))==1
        parent='event_id' if key=='E29' else 'work_id'
        bad=data|{ordinal:next_ordinal+1,parent:b'other' if parent=='event_id' else UUID(int=9)}
        _round2_reject(lambda:R.decode_event_rows(request,[wire(data),wire(bad)]))
        _round2_reject(lambda:R.decode_event_rows(request,[wire(data),wire(data)]))


def _g1_expect_error(call, observed):
    try:call()
    except E.PersistenceError as error:
        expected=E.ErrorCode.INVALID_OBSERVATION if observed else E.ErrorCode.LOCAL_INVALID_ARGUMENT
        assert error.code is expected and error.unconfirmed is observed
        assert error.args==(expected.value,)
        assert error.__cause__ is None and error.__context__ is None and error.__suppress_context__
        return
    raise AssertionError('G1 invalid accepted')


def _g1_guard_fixture(key):
    from uuid import UUID
    from modkit_events.persistence.catalog import get_statement
    fence=M.Fence(work_id=UUID(int=11),token=UUID(int=12),ownership_revision=2,cycle=1,expected_attempt=1)
    data=dict(guard_id=UUID(int=13),work_id=fence.work_id,root_xid=3,token=fence.token,ownership_revision=2,cycle=1,expected_attempt=1,satisfied=False,final_fence_at=None,terminal_state=None,result_digest=None)
    spec=get_statement(key)
    request=B.freeze_request(spec,[getattr(fence,p.name) for p in spec.parameters],context=B.ReturnContext(expected=(fence,),readiness=None))
    return request,data


def _g1_wire(request,data):return tuple(data[c.name] for c in request.statement.result.columns)


def test_g1_e14_wire_xid_and_cardinality():
    from modkit_events.persistence.catalog import get_statement
    request=B.freeze_request(get_statement('E14'),(),context=B.ReturnContext(expected=(),readiness=None))
    for value,expected in [(1,1),(2**64-1,2**64-1),('1',1),(str(2**64-1),2**64-1)]:
        assert R.decode_event_rows(request,[(value,)])==expected
    for value in (0,-1,2**64,True,None,'0','01','+1',' 1','1 ','１',str(2**64),b'1'):
        _g1_expect_error(lambda:R.decode_event_rows(request,[(value,)]),True)
    for rows in ([],[(1,),(1,)],[()],[(1,2)]):_g1_expect_error(lambda:R.decode_event_rows(request,rows),True)
    _g1_expect_error(lambda:B.freeze_request(get_statement('E14'),[1],context=request.context),False)


def test_g1_e08_e09_guard_fence_and_wire():
    from uuid import UUID
    for key in ('E08','E09'):
        request,data=_g1_guard_fixture(key)
        actual=R.decode_event_rows(request,[_g1_wire(request,data)])
        assert actual==O.GuardRow(**data)
        for name,value in [('work_id',UUID(int=21)),('token',UUID(int=22)),('ownership_revision',3),('cycle',2),('expected_attempt',2)]:
            _g1_expect_error(lambda:R.decode_event_rows(request,[_g1_wire(request,data|{name:value})]),True)
        for name,values in [('guard_id',[None,b'bad',1]),('root_xid',[0,-1,2**64,True,None]),('ownership_revision',[0,2**63,True]),('expected_attempt',[0,1001,True]),('satisfied',[1,None,'false'])]:
            for value in values:_g1_expect_error(lambda:R.decode_event_rows(request,[_g1_wire(request,data|{name:value})]),True)
        # Guard/root IDs aren't request fields: validate wire bounds, not invented equality.
        for root in (1,2**64-1,str(2**64-1)):
            row=R.decode_event_rows(request,[_g1_wire(request,data|{'root_xid':root})])
            assert row.root_xid==int(root)
        strings=data|{n:str(data[n]) for n in ('guard_id','work_id','token')}
        assert R.decode_event_rows(request,[_g1_wire(request,strings)])==actual
        if key=='E09':assert R.decode_event_rows(request,[]) is None
        else:_g1_expect_error(lambda:R.decode_event_rows(request,[]),True)
        row=_g1_wire(request,data)
        for rows in ([row,row],[row[:-1]],[row+(None,)]):_g1_expect_error(lambda:R.decode_event_rows(request,rows),True)


def test_g1_guard_certificate_null_arms():
    from datetime import datetime,timezone,timedelta
    instant=datetime(2026,1,1,tzinfo=timezone(timedelta(hours=3)))
    for key in ('E08','E09'):
        request,data=_g1_guard_fixture(key)
        for name,value in [('final_fence_at',instant),('terminal_state','succeeded'),('result_digest',b'x'*32)]:
            bad=data|{name:value}
            _g1_expect_error(lambda:O.GuardRow(**bad),True)
            _g1_expect_error(lambda:R.decode_event_rows(request,[_g1_wire(request,bad)]),True)
        source_digest=bytearray(b'x'*32)
        full=data|dict(satisfied=True,final_fence_at=instant,terminal_state='succeeded',result_digest=source_digest)
        generic=O.GuardRow(**full)
        assert generic.final_fence_at==instant.astimezone(timezone.utc)
        assert generic.final_fence_at.tzinfo is timezone.utc
        assert generic.final_fence_at.utcoffset()==timedelta(0)
        assert type(generic.result_digest) is bytes and generic.result_digest==b'x'*32
        source_digest[:]=b'y'*32
        assert generic.result_digest==b'x'*32
        _g1_expect_error(lambda:R.decode_event_rows(request,[_g1_wire(request,full)]),True)
        for name in ('final_fence_at','terminal_state','result_digest'):
            _g1_expect_error(lambda:O.GuardRow(**(full|{name:None})),True)
        for name,value in [('terminal_state','failed'),('result_digest',b'x'*31),('result_digest',b'x'*33),('final_fence_at',datetime(2026,1,1))]:
            _g1_expect_error(lambda:O.GuardRow(**(full|{name:value})),True)


def test_g1_e10_guardref_freeze_and_unit():
    from uuid import UUID
    from modkit_events.persistence.catalog import get_statement
    guard=M.GuardRef(guard_id=UUID(int=1),work_id=UUID(int=2),root_xid=3,token=UUID(int=4),ownership_revision=5,cycle=1,expected_attempt=1)
    spec=get_statement('E10');context=B.ReturnContext(expected=(guard,),readiness=None)
    result=bytearray(b'first');params=[getattr(guard,p.name) if p.name!='result' else result for p in spec.parameters]
    request=B.freeze_request(spec,params,context=context);result[:]=b'other'
    assert request.parameters[-1]==b'first' and R.decode_event_rows(request,[(True,)]) is True
    for i,p in enumerate(spec.parameters[:-1]):
        changed=list(params);value=changed[i];changed[i]=UUID(int=99) if type(value) is UUID else value+1
        _g1_expect_error(lambda:B.freeze_request(spec,changed,context=context),False)
    for value in (False,1,0,None,'true'):_g1_expect_error(lambda:R.decode_event_rows(request,[(value,)]),True)
    for rows in ([],[(True,),(True,)],[()],[(True,True)]):_g1_expect_error(lambda:R.decode_event_rows(request,rows),True)
    _g1_expect_error(lambda:B.freeze_request(spec,params,context=B.ReturnContext(expected=(),readiness=None)),False)


def test_g1_context_descriptor_and_tamper():
    from dataclasses import replace
    from uuid import UUID
    from modkit_events.persistence.catalog import get_statement
    for key in ('E08','E09'):
        request,data=_g1_guard_fixture(key)
        for context in (B.ReturnContext(expected=(),readiness=None),object()):
            _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=context),False)
        for index,value in enumerate(request.parameters):
            changed=list(request.parameters);changed[index]=UUID(int=99) if type(value) is UUID else value+1
            _g1_expect_error(lambda:B.freeze_request(request.statement,changed,context=request.context),False)
        copied=B.freeze_request(replace(request.statement),request.parameters,context=request.context)
        _g1_expect_error(lambda:R.decode_event_rows(copied,[_g1_wire(request,data)]),True)
        tampered=replace(request);object.__setattr__(tampered,'parameters',request.parameters[:-1])
        _g1_expect_error(lambda:R.decode_event_rows(tampered,[_g1_wire(request,data)]),True)
        fence=request.context.expected[0];badfence=replace(fence);object.__setattr__(badfence,'ownership_revision',0)
        badcontext=replace(request.context);object.__setattr__(badcontext,'expected',(badfence,))
        _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=badcontext),False)
    calls=[]
    class Text(str):
        def __int__(self):calls.append('int');return 1
        def __eq__(self,other):calls.append('eq');return True
    request=B.freeze_request(get_statement('E14'),(),context=B.ReturnContext(expected=(),readiness=None))
    _g1_expect_error(lambda:R.decode_event_rows(request,[(Text('1'),)]),True)
    assert calls==[]


def test_g1_bounded_failure_and_baseexception():
    request,data=_g1_guard_fixture('E09');row=_g1_wire(request,data);seen=[]
    def overflow():
        for index in range(4):seen.append(index);yield row
    _g1_expect_error(lambda:R.decode_event_rows(request,overflow()),True)
    assert seen==[0,1]
    def ordinary():
        yield row
        raise RuntimeError('private provider detail')
    try:raise ValueError('ambient')
    except ValueError:_g1_expect_error(lambda:R.decode_event_rows(request,ordinary()),True)
    class Stop(BaseException):pass
    marker=Stop('primary');marker.add_note('original')
    cause=ValueError('cause');context=ValueError('context')
    marker.__cause__=cause;marker.__context__=context;marker.__suppress_context__=False
    def interrupted():
        yield row
        raise marker
    try:R.decode_event_rows(request,interrupted())
    except Stop as caught:
        assert caught is marker and caught.args==('primary',) and caught.__notes__==['original']
        assert caught.__cause__ is cause and caught.__context__ is context and not caught.__suppress_context__
    else:raise AssertionError('G1 primary swallowed')


def _g2_fixture(key,outcome='confirmed_success'):
    from datetime import datetime,timezone
    from uuid import UUID
    from modkit_events.persistence.catalog import get_statement
    now=datetime(2026,1,1,tzinfo=timezone.utc);work=UUID(int=1);token=UUID(int=2);dispatch=UUID(int=3);operation=UUID(int=9)
    context=B.ReturnContext(expected=(),readiness=None)
    if key=='E27':
        params=[b'event',2,operation,'published',None,b'evidence',b'binding']
        names=('operation_id','event_id','expected_revision','status','receipt','evidence','binding','resulting_revision','recorded_at')
        row=(operation,b'event',2,'published',None,b'evidence',b'binding',3,now)
    elif key=='E31':
        retry=now if outcome=='safe_retry' else None;result=b'' if outcome=='confirmed_success' else None
        digest=bytes.fromhex('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855') if result is not None else None
        params=[work,2,1,1,dispatch,operation,outcome,retry,result,b'evidence',b'binding']
        names=('operation_id','operation_kind','work_id','expected_revision','cycle','attempt','dispatch_id','outcome','retry_at','result','result_digest','reason','evidence','binding','resolution_root_xid','recorded_at')
        row=(operation,'reconcile_work',work,2,1,1,dispatch,outcome,retry,result,digest,None,b'evidence',b'binding',77,now)
    else:
        fence=M.Fence(work_id=work,token=token,ownership_revision=2,cycle=1,expected_attempt=1)
        context=B.ReturnContext(expected=(fence,),readiness=None)
        params=[work,token,2,1,1,77,operation,'uncertain',b'evidence',b'binding']
        names=('operation_id','work_id','token','expected_revision','cycle','attempt','dispatch_id','failed_business_root','reason','evidence','binding','resulting_revision','recorded_at')
        row=(operation,work,token,2,1,1,dispatch,77,'uncertain',b'evidence',b'binding',3,now)
    request=B.freeze_request(get_statement(key),params,context=context)
    return request,row,names


def test_g2_e31_reason_fixed_null():
    for outcome in ('confirmed_success','confirmed_rejection','confirmed_cancelled','safe_retry'):
        request,row,names=_g2_fixture('E31',outcome)
        result=R.decode_event_rows(request,[row])
        direct=O.ResolutionObservation(**dict(zip(names,row)))
        assert tuple(getattr(result,name) for name in names)==row
        assert direct==result and result.reason is None
        for reason in ('reconcile_success','reconcile_rejection','reconcile_cancelled',
                       'reconcile_safe_retry','unexpected','',0,False,b'reconcile_success'):
            changed=list(row);changed[11]=reason
            _g1_expect_error(lambda:R.decode_event_rows(request,[tuple(changed)]),True)
            _g1_expect_error(lambda:O.ResolutionObservation(**dict(zip(names,changed))),True)


def test_g2_e27_repair_fields_preserved():
    request,row,names=_g2_fixture('E27')
    for status in ('published','rejected'):
        for receipt in (None,b''):
            params=list(request.parameters);params[3]=status;params[4]=receipt
            changed=list(row);changed[3]=status;changed[4]=receipt
            frozen=B.freeze_request(request.statement,params,context=request.context)
            actual=R.decode_event_rows(frozen,[tuple(changed)])
            assert tuple(getattr(actual,name) for name in names)==tuple(changed)
            assert O.RepairObservation(**dict(zip(names,changed)))==actual


def test_g2_e32_submitted_reason_preserved():
    request,row,names=_g2_fixture('E32')
    for reason in ('uncertain','reconcile_success','a'*256):
        params=list(request.parameters);params[7]=reason
        changed=list(row);changed[8]=reason
        frozen=B.freeze_request(request.statement,params,context=request.context)
        actual=R.decode_event_rows(frozen,[tuple(changed)])
        assert tuple(getattr(actual,name) for name in names)==tuple(changed)
        assert O.SettlementObservation(**dict(zip(names,changed)))==actual
        changed[8]='different_valid_reason'
        _g1_expect_error(lambda:R.decode_event_rows(frozen,[tuple(changed)]),True)
    for reason in (None,'','A','a'*257,b'uncertain',False):
        params=list(request.parameters);params[7]=reason
        changed=list(row);changed[8]=reason
        _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
        _g1_expect_error(lambda:R.decode_event_rows(request,[tuple(changed)]),True)
        _g1_expect_error(lambda:O.SettlementObservation(**dict(zip(names,changed))),True)


def test_g2_literal_results_and_each_request_field():
    from uuid import UUID
    from datetime import timedelta
    from hashlib import sha256
    maps={
      'E27':{'event_id':1,'expected_revision':2,'operation_id':0,'status':3,'receipt':4,'evidence':5,'binding':6},
      'E31':{'work_id':2,'expected_revision':3,'cycle':4,'attempt':5,'dispatch_id':6,'operation_id':0,'outcome':7,'retry_at':8,'result':9,'evidence':12,'binding':13},
      'E32':{'work_id':1,'token':2,'ownership_revision':3,'cycle':4,'expected_attempt':5,'failed_business_root':7,'operation_id':0,'reason':8,'evidence':9,'binding':10}}
    for key in ('E27','E31','E32'):
        request,row,names=_g2_fixture(key)
        actual=R.decode_event_rows(request,[row])
        assert tuple(getattr(actual,name) for name in names)==row
        for name,index in maps[key].items():
            if key=='E31' and name=='retry_at':
                request2,base,_=_g2_fixture(key,'safe_retry');changed=list(base);changed[8]+=timedelta(seconds=1)
                _g1_expect_error(lambda:R.decode_event_rows(request2,[tuple(changed)]),True)
                continue
            changed=list(row);value=changed[index]
            if type(value) is UUID:changed[index]=UUID(int=999)
            elif type(value) is int:changed[index]=value+1
            elif type(value) is bytes:changed[index]=b'changed'
            elif value is None:changed[index]=b'changed'
            elif name=='status':changed[index]='rejected'
            elif name=='outcome':changed[index]='confirmed_cancelled'
            else:changed[index]='changed'
            # Change one requested semantic field while preserving dependent result digest.
            if key=='E31' and name=='result':changed[10]=sha256(changed[9]).digest()
            if key=='E31' and name=='outcome':changed[9]=changed[10]=None
            _g1_expect_error(lambda:R.decode_event_rows(request,[tuple(changed)]),True)


def test_g2_nullable_domains_and_revision():
    from datetime import datetime
    for outcome in ('confirmed_success','confirmed_rejection','confirmed_cancelled','safe_retry'):
        request,row,names=_g2_fixture('E31',outcome)
        actual=R.decode_event_rows(request,[row]);assert tuple(getattr(actual,name) for name in names)==row
        invalid={1:['repair_publication','hold_uncertain','RECONCILE_WORK',None],7:['unknown',None],14:[0,2**64,True],15:[None,datetime(2026,1,1)]}
        if outcome=='confirmed_success':invalid.update({9:[None],10:[None,b'x'*32,b'x'*31]})
        else:invalid.update({9:[b''],10:[b'x'*32]})
        invalid[8]=[None] if outcome=='safe_retry' else [row[15]]
        for index,values in invalid.items():
            for value in values:
                changed=list(row);changed[index]=value
                _g1_expect_error(lambda:R.decode_event_rows(request,[tuple(changed)]),True)
    for key,index in [('E27',7),('E32',11)]:
        request,row,names=_g2_fixture(key)
        for revision in (0,2,True,2**63):
            changed=list(row);changed[index]=revision
            _g1_expect_error(lambda:R.decode_event_rows(request,[tuple(changed)]),True)
    request,row,names=_g2_fixture('E27')
    for receipt in (None,b'',b'x'*4096):
        params=list(request.parameters);params[4]=receipt
        req=B.freeze_request(request.statement,params,context=request.context)
        changed=list(row);changed[4]=receipt
        assert R.decode_event_rows(req,[tuple(changed)]).receipt==receipt
    changed=list(row);changed[4]=b'x'*4097
    _g1_expect_error(lambda:R.decode_event_rows(request,[tuple(changed)]),True)


def test_g2_context_cardinality_and_snapshot():
    from dataclasses import replace
    from uuid import UUID
    for key in ('E27','E31','E32'):
        request,row,names=_g2_fixture(key)
        for rows in ([],[row,row],[row[:-1]],[row+(None,)]):_g1_expect_error(lambda:R.decode_event_rows(request,rows),True)
        copied=B.freeze_request(replace(request.statement),request.parameters,context=request.context)
        _g1_expect_error(lambda:R.decode_event_rows(copied,[row]),True)
        params=list(request.parameters)
        evidence_index={'E27':5,'E31':9,'E32':8}[key]
        buffer=bytearray(b'evidence');params[evidence_index]=buffer
        frozen=B.freeze_request(request.statement,params,context=request.context);buffer[:]=b'mutated!'
        assert frozen.parameters[evidence_index]==b'evidence'
        assert tuple(getattr(R.decode_event_rows(frozen,[row]),name) for name in names)==row
        bad=replace(request);object.__setattr__(bad,'parameters',request.parameters[:-1])
        _g1_expect_error(lambda:R.decode_event_rows(bad,[row]),True)
    request,row,names=_g2_fixture('E32')
    _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=B.ReturnContext(expected=(),readiness=None)),False)
    for index in range(5):
        changed=list(request.parameters);value=changed[index];changed[index]=UUID(int=99) if type(value) is UUID else value+1
        _g1_expect_error(lambda:B.freeze_request(request.statement,changed,context=request.context),False)
    for key in ('E27','E31'):
        request,row,names=_g2_fixture(key)
        fence=M.Fence(work_id=UUID(int=1),token=UUID(int=2),ownership_revision=2,cycle=1,expected_attempt=1)
        _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=B.ReturnContext(expected=(fence,),readiness=None)),False)


# Independent literal wire order and reference framing from the accepted D2/D4
# contract. No production encoder or catalog column list constructs these rows.
_G3_WORK_NAMES=('work_id','kind','subscription_id','namespace','command_type',
 'schema_version_decimal','runnable_version','canonical_version','scope_evidence',
 'scope_application','scope_tenant','scope_owner','idempotency_key','intent_evidence',
 'semantic_input','replay_input','protected_binding','replay_policy','max_attempts',
 'deadline','original_available_at','state','cancellation_requested','token',
 'ownership_revision','lease_until','available_at','cycle','attempt_count','dispatch_id',
 'result','created_at','updated_at','success_origin','completion_guard_id','final_fence_at',
 'completion_result_digest','resolution_operation_id','terminal_resolution_operation_id')
_G3_HALF_NAMES=('inbox_subscription_id','original_event_id','envelope_evidence','original_replay_input')
_G3_EVENT_JSON=b'{"event_id":"evt","name":"run","schema_version":1,"payload":{"x":1},"metadata":{"m":"v"}}'
_G3_ENVELOPE=bytes.fromhex(
 '4d4b504601000000000000000e6576656e742d656e76656c6f7065000000050000000000000003657674'
 '000000000000000372756e00000000000000013100000000000000206f000000010000000000000001'
 '78000000000000000a6900000000000000013100000000000000206f0000000100000000000000016d'
 '000000000000000a73000000000000000176')


def _g3_frame(tag,values):
    # Test-only F/R grammar, with independently specified field values/order.
    def field(value):return len(value).to_bytes(8,'big')+value
    return b'MKPF\x01'+field(tag)+len(values).to_bytes(4,'big')+b''.join(field(v) for v in values)


def _g3_optional(value):
    return b'0' if value is None else b'1'+len(value).to_bytes(8,'big')+value


def _g3_fixture(*,work=1,kind='inbox',subscription=b'sub',namespace=b'inbox',
                key=b'key',event=b'evt',application=b'app',tenant=None,owner=None,
                cipher=b'cipher'):
    from uuid import UUID
    from datetime import datetime,timezone
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    payload=b'o\0\0\0\1'+b'\0'*7+b'\1x'+b'\0'*7+b'\x0ai'+b'\0'*7+b'\x011'
    metadata=b'o\0\0\0\1'+b'\0'*7+b'\1m'+b'\0'*7+b'\x0as'+b'\0'*7+b'\x01v'
    envelope=_g3_frame(b'event-envelope',(event,b'run',b'1',payload,metadata))
    if event==b'evt':assert envelope==_G3_ENVELOPE
    replay=_G3_EVENT_JSON.replace(b'"evt"',b'"'+event+b'"')
    def optional_scope(value):return b'\0' if value is None else b'\1'+len(value).to_bytes(2,'big')+value
    scope=b'MKSC\1'+len(application).to_bytes(2,'big')+application+optional_scope(tenant)+optional_scope(owner)
    binding=_g3_frame(b'protected-binding',(b'present',_g3_optional(b'c'),_g3_optional(b'k'),b'0',b'retain',_g3_optional(cipher),b'0',b'bound',b'o\0\0\0\0',b'o\0\0\0\0'))
    if kind=='job':subscription=None
    semantic=envelope if kind=='inbox' else payload
    work_replay=replay if kind=='inbox' else b'{"x":1}'
    intent=_g3_frame(b'work-intent',(kind.encode('ascii'),_g3_optional(subscription),namespace,b'run',b'1',b'1',scope,_g3_optional(key),semantic,binding,b'disabled',b'3',b'0',b'2026-01-01T00:00:00.000000Z'))
    data=dict(work_id=UUID(int=work),kind=kind,subscription_id=subscription,namespace=namespace,
      command_type=b'run',schema_version_decimal=b'1',runnable_version=1,canonical_version=1,
      scope_evidence=scope,scope_application=application,scope_tenant=tenant,scope_owner=owner,
      idempotency_key=key,intent_evidence=intent,semantic_input=semantic,replay_input=work_replay,
      protected_binding=binding,replay_policy='disabled',max_attempts=3,deadline=None,
      original_available_at=now,state='queued',cancellation_requested=False,token=None,
      ownership_revision=0,lease_until=None,available_at=now,cycle=1,attempt_count=0,
      dispatch_id=None,result=None,created_at=now,updated_at=now,success_origin=None,
      completion_guard_id=None,final_fence_at=None,completion_result_digest=None,
      resolution_operation_id=None,terminal_resolution_operation_id=None,resolution=None)
    half=dict(zip(_G3_HALF_NAMES,(subscription,event,envelope,replay) if kind=='inbox' else (None,)*4))
    return data,half


def _g3_row(key,data,half,*,present=None):
    row=tuple(data[name] for name in _G3_WORK_NAMES)+(False,)+(None,)*16
    if key=='E16':return row+tuple(half[name] for name in _G3_HALF_NAMES)
    if key=='E34':return row+(data['kind']=='inbox' if present is None else present,)+tuple(half[name] for name in _G3_HALF_NAMES)
    return row


def _g3_request(key,parameters=None):
    from uuid import UUID
    from modkit_events.persistence.catalog import get_statement
    if parameters is None:
        parameters=(b'sub',b'evt') if key=='E16' else (UUID(int=1),'inbox',b'sub',b'inbox',b'run',b'MKSC\1\0\3app\0\0',b'key')
        if key=='E34':parameters+=(b'evt',)
    return B.freeze_request(get_statement(key),parameters,context=B.ReturnContext(expected=(),readiness=None))


def _g3_assert_record(actual,key,data,half):
    cls={'E16':O.InboxObservation,'E17':O.WorkObservation,'E34':O.InboxCandidate}[key]
    assert type(actual) is cls
    assert tuple(getattr(actual,name) for name in _G3_WORK_NAMES)==tuple(data[name] for name in _G3_WORK_NAMES)
    assert actual.resolution is None
    if key!='E17':
        assert tuple(getattr(actual,name) for name in _G3_HALF_NAMES)==tuple(half[name] for name in _G3_HALF_NAMES)
    if key=='E34':assert actual.inbox_half_present is (data['kind']=='inbox')


def test_g3_e16_full_inbox_composition():
    data,half=_g3_fixture();request=_g3_request('E16');row=_g3_row('E16',data,half)
    _g3_assert_record(R.decode_event_rows(request,[row]),'E16',data,half)
    _g3_assert_record(O.InboxObservation(**data,**half),'E16',data,half)
    assert R.decode_event_rows(request,[]) is None
    for rows in ([row,row],[()],[row[:-1]],[row+(None,)]):
        _g1_expect_error(lambda:R.decode_event_rows(request,rows),True)
    for name in _G3_HALF_NAMES:
        for value in (None,b'',b'other'):
            bad=half|{name:value}
            _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row('E16',data,bad)]),True)
            _g1_expect_error(lambda:O.InboxObservation(**data,**bad),True)
    for params in ((b'other',b'evt'),(b'sub',b'other')):
        req=_g3_request('E16',params)
        _g1_expect_error(lambda:R.decode_event_rows(req,[row]),True)
    for index in (0,1):
        for value in (None,b'','sub'):
            params=list(request.parameters);params[index]=value
            _g1_expect_error(lambda:_g3_request('E16',params),False)
    job,jhalf=_g3_fixture(kind='job')
    _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row('E16',job,half)]),True)
    # Canonical-equivalent replay bytes stay distinct and exactly preserved.
    spelling=b'  '+half['original_replay_input']+b'\n'
    changed=half|{'original_replay_input':spelling}
    _g3_assert_record(R.decode_event_rows(request,[_g3_row('E16',data,changed)]),'E16',data,changed)
    for name in ('replay_input','original_replay_input'):
        bad_replay=_G3_EVENT_JSON.replace(b'"v"',b'"w"')
        d=data|{name:bad_replay} if name=='replay_input' else data
        h=half|{name:bad_replay} if name=='original_replay_input' else half
        _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row('E16',d,h)]),True)


def test_g3_e17_direct_scoped_and_split_candidates():
    from uuid import UUID
    request=_g3_request('E17');base,half=_g3_fixture();scoped,shalf=_g3_fixture(work=2)
    assert R.decode_event_rows(request,[])==()
    for data,h in ((base,half),(scoped,shalf)):
        result=R.decode_event_rows(request,[_g3_row('E17',data,h)])
        assert len(result)==1;_g3_assert_record(result[0],'E17',data,h)
    # Direct wrong-kind evidence plus a different scoped ID must both survive.
    direct,dhalf=_g3_fixture(kind='job',namespace=b'other',key=b'other')
    rows=[_g3_row('E17',direct,dhalf),_g3_row('E17',scoped,shalf)]
    result=R.decode_event_rows(request,rows);assert len(result)==2
    for actual,(data,h) in zip(result,((direct,dhalf),(scoped,shalf))):_g3_assert_record(actual,'E17',data,h)
    for bad in ([rows[0],rows[0]],list(reversed(rows)),rows+[rows[1]]):
        _g1_expect_error(lambda:R.decode_event_rows(request,bad),True)
    # Vary one request partition field with a non-direct candidate.
    for index,value in ((2,b'other'),(3,b'other'),(4,b'other'),(5,b'MKSC\1\0\3alt\0\0'),(6,b'other'),(6,None)):
        params=list(request.parameters);params[index]=value;req=_g3_request('E17',params)
        _g1_expect_error(lambda:R.decode_event_rows(req,[_g3_row('E17',scoped,shalf)]),True)
    params=list(request.parameters);params[1]='job';params[2]=None;req=_g3_request('E17',params)
    _g1_expect_error(lambda:R.decode_event_rows(req,[_g3_row('E17',scoped,shalf)]),True)
    params=list(request.parameters);params[6]=None;req=_g3_request('E17',params)
    _g3_assert_record(R.decode_event_rows(req,[_g3_row('E17',base,half)])[0],'E17',base,half)
    unkeyed,uhalf=_g3_fixture(work=2,key=None)
    _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row('E17',unkeyed,uhalf)]),True)
    # Multiple otherwise valid scoped candidates are bounded, never selected away.
    third,thalf=_g3_fixture(work=3)
    _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row('E17',base,half),_g3_row('E17',scoped,shalf),_g3_row('E17',third,thalf)]),True)


def test_g3_e34_three_paths_and_half_truth_table():
    request=_g3_request('E34')
    direct,dhalf=_g3_fixture(kind='job',namespace=b'other',key=b'other')
    scoped,shalf=_g3_fixture(work=2,event=b'alt')
    event,ehalf=_g3_fixture(work=3,namespace=b'other',key=b'other')
    candidates=((direct,dhalf),(scoped,shalf),(event,ehalf))
    rows=[_g3_row('E34',data,half) for data,half in candidates]
    assert R.decode_event_rows(request,[])==()
    for count in (1,2,3):
        actual=R.decode_event_rows(request,rows[:count]);assert len(actual)==count
        for record,(data,half) in zip(actual,candidates):_g3_assert_record(record,'E34',data,half)
    # Each non-direct path independently admits its complete, distinct evidence.
    for data,half in candidates[1:]:_g3_assert_record(R.decode_event_rows(request,[_g3_row('E34',data,half)])[0],'E34',data,half)
    base,bhalf=_g3_fixture()
    _g3_assert_record(R.decode_event_rows(request,[_g3_row('E34',base,bhalf)])[0],'E34',base,bhalf)
    for bad in ([rows[0],rows[0]],list(reversed(rows)),rows+[rows[-1]]):
        _g1_expect_error(lambda:R.decode_event_rows(request,bad),True)
    _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row('E34',direct,dhalf,present=True)]),True)
    for name in _G3_HALF_NAMES:
        h=dhalf|{name:b'unexpected'}
        _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row('E34',direct,h)]),True)
        h=bhalf|{name:None}
        _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row('E34',base,h)]),True)
    for half in (bhalf,dict.fromkeys(_G3_HALF_NAMES)):
        _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row('E34',base,half,present=False)]),True)
    for present in (None,0,1,'true'):
        bad=list(_g3_row('E34',base,bhalf));bad[56]=present
        _g1_expect_error(lambda:R.decode_event_rows(request,[bad]),True)
    unrelated,uhalf=_g3_fixture(work=4,event=b'alt',namespace=b'other',key=b'other')
    _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row('E34',unrelated,uhalf)]),True)
    for index,value in ((2,b'other'),(7,b'other')):
        params=list(request.parameters);params[index]=value;req=_g3_request('E34',params)
        _g1_expect_error(lambda:R.decode_event_rows(req,[rows[2]]),True)
    params=list(request.parameters);params[6]=None;req=_g3_request('E34',params)
    _g3_assert_record(R.decode_event_rows(req,[rows[2]])[0],'E34',event,ehalf)
    _g1_expect_error(lambda:R.decode_event_rows(req,[rows[1]]),True)


def test_g3_immutable_identity_and_protected_evidence():
    from datetime import timedelta
    data,half=_g3_fixture();changed,chalf=_g3_fixture(cipher=b'changed_cipher')
    # This full alternate protected intent is conflict evidence, not corruption.
    for key in ('E16','E17','E34'):
        request=_g3_request(key)
        result=R.decode_event_rows(request,[_g3_row(key,changed,chalf)])
        _g3_assert_record(result if key=='E16' else result[0],key,changed,chalf)
        badfields={'kind':'job','subscription_id':b'other','namespace':b'other',
          'command_type':b'other','schema_version_decimal':b'2','canonical_version':2,
          'scope_evidence':b'MKSC\1\0\3alt\0\0','scope_application':b'alt',
          'scope_tenant':b'tenant','scope_owner':b'owner','idempotency_key':b'other',
          'intent_evidence':data['intent_evidence']+b'x','semantic_input':b'o\0\0\0\0',
          'replay_input':_G3_EVENT_JSON.replace(b'"v"',b'"w"'),
          'protected_binding':changed['protected_binding'],'replay_policy':'application_safe',
          'max_attempts':4,'deadline':data['created_at']+timedelta(seconds=1),
          'original_available_at':data['original_available_at']+timedelta(seconds=1)}
        for name,value in badfields.items():
            bad=data|{name:value}
            _g1_expect_error(lambda:R.decode_event_rows(request,[_g3_row(key,bad,half)]),True)
        bad=list(_g3_row(key,data,half));bad[40]=data['work_id']
        _g1_expect_error(lambda:R.decode_event_rows(request,[bad]),True)


def test_g3_buffers_uuid_utc_and_nullable_scope():
    from datetime import timezone,timedelta
    from dataclasses import FrozenInstanceError
    for key in ('E16','E17','E34'):
        for tenant,owner in ((None,None),(b'tenant',None),(None,b'owner'),(b'tenant',b'owner')):
            data,half=_g3_fixture(application=b'a\0p',tenant=tenant,owner=owner)
            request=_g3_request(key);wire=list(_g3_row(key,data,half));buffers=[]
            for index,value in enumerate(wire):
                if type(value) is bytes:
                    buffer=bytearray(value);buffers.append(buffer)
                    wire[index]=buffer if index%2 else memoryview(buffer)
            wire[0]=str(data['work_id'])
            for index in (20,26,31,32):wire[index]=wire[index].astimezone(timezone(timedelta(hours=2)))
            result=R.decode_event_rows(request,[wire]);actual=result if key=='E16' else result[0]
            for buffer in buffers:buffer[:]=b'x'*len(buffer)
            _g3_assert_record(actual,key,data,half)
            for name in _G3_WORK_NAMES+(() if key=='E17' else _G3_HALF_NAMES):
                if type((data|half).get(name)) is bytes:assert type(getattr(actual,name)) is bytes
            for name in ('original_available_at','available_at','created_at','updated_at'):
                assert getattr(actual,name).tzinfo is timezone.utc
            try:actual.namespace=b'changed'
            except FrozenInstanceError:pass
            else:raise AssertionError('G3 returned mutable record')
        data,half=_g3_fixture();row=_g3_row(key,data,half)
        for index,value in ((0,'00000000000000000000000000000001'),(0,None),(7,True),(20,data['created_at'].replace(tzinfo=None)),(9,'app')):
            bad=list(row);bad[index]=value
            _g1_expect_error(lambda:R.decode_event_rows(request,[bad]),True)


def test_g3_request_context_and_bounded_batches():
    from dataclasses import replace
    from uuid import UUID
    data,half=_g3_fixture()
    fence=M.Fence(work_id=UUID(int=1),token=UUID(int=2),ownership_revision=1,cycle=1,expected_attempt=0)
    for key,maximum in (('E16',1),('E17',2),('E34',3)):
        request=_g3_request(key);row=_g3_row(key,data,half)
        for context in (object(),B.ReturnContext(expected=(fence,),readiness=None)):
            _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=context),False)
        for params in (request.parameters[:-1],request.parameters+(None,)):
            _g1_expect_error(lambda:_g3_request(key,params),False)
        copied=B.freeze_request(replace(request.statement),request.parameters,context=request.context)
        _g1_expect_error(lambda:R.decode_event_rows(copied,[row]),True)
        tampered=replace(request);object.__setattr__(tampered,'parameters',request.parameters[:-1])
        _g1_expect_error(lambda:R.decode_event_rows(tampered,[row]),True)
        for bad in ((),row[:-1],row+(None,)):_g1_expect_error(lambda:R.decode_event_rows(request,[bad]),True)
        seen=[]
        def overflow():
            for index in range(maximum+2):seen.append(index);yield row
        _g1_expect_error(lambda:R.decode_event_rows(request,overflow()),True)
        assert seen==list(range(maximum+1))
        def ordinary():
            yield row
            raise RuntimeError('private read detail')
        _g1_expect_error(lambda:R.decode_event_rows(request,ordinary()),True)
        if maximum>1:
            # A valid first row cannot escape a corrupt later full record.
            other,ohalf=_g3_fixture(work=2);other['intent_evidence']=b'corrupt'
            _g1_expect_error(lambda:R.decode_event_rows(request,[row,_g3_row(key,other,ohalf)]),True)
        class Stop(BaseException):pass
        marker=Stop('primary');marker.add_note('retained')
        def interrupted():
            yield row
            raise marker
        try:R.decode_event_rows(request,interrupted())
        except Stop as caught:assert caught is marker and caught.args==('primary',) and caught.__notes__==['retained']
        else:raise AssertionError('G3 primary replaced')
        params=[bytearray(v) if type(v) is bytes else v for v in request.parameters]
        frozen=_g3_request(key,params)
        for value in params:
            if type(value) is bytearray:value[:]=b'x'*len(value)
        assert frozen.parameters==request.parameters
    for key in ('E17','E34'):
        request=_g3_request(key)
        for index,value in ((0,str(UUID(int=1))),(1,'unknown'),(2,None),(3,None),(4,b''),(5,b'bad'),(6,b'')):
            params=list(request.parameters);params[index]=value
            _g1_expect_error(lambda:_g3_request(key,params),False)
        params=list(request.parameters);params[1]='job';params[2]=None
        if key=='E34':_g1_expect_error(lambda:_g3_request(key,params),False)
        else:assert _g3_request(key,params).parameters==tuple(params)


_G4_OUTBOX_NAMES=('event_id','canonical_version','envelope_evidence','replay_input',
 'state','token','ownership_revision','lease_until','intent_id','receipt',
 'outcome_evidence','created_at','updated_at')
# Fixed SHA256 vectors, independently computed from literal event identity bytes.
_G4_ALT_CURSOR=bytes.fromhex('4d48fba6cf5f7d6abfb35e695f453297870a7a56568ceae968f06d04701b0047')
_G4_EVT_CURSOR=bytes.fromhex('b04f002b6dbff4d1587d0cdcb95c1bc907529786442f4be5385dd87579432541')
_G4_MORE_CURSOR=bytes.fromhex('187897ce0afcf20b50ba2b37dca84a951b7046f29ed5ab94f010619f69d6e189')


def _g4_work(state='claimed',work=1):
    from uuid import UUID
    from datetime import timedelta
    data,_=_g3_fixture(work=work)
    data['state']=state
    if state in ('claimed','running'):
        data.update(token=UUID(int=100+work),ownership_revision=1,
                    lease_until=data['created_at']+timedelta(seconds=30))
    if state in ('running','held'):data.update(dispatch_id=UUID(int=200+work),attempt_count=1)
    if state=='blocked_schema':data['runnable_version']=None
    return data


def _g4_outbox(event=b'alt',state='claimed'):
    from uuid import UUID
    from datetime import timedelta
    work,half=_g3_fixture(event=event)
    owned=state in ('claimed','publishing');intent=state not in ('pending','claimed')
    return dict(event_id=event,canonical_version=1,envelope_evidence=half['envelope_evidence'],
      replay_input=half['original_replay_input'],state=state,token=UUID(int=10) if owned else None,
      ownership_revision=1 if owned else 0,lease_until=work['created_at']+timedelta(seconds=30) if owned else None,
      intent_id=UUID(int=20) if intent else None,receipt=b'' if intent else None,
      outcome_evidence=b'evidence' if intent else None,created_at=work['created_at'],updated_at=work['created_at'])


def _g4_scan_request(key,*,limit=2,budget=4,after=None,namespace=b'inbox',kind='inbox'):
    from modkit_events.persistence.catalog import get_statement
    params={'E04':(namespace,kind,(b'run',),(1,),limit,30,after,budget),
            'E13':(namespace,kind,limit,after,budget),'E22':(limit,30,after,budget),
            'E26':(limit,after,budget)}[key]
    return B.freeze_request(get_statement(key),params,context=B.ReturnContext(expected=(),readiness=None))


def _g4_header(key,visited,cursor,exhausted):
    return ('header',visited,cursor,exhausted)+(None,)*(56 if key in ('E04','E13') else 13)


def _g4_item(key,data):
    values=_g3_row('E17',data,{}) if key in ('E04','E13') else tuple(data[name] for name in _G4_OUTBOX_NAMES)
    return ('item',None,None,None)+values


def _g4_assert_page(page,key,data,visited,cursor,exhausted):
    assert type(page) is O.ScanPage and type(page.items) is tuple
    assert (page.visited,page.next_cursor,page.pass_exhausted)==(visited,cursor,exhausted)
    assert len(page.items)==len(data)
    for actual,expected in zip(page.items,data):
        if key in ('E04','E13'):_g3_assert_record(actual,'E17',expected,{})
        else:
            assert type(actual) is O.OutboxRow
            assert tuple(getattr(actual,name) for name in _G4_OUTBOX_NAMES)==tuple(expected[name] for name in _G4_OUTBOX_NAMES)


def _g4_scan_fixture(key):
    from uuid import UUID
    if key in ('E04','E13'):
        state='claimed' if key=='E04' else 'queued'
        return [_g4_work(state,1),_g4_work(state,2)],UUID(int=0),UUID(int=1),UUID(int=2)
    state='claimed' if key=='E22' else 'pending'
    # Digest order deliberately differs from lexical event-ID order.
    return [_g4_outbox(b'more',state),_g4_outbox(b'evt',state)],b'\0'*32,_G4_MORE_CURSOR,_G4_EVT_CURSOR


def test_g4_work_scan_eligibility_and_partition():
    from uuid import UUID
    key='E04';request=_g4_scan_request(key);records,low,first,last=_g4_scan_fixture(key)
    rows=[_g4_header(key,2,last,False)]+[_g4_item(key,d) for d in records]
    _g4_assert_page(R.decode_event_rows(request,rows),key,records,2,last,False)
    for args in ({'namespace':b'other'},{'kind':'job'}):
        bad=_g4_scan_request(key,**args)
        _g1_expect_error(lambda:R.decode_event_rows(bad,rows),True)
    for commands,versions in (((b'other',),(1,)),((b'run',),(2,)),((b'run',b'other'),(2,1))):
        params=list(request.parameters);params[2]=commands;params[3]=versions
        bad=B.freeze_request(request.statement,params,context=request.context)
        _g1_expect_error(lambda:R.decode_event_rows(bad,rows),True)
    params=list(request.parameters);params[2]=(b'run',b'other');params[3]=(1,2)
    paired=B.freeze_request(request.statement,params,context=request.context)
    _g4_assert_page(R.decode_event_rows(paired,rows),key,records,2,last,False)
    for state in ('queued','running','held','blocked_schema'):
        bad=_g4_work(state)
        _g1_expect_error(lambda:R.decode_event_rows(request,[_g4_header(key,1,first,True),_g4_item(key,bad)]),True)
    # These claimed observations cannot supply an executable/readiness candidate.
    for patch in ({'runnable_version':None},{'cancellation_requested':True},{'attempt_count':3},
                  {'token':None},{'lease_until':None},{'dispatch_id':UUID(int=9)}):
        bad=records[0]|patch
        _g1_expect_error(lambda:R.decode_event_rows(request,[_g4_header(key,1,first,True),_g4_item(key,bad)]),True)
    key='E13';request=_g4_scan_request(key)
    for state in ('queued','expired','failed','cancelled','held'):
        data=_g4_work(state)
        _g4_assert_page(R.decode_event_rows(request,[_g4_header(key,1,first,True),_g4_item(key,data)]),key,[data],1,first,True)
    recovered=[_g4_work('queued',1),_g4_work('held',2)]
    rows=[_g4_header(key,2,last,False)]+[_g4_item(key,d) for d in recovered]
    _g4_assert_page(R.decode_event_rows(request,rows),key,recovered,2,last,False)
    for state in ('claimed','running','retry_waiting','blocked_schema'):
        data=_g4_work(state)
        _g1_expect_error(lambda:R.decode_event_rows(request,[_g4_header(key,1,first,True),_g4_item(key,data)]),True)
    for args in ({'namespace':b'other'},{'kind':'job'}):
        bad=_g4_scan_request(key,**args)
        _g1_expect_error(lambda:R.decode_event_rows(bad,rows),True)


def test_g4_outbox_scan_eligibility_and_evidence():
    from uuid import UUID
    for key in ('E22','E26'):
        request=_g4_scan_request(key);records,low,first,last=_g4_scan_fixture(key)
        if key=='E26':records[1]=_g4_outbox(b'evt','held')
        rows=[_g4_header(key,2,last,False)]+[_g4_item(key,d) for d in records]
        _g4_assert_page(R.decode_event_rows(request,rows),key,records,2,last,False)
        rejected=('pending','publishing','published','rejected','held') if key=='E22' else ('claimed','publishing','published','rejected')
        for state in rejected:
            data=_g4_outbox(b'more',state)
            _g1_expect_error(lambda:R.decode_event_rows(request,[_g4_header(key,1,first,True),_g4_item(key,data)]),True)
        # Keep the evt endpoint valid so ordering cannot mask the ID mismatch.
        identity_header=_g4_header(key,1,_G4_EVT_CURSOR,True)
        coherent=_g4_outbox(b'evt','claimed' if key=='E22' else 'pending')
        _g4_assert_page(R.decode_event_rows(request,[identity_header,_g4_item(key,coherent)]),key,[coherent],1,_G4_EVT_CURSOR,True)
        mismatched=records[0]|{'event_id':b'evt'}
        _g1_expect_error(lambda:R.decode_event_rows(request,[identity_header,_g4_item(key,mismatched)]),True)
        for patch in ({'envelope_evidence':records[0]['envelope_evidence']+b'x'},
                      {'replay_input':records[0]['replay_input'].replace(b'"v"',b'"w"')},
                      {'intent_id':UUID(int=20)}):
            bad=records[0]|patch
            _g1_expect_error(lambda:R.decode_event_rows(request,[_g4_header(key,1,first,True),_g4_item(key,bad)]),True)
    request=_g4_scan_request('E26');held=_g4_outbox(state='held')
    _g4_assert_page(R.decode_event_rows(request,[_g4_header('E26',1,_G4_ALT_CURSOR,True),_g4_item('E26',held)]),'E26',[held],1,_G4_ALT_CURSOR,True)
    for patch in ({'intent_id':None},{'token':UUID(int=9)},{'lease_until':held['created_at']}):
        _g1_expect_error(lambda:R.decode_event_rows(request,[_g4_header('E26',1,_G4_ALT_CURSOR,True),_g4_item('E26',held|patch)]),True)
    request=_g4_scan_request('E22');claimed=_g4_outbox()
    for name in ('token','lease_until'):
        _g1_expect_error(lambda:R.decode_event_rows(request,[_g4_header('E22',1,_G4_ALT_CURSOR,True),_g4_item('E22',claimed|{name:None})]),True)


def test_g4_scan_header_cursor_and_budget():
    from modkit_events.persistence.catalog import RecordKind
    for key in ('E04','E13','E22','E26'):
        request=_g4_scan_request(key);data,low,first,last=_g4_scan_fixture(key)
        items=[_g4_item(key,d) for d in data];header=_g4_header(key,2,last,False)
        for visited,cursor,exhausted in ((0,None,True),(0,None,False),(1,first,True),(1,first,False),(4,last,False)):
            _g4_assert_page(R.decode_event_rows(request,[_g4_header(key,visited,cursor,exhausted)]),key,[],visited,cursor,exhausted)
        after=_g4_scan_request(key,after=low)
        _g4_assert_page(R.decode_event_rows(after,[_g4_header(key,0,low,True)]),key,[],0,low,True)
        _g4_assert_page(R.decode_event_rows(after,[header]+items),key,data,2,last,False)
        invalid_headers=[_g4_header(key,-1,last,False),_g4_header(key,5,last,False),
          _g4_header(key,1,None,True),_g4_header(key,0,last,True),_g4_header(key,4,last,True)]
        for bad in invalid_headers:_g1_expect_error(lambda:R.decode_event_rows(request,[bad]),True)
        for index,value in ((0,'other'),(1,None),(3,None),(3,1),(4,items[0][4])):
            bad=list(header);bad[index]=value
            _g1_expect_error(lambda:R.decode_event_rows(request,[bad]+items),True)
        bad_batches=([],items,[items[0],header],[header,header],
          [_g4_header(key,0,None,False),items[0]],[_g4_header(key,1,last,False)]+items,
          [_g4_header(key,2,last,True)]+items,[header,items[1],items[0]],
          [header,items[0],items[0]],[_g4_header(key,2,first,False)]+items)
        for bad in bad_batches:_g1_expect_error(lambda:R.decode_event_rows(request,bad),True)
        for index,value in ((0,'header'),(1,1),(2,low),(3,False)):
            bad=list(items[0]);bad[index]=value
            _g1_expect_error(lambda:R.decode_event_rows(request,[header,bad]),True)
        after_first=_g4_scan_request(key,after=first)
        _g1_expect_error(lambda:R.decode_event_rows(after_first,[header]+items),True)
        _g1_expect_error(lambda:R.decode_event_rows(after_first,[_g4_header(key,1,first,True)]),True)
        correct=RecordKind.WORK if key in ('E04','E13') else RecordKind.OUTBOX
        wrong=RecordKind.OUTBOX if correct is RecordKind.WORK else RecordKind.WORK
        _g4_assert_page(R.decode_scan_page(request,[header]+items,item_kind=correct),key,data,2,last,False)
        _g1_expect_error(lambda:R.decode_scan_page(request,[header]+items,item_kind=wrong),True)
        one=_g4_scan_request(key,limit=1,budget=1)
        _g4_assert_page(R.decode_event_rows(one,[_g4_header(key,1,first,False),items[0]]),key,[data[0]],1,first,False)
        _g1_expect_error(lambda:R.decode_event_rows(one,[_g4_header(key,1,first,True),items[0]]),True)
        largest=_g4_scan_request(key,limit=256,budget=4096)
        _g4_assert_page(R.decode_event_rows(largest,[_g4_header(key,4096,last,False)]),key,[],4096,last,False)
        for args in ({'limit':0},{'limit':257},{'budget':0},{'budget':4097},{'limit':2,'budget':1}):
            _g1_expect_error(lambda:_g4_scan_request(key,**args),False)
        if key in ('E22','E26'):
            for cursor in (b'',b'x'*31,b'x'*33):
                _g1_expect_error(lambda:_g4_scan_request(key,after=cursor),False)
                _g1_expect_error(lambda:R.decode_event_rows(request,[_g4_header(key,1,cursor,False)]),True)


def _g4_list_request(*,after_time=None,after_work=None,namespace=b'inbox',limit=2):
    from modkit_events.persistence.catalog import get_statement
    return B.freeze_request(get_statement('E30'),(namespace,after_time,after_work,limit),context=B.ReturnContext(expected=(),readiness=None))


def test_g4_e30_keyset_list_boundaries():
    from uuid import UUID
    from datetime import timezone,timedelta
    request=_g4_list_request();first=_g4_work('queued',1);second=_g4_work('held',2)
    rows=[_g3_row('E17',d,{}) for d in (first,second)]
    assert R.decode_event_rows(request,[])==()
    actual=R.decode_event_rows(request,rows);assert len(actual)==2
    for record,data in zip(actual,(first,second)):_g3_assert_record(record,'E17',data,{})
    cursor_time=first['created_at'].astimezone(timezone(timedelta(hours=2)))
    after=_g4_list_request(after_time=cursor_time,after_work=UUID(int=1))
    assert after.parameters[1].tzinfo is timezone.utc
    _g3_assert_record(R.decode_event_rows(after,[rows[1]])[0],'E17',second,{})
    _g1_expect_error(lambda:R.decode_event_rows(after,[rows[0]]),True)
    # Timestamp dominates UUID ordering after the equality tie-break.
    later=first|{'created_at':first['created_at']+timedelta(seconds=1)}
    actual=R.decode_event_rows(request,[rows[1],_g3_row('E17',later,{})]);assert len(actual)==2
    _g3_assert_record(actual[0],'E17',second,{});_g3_assert_record(actual[1],'E17',later,{})
    for bad in ([rows[0],rows[0]],list(reversed(rows)),[_g3_row('E17',later,{}),rows[1]],rows+[rows[1]]):
        _g1_expect_error(lambda:R.decode_event_rows(request,bad),True)
    wrong=_g4_list_request(namespace=b'other')
    _g1_expect_error(lambda:R.decode_event_rows(wrong,rows),True)
    for args in ({'after_time':cursor_time},{'after_work':UUID(int=1)},
                 {'after_time':first['created_at'].replace(tzinfo=None),'after_work':UUID(int=1)}):
        _g1_expect_error(lambda:_g4_list_request(**args),False)
    later_cursor=_g4_list_request(after_time=later['created_at'],after_work=UUID(int=1))
    _g1_expect_error(lambda:R.decode_event_rows(later_cursor,[rows[1]]),True)


def test_g4_bounded_demand_and_late_corruption():
    from collections.abc import Sequence
    class Row(Sequence):
        def __init__(self,values):self.values=values;self.reads=[]
        def __len__(self):return len(self.values)
        def __getitem__(self,index):
            self.reads.append(index)
            if index>=len(self.values):raise IndexError
            return self.values[index]
    for key in ('E04','E13','E22','E26','E30'):
        if key=='E30':
            request=_g4_list_request();data=[_g4_work('queued',1),_g4_work('queued',2)]
            rows=[_g3_row('E17',d,{}) for d in data];maximum=2
        else:
            request=_g4_scan_request(key);data,low,first,last=_g4_scan_fixture(key)
            rows=[_g4_header(key,2,last,False)]+[_g4_item(key,d) for d in data];maximum=3
        seen=[];excess=Row(rows[-1])
        def overflow():
            for index in range(maximum+2):
                seen.append(index);yield rows[index] if index<maximum else excess
        _g1_expect_error(lambda:R.decode_event_rows(request,overflow()),True)
        assert seen==list(range(maximum+1)) and excess.reads==[]
        corrupt=data[1]|({'replay_input':b'{}'} if key in ('E22','E26') else {'intent_evidence':b'corrupt'})
        bad=rows[:-1]+[(_g3_row('E17',corrupt,{}) if key=='E30' else _g4_item(key,corrupt))]
        _g1_expect_error(lambda:R.decode_event_rows(request,bad),True)
        for tail in ((),rows[-1][:-1],rows[-1]+(None,)):
            _g1_expect_error(lambda:R.decode_event_rows(request,rows[:-1]+[tail]),True)
        def broken():
            yield rows[0]
            raise RuntimeError('private scan detail')
        _g1_expect_error(lambda:R.decode_event_rows(request,broken()),True)
        if key=='E30':
            bad=list(rows[1]);bad[40]=data[1]['work_id']
            _g1_expect_error(lambda:R.decode_event_rows(request,[rows[0],bad]),True)
    # ScanFrame plus typed page construction must not reread original Sequences.
    key='E04';request=_g4_scan_request(key);data,low,first,last=_g4_scan_fixture(key)
    values=[_g4_header(key,2,last,False)]+[_g4_item(key,d) for d in data]
    tracked=[Row(value) for value in values]
    _g4_assert_page(R.decode_event_rows(request,tracked),key,data,2,last,False)
    assert all(row.reads==list(range(len(row.values)+1)) for row in tracked)


# G5A: literal scalar/admission/subscription contracts, not database behavior.
_G5A_ADMISSION_NAMES=('work_id','kind','subscription_id','namespace','command_type',
 'scope_evidence','idempotency_key','canonical_version','schema_version_decimal',
 'scope_application','scope_tenant','scope_owner','intent_evidence','semantic_input',
 'replay_input','protected_binding','replay_policy','max_attempts','deadline','original_available_at')
_G5A_SUBSCRIPTION_NAMES=('subscription_id','manifest','consumer_group','capacity',
 'nonterminal_count','created_at')


def _g5a_fixture(key):
    from modkit_events.persistence.catalog import get_statement
    data,half=_g3_fixture()
    empty=B.ReturnContext(expected=(),readiness=None)
    if key in ('E02','E03'):
        event=M.EventInput(event=B.validate_event_replay(_G3_EVENT_JSON),replay_envelope=_G3_EVENT_JSON)
        assert event.event_id_bytes==b'evt' and event.evidence.content==_G3_ENVELOPE
    if key=='E01':
        params=(b'sub',b'manifest',b'group',3);context=empty;row=(True,)
    elif key=='E02':
        params=(b'evt',1,_G3_ENVELOPE,_G3_EVENT_JSON)
        context=B.ReturnContext(expected=(event,),readiness=None);row=(False,)
    elif key=='E03':
        admission=_admission_from_work_fields(data)
        params=tuple(data[n] for n in _G5A_ADMISSION_NAMES)+(b'evt',1,_G3_ENVELOPE,_G3_EVENT_JSON,True,b'broker',b'transport')
        context=B.ReturnContext(expected=(admission,event),readiness=None);row=(data['work_id'],True)
    elif key=='E18':
        params=(b'sub',);context=empty
        row=(b'sub',b'manifest',b'group',3,2,data['created_at'])
    else:raise AssertionError('outside G5A')
    request=B.freeze_request(get_statement(key),params,context=context)
    assert request.parameters==params and request.statement is get_statement(key)
    return request,row


def test_g5a_e01_registration_request_and_unit():
    request,row=_g5a_fixture('E01')
    assert R.decode_event_rows(request,[row]) is True
    for value in (False,0,1,None,'true',b'true'):
        _g1_expect_error(lambda:R.decode_event_rows(request,[(value,)]),True)
    for capacity in (1,2147483647):
        params=request.parameters[:3]+(capacity,)
        assert B.freeze_request(request.statement,params,context=request.context).parameters==params
    for index,value in ((0,b''),(0,b'x'*257),(0,b'\xff'),(0,'sub'),(1,None),
                        (2,b''),(2,b'\xff'),(3,0),(3,-1),(3,2147483648),(3,True),(3,1.0)):
        params=list(request.parameters);params[index]=value
        _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
    # Opaque manifest is not a parsed configuration; exact byte budget still applies.
    for manifest in (b'',b'\x00\xff',b'x'*1048576):
        params=(b'sub',manifest,b'group',1)
        assert B.freeze_request(request.statement,params,context=request.context).parameters==params
    _g1_expect_error(lambda:B.freeze_request(request.statement,(b'sub',b'x'*1048577,b'group',1),context=request.context),False)
    boundary=('é'*128).encode()
    assert B.freeze_request(request.statement,(boundary,b'',boundary,1),context=request.context).parameters==(boundary,b'',boundary,1)
    _g1_expect_error(lambda:B.freeze_request(request.statement,(boundary+b'x',b'',b'group',1),context=request.context),False)


def test_g5a_e02_event_binding_and_boolean():
    request,row=_g5a_fixture('E02')
    for value in (True,False):assert R.decode_event_rows(request,[(value,)]) is value
    class Integer(int):pass
    truthiness=[]
    class Truthy:
        def __bool__(self):truthiness.append(True);return True
    for value in (None,0,1,Integer(1),'false',b'false',Truthy()):
        _g1_expect_error(lambda:R.decode_event_rows(request,[(value,)]),True)
    assert truthiness==[], 'strict boolean decoding consulted truthiness'
    for index,value in ((0,b'other'),(1,2),(1,True),(2,b'other'),(3,b'{}')):
        params=list(request.parameters);params[index]=value
        _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
    # Canonical-equivalent replay is a valid EventInput but not these request bytes.
    alternate=_G3_EVENT_JSON+b' '
    other=M.EventInput(event=B.validate_event_replay(alternate),replay_envelope=alternate)
    assert other.evidence.content==_G3_ENVELOPE
    context=B.ReturnContext(expected=(other,),readiness=None)
    _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=context),False)
    params=request.parameters[:3]+(alternate,)
    assert B.freeze_request(request.statement,params,context=context).parameters==params


def test_g5a_e03_admission_binding_and_inserted_identity():
    from uuid import UUID
    from datetime import timedelta
    request,row=_g5a_fixture('E03')
    # Literal projection/order: no production _admission_values used as expected oracle.
    assert tuple(p.name for p in request.statement.parameters)==_G5A_ADMISSION_NAMES+('event_id','event_canonical_version','envelope_evidence','event_replay_input','supported','broker_reference','transport_observation')
    assert len(request.parameters)==27
    for work,inserted in ((UUID(int=1),True),(UUID(int=1),False),(UUID(int=2),False)):
        result=R.decode_event_rows(request,[(work,inserted)])
        assert type(result) is O.AdmissionRow and result.work_id==work and result.inserted is inserted
    _g1_expect_error(lambda:R.decode_event_rows(request,[(UUID(int=2),True)]),True)
    for value in (0,1,None,'false'):
        _g1_expect_error(lambda:R.decode_event_rows(request,[(UUID(int=1),value)]),True)
    normalized=R.decode_event_rows(request,[(str(UUID(int=1)),True)])
    assert type(normalized.work_id) is UUID and normalized.work_id==UUID(int=1)
    for value in (None,1,'00000000000000000000000000000001'):
        _g1_expect_error(lambda:R.decode_event_rows(request,[(value,False)]),True)
    changes=(UUID(int=2),'job',b'other',b'other',b'other',b'MKSC\1\0\3alt\0\0',
             b'other',2,b'2',b'alt',b'tenant',b'owner',b'other',b'other',
             b'{}',b'other','application_safe',4,request.parameters[19],request.parameters[19]+timedelta(seconds=1))
    assert len(changes)==20
    for index,value in enumerate(changes):
        params=list(request.parameters);params[index]=value
        _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
    for index,value in ((20,b'other'),(21,2),(22,b'other'),(23,b'{}'),(24,1),(24,None),(25,None),(26,'text')):
        params=list(request.parameters);params[index]=value
        _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
    # supported has two valid arms, while broker/transport evidence is opaque.
    for supported in (True,False):
        params=request.parameters[:24]+(supported,b'',b'\0\xff')
        assert B.freeze_request(request.statement,params,context=request.context).parameters==params
    reverse=B.ReturnContext(expected=tuple(reversed(request.context.expected)),readiness=None)
    assert B.freeze_request(request.statement,request.parameters,context=reverse).parameters==request.parameters


def test_g5a_e18_optional_subscription_record():
    from datetime import timezone,timedelta
    from dataclasses import FrozenInstanceError
    request,row=_g5a_fixture('E18')
    assert R.decode_event_rows(request,[]) is None
    assert tuple(c.name for c in request.statement.result.columns)==_G5A_SUBSCRIPTION_NAMES
    for capacity,count in ((1,0),(1,1),(2147483647,2147483647)):
        wire=row[:3]+(capacity,count,row[5])
        result=R.decode_event_rows(request,[wire])
        assert type(result) is O.SubscriptionRow
        assert tuple(getattr(result,n) for n in _G5A_SUBSCRIPTION_NAMES)==wire
    for index,value in ((0,b'other'),(0,b''),(0,b'\xff'),(1,None),(2,b''),(2,b'\xff'),
                        (3,0),(3,2147483648),(3,True),(4,-1),(4,4),(4,True),(4,2**63),
                        (5,None),(5,row[5].replace(tzinfo=None))):
        wire=list(row);wire[index]=value
        if not (index==0 and value==b'other'):
            # Isolate record validity from the separate request-ID coupling.
            _g1_expect_error(lambda:O.SubscriptionRow(**dict(zip(_G5A_SUBSCRIPTION_NAMES,wire))),True)
        _g1_expect_error(lambda:R.decode_event_rows(request,[wire]),True)
    for manifest in (b'',b'\0\xff',b'x'*1048576):
        wire=(row[0],manifest)+row[2:]
        assert R.decode_event_rows(request,[wire]).manifest==manifest
    _g1_expect_error(lambda:R.decode_event_rows(request,[(row[0],b'x'*1048577)+row[2:]]),True)
    buffers=[bytearray(v) for v in row[:3]]
    wire=[buffers[0],memoryview(buffers[1]),buffers[2],3,2,row[5].astimezone(timezone(timedelta(hours=2)))]
    result=R.decode_event_rows(request,[wire])
    for value in buffers:value[:]=b'x'*len(value)
    assert tuple(getattr(result,n) for n in _G5A_SUBSCRIPTION_NAMES)==row
    assert all(type(getattr(result,n)) is bytes for n in _G5A_SUBSCRIPTION_NAMES[:3])
    assert result.created_at.tzinfo is timezone.utc
    try:result.capacity=9
    except FrozenInstanceError:pass
    else:raise AssertionError('mutable subscription observation')
    for value in (None,b'',b'x'*257,b'\xff','sub'):
        _g1_expect_error(lambda:B.freeze_request(request.statement,(value,),context=request.context),False)


def test_g5a_context_descriptor_and_request_snapshot():
    from dataclasses import replace
    from uuid import UUID
    fence=M.Fence(work_id=UUID(int=1),token=UUID(int=2),ownership_revision=1,cycle=1,expected_attempt=0)
    wrong=B.ReturnContext(expected=(fence,),readiness=None)
    for key in ('E01','E02','E03','E18'):
        request,row=_g5a_fixture(key)
        for context in (object(),wrong):
            _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=context),False)
        for params in (request.parameters[:-1],request.parameters+(None,)):
            _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
        copied=B.freeze_request(replace(request.statement),request.parameters,context=request.context)
        _g1_expect_error(lambda:R.decode_event_rows(copied,[row]),True)
        tampered=replace(request);object.__setattr__(tampered,'parameters',request.parameters[:-1])
        _g1_expect_error(lambda:R.decode_event_rows(tampered,[row]),True)
        tampered=replace(request);object.__setattr__(tampered,'context',wrong)
        _g1_expect_error(lambda:R.decode_event_rows(tampered,[row]),True)
        params=[bytearray(v) if type(v) is bytes else v for v in request.parameters]
        frozen=B.freeze_request(request.statement,params,context=request.context)
        for value in params:
            if type(value) is bytearray:value[:]=b'x'*len(value)
        assert frozen.parameters==request.parameters
        for wire in ((),row[:-1],row+(None,)):
            _g1_expect_error(lambda:R.decode_event_rows(request,[wire]),True)
        if key!='E18':_g1_expect_error(lambda:R.decode_event_rows(request,[]),True)
        if key in ('E02','E03'):
            empty=B.ReturnContext(expected=(),readiness=None)
            _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=empty),False)
        if key=='E03':
            for expected in ((request.context.expected[0],),(request.context.expected[1],)):
                context=B.ReturnContext(expected=expected,readiness=None)
                _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=context),False)


def test_g5a_bounded_demand_and_failure_identity():
    from collections.abc import Sequence
    class Counted(Sequence):
        def __init__(self,values,repeat=False):self.values=values;self.reads=[];self.repeat=repeat
        def __len__(self):raise AssertionError('length is not trusted')
        def __getitem__(self,index):
            self.reads.append(index)
            if self.repeat:return self.values[0]
            if index>=len(self.values):raise IndexError
            return self.values[index]
    class Stop(BaseException):pass
    for key in ('E01','E02','E03','E18'):
        request,row=_g5a_fixture(key)
        params=Counted(request.parameters)
        frozen=B.freeze_request(request.statement,params,context=request.context)
        assert frozen.parameters==request.parameters and params.reads==list(range(len(request.parameters)+1))
        params=Counted(request.parameters+(None,None))
        _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
        assert params.reads==list(range(len(request.parameters)+1))
        wire=Counted(row)
        R.decode_event_rows(request,[wire])
        assert wire.reads==list(range(len(row)+1))
        excess=Counted(row);seen=[]
        def overflow():
            for index,value in enumerate((row,excess,row)):
                seen.append(index);yield value
        _g1_expect_error(lambda:R.decode_event_rows(request,overflow()),True)
        assert seen==[0,1] and excess.reads==[]
        huge=Counted((None,),repeat=True)
        _g1_expect_error(lambda:R.decode_event_rows(request,[huge]),True)
        assert huge.reads==list(range(257))
        def late_error():
            yield row
            raise RuntimeError('private iterator detail')
        _g1_expect_error(lambda:R.decode_event_rows(request,late_error()),True)
        marker=Stop('retained primary');cause=RuntimeError('existing cause')
        marker.__cause__=cause;marker.add_note('retained note')
        def late_stop():
            yield row
            raise marker
        try:R.decode_event_rows(request,late_stop())
        except Stop as caught:
            assert caught is marker and caught.__cause__ is cause
            assert caught.args==('retained primary',) and caught.__notes__==['retained note']
        else:raise AssertionError('G5A primary replaced')
        class FailedSequence(Sequence):
            def __len__(self):return 1
            def __getitem__(self,index):raise marker
        for call in (lambda:B.freeze_request(request.statement,FailedSequence(),context=request.context),
                     lambda:R.decode_event_rows(request,[FailedSequence()])):
            try:call()
            except Stop as caught:assert caught is marker and caught.__cause__ is cause
            else:raise AssertionError('G5A sequence primary replaced')


# G5B1: literal E05/E07 Fence/time projections; prospective scoped controls only.
def _g5b1_fixture(key):
    from uuid import UUID
    from datetime import datetime,timezone
    from modkit_events.persistence.catalog import get_statement
    assert key in ('E05','E07')
    fence=M.Fence(work_id=UUID(int=11),token=UUID(int=12),ownership_revision=2,cycle=1,expected_attempt=1)
    instant=datetime(2026,11,6,12,30,45,123456,tzinfo=timezone.utc)
    params=(UUID(int=11),UUID(int=12),2,1,1,30 if key=='E05' else instant)
    request=B.freeze_request(get_statement(key),params,context=B.ReturnContext(expected=(fence,),readiness=None))
    return request,instant


def test_g5b1_e05_fence_lease_and_timestamp():
    from uuid import UUID
    from datetime import datetime,timezone,timedelta
    request,expected=_g5b1_fixture('E05')
    assert tuple(p.name for p in request.statement.parameters)==('work_id','token','ownership_revision','cycle','expected_attempt','lease_seconds')
    assert tuple(c.name for c in request.statement.result.columns)==('lease_until',)
    assert request.parameters==(UUID(int=11),UUID(int=12),2,1,1,30.0)
    assert type(request.parameters[-1]) is float
    for lease in (0.125,1,3600):
        frozen=B.freeze_request(request.statement,request.parameters[:5]+(lease,),context=request.context)
        assert frozen.parameters==request.parameters[:5]+(float(lease),)
        assert type(frozen.parameters[-1]) is float
    for lease in (0,-1,3600.0001,True,False,None,'30',float('nan'),float('inf'),-float('inf')):
        _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters[:5]+(lease,),context=request.context),False)
    offset=datetime(2026,11,6,14,30,45,123456,tzinfo=timezone(timedelta(hours=2)))
    for wire in (expected,offset):
        result=R.decode_event_rows(request,[(wire,)])
        assert type(result) is datetime and result==expected and result.tzinfo is timezone.utc
    for wire in (None,True,0,'2026-11-06T12:30:45Z',expected.replace(tzinfo=None)):
        _g1_expect_error(lambda:R.decode_event_rows(request,[(wire,)]),True)
    for rows in ([],[(expected,),(expected,)],[()],[(expected,None)]):
        _g1_expect_error(lambda:R.decode_event_rows(request,rows),True)


def test_g5b1_e07_fence_available_at_and_unit():
    from uuid import UUID
    from datetime import datetime,timezone,timedelta
    request,expected=_g5b1_fixture('E07')
    assert tuple(p.name for p in request.statement.parameters)==('work_id','token','ownership_revision','cycle','expected_attempt','available_at')
    assert request.parameters==(UUID(int=11),UUID(int=12),2,1,1,expected)
    offset=datetime(2026,11,6,7,0,45,123456,tzinfo=timezone(-timedelta(hours=5,minutes=30)))
    frozen=B.freeze_request(request.statement,request.parameters[:5]+(offset,),context=request.context)
    assert frozen.parameters==request.parameters and frozen.parameters[-1].tzinfo is timezone.utc
    for value in (None,True,0,'2026-11-06T12:30:45Z',expected.replace(tzinfo=None)):
        _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters[:5]+(value,),context=request.context),False)
    assert R.decode_event_rows(request,[(True,)]) is True
    for value in (False,0,1,None,'true'):
        _g1_expect_error(lambda:R.decode_event_rows(request,[(value,)]),True)
    for rows in ([],[(True,),(True,)],[()],[(True,None)]):
        _g1_expect_error(lambda:R.decode_event_rows(request,rows),True)


def test_g5b1_time_context_and_failures():
    from uuid import UUID
    from dataclasses import replace
    from datetime import datetime,tzinfo
    empty=B.ReturnContext(expected=(),readiness=None)
    for key in ('E05','E07'):
        request,instant=_g5b1_fixture(key)
        row=(instant,) if key=='E05' else (True,)
        fence=request.context.expected[0]
        # Each alternative is independently valid; a paired positive isolates equality.
        for index,name,value in ((0,'work_id',UUID(int=21)),(1,'token',UUID(int=22)),
                                 (2,'ownership_revision',3),(4,'expected_attempt',2)):
            params=list(request.parameters);params[index]=value
            _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
            other=replace(fence,**{name:value})
            context=B.ReturnContext(expected=(other,),readiness=None)
            _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=context),False)
            paired=B.freeze_request(request.statement,params,context=context)
            assert paired.parameters==tuple(params)
            assert R.decode_event_rows(paired,[row])==row[0]
        params=list(request.parameters);params[3]=2
        # Cycle is fixed1: this is aggregate domain rejection, not isolated equality.
        _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
        for context in (empty,object()):
            _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=context),False)
        pub=M.PublicationFence(event_id='event',token=UUID(int=12),ownership_revision=2)
        wrong=B.ReturnContext(expected=(pub,),readiness=None)
        _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=wrong),False)
        copied=B.freeze_request(replace(request.statement),request.parameters,context=request.context)
        _g1_expect_error(lambda:R.decode_event_rows(copied,[row]),True)
        tampered=replace(request);object.__setattr__(tampered,'context',empty)
        _g1_expect_error(lambda:R.decode_event_rows(tampered,[row]),True)
        badfence=replace(fence);badcontext=B.ReturnContext(expected=(badfence,),readiness=None)
        object.__setattr__(badfence,'cycle',2)
        _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=badcontext),False)

    # Exercise actual datetime normalization callbacks, not another generic iterator matrix.
    class ClockFailure(tzinfo):
        def __init__(self,error):self.error=error;self.calls=0
        def utcoffset(self,value):self.calls+=1;raise self.error
    class Stop(BaseException):pass
    renew,instant=_g5b1_fixture('E05');release,_=_g5b1_fixture('E07')
    for observed in (False,True):
        def invoke(wire):
            if observed:return R.decode_event_rows(renew,[(wire,)])
            return B.freeze_request(release.statement,release.parameters[:5]+(wire,),context=release.context)
        ordinary=ClockFailure(RuntimeError('private time-hook detail'))
        wire=datetime(2026,11,6,12,30,tzinfo=ordinary)
        _g1_expect_error(lambda:invoke(wire),observed)
        assert ordinary.calls==1
        primary=Stop('retained time primary');cause=RuntimeError('prior cause')
        primary.__cause__=cause;primary.add_note('prior note')
        interrupted=ClockFailure(primary)
        wire=datetime(2026,11,6,12,30,tzinfo=interrupted)
        try:invoke(wire)
        except Stop as caught:
            assert caught is primary and caught.__cause__ is cause
            assert caught.args==('retained time primary',) and caught.__notes__==['prior note']
        else:raise AssertionError('G5B1 time primary replaced')
        assert interrupted.calls==1


# G5B2: actual attempt/failure/cancellation projections, not SQL transition proof.
def _g5b2_fixture(key):
    from uuid import UUID
    from modkit_events.persistence.catalog import get_statement
    assert key in ('E06','E11','E12')
    fence=M.Fence(work_id=UUID(int=11),token=UUID(int=12),ownership_revision=2,cycle=1,expected_attempt=1)
    base=(UUID(int=11),UUID(int=12),2,1,1)
    params={'E06':base+(UUID(int=13),b'effect',b'request',None),
            'E11':base+(7,'failed',None,'failure',b'evidence'),
            'E12':(UUID(int=11),None,None,'cancel')}[key]
    context=B.ReturnContext(expected=() if key=='E12' else (fence,),readiness=None)
    return B.freeze_request(get_statement(key),params,context=context)


def _g5b2_fence_pairs(request):
    from dataclasses import replace
    from uuid import UUID
    fence=request.context.expected[0]
    for index,name,value in ((0,'work_id',UUID(int=21)),(1,'token',UUID(int=22)),
                             (2,'ownership_revision',3),(4,'expected_attempt',2)):
        params=list(request.parameters);params[index]=value
        _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
        context=B.ReturnContext(expected=(replace(fence,**{name:value}),),readiness=None)
        paired=B.freeze_request(request.statement,params,context=context)
        assert paired.parameters==tuple(params)
        row=(paired.parameters[4]+1,) if request.statement.key=='E06' else (True,)
        assert R.decode_event_rows(paired,[row])==row[0]
    params=list(request.parameters);params[3]=2  # aggregate cycle domain, not isolated equality
    _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
    empty=B.ReturnContext(expected=(),readiness=None)
    _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=empty),False)


def test_g5b2_e06_attempt_dispatch_projection():
    from uuid import UUID
    from dataclasses import replace
    request=_g5b2_fixture('E06')
    assert tuple(p.name for p in request.statement.parameters)==('work_id','token','ownership_revision','cycle','expected_attempt','dispatch_id','effect_id','request_evidence','provider_key_reference')
    assert request.parameters==(UUID(int=11),UUID(int=12),2,1,1,UUID(int=13),b'effect',b'request',None)
    _g5b2_fence_pairs(request)
    for prior in (999,1000):
        fence=replace(request.context.expected[0],expected_attempt=prior)
        params=request.parameters[:4]+(prior,)+request.parameters[5:]
        bound=B.freeze_request(request.statement,params,context=B.ReturnContext(expected=(fence,),readiness=None))
        assert bound.parameters[4]==prior  # prior1000 is legal; no successful1001 exists
        if prior==999:assert R.decode_event_rows(bound,[(1000,)])==1000
        else:
            for value in (1000,1001):_g1_expect_error(lambda:R.decode_event_rows(bound,[(value,)]),True)
    for value in (0,1,3,True,None,1001,'2'):
        _g1_expect_error(lambda:R.decode_event_rows(request,[(value,)]),True)
    assert R.decode_event_rows(request,[(2,)])==2
    for rows in ([],[(2,),(2,)],[()],[(2,None)]):
        _g1_expect_error(lambda:R.decode_event_rows(request,rows),True)
    boundary=('é'*128).encode()
    for effect,provider in ((b'effect',None),(boundary,b'provider'),(b'e',boundary)):
        params=request.parameters[:6]+(effect,b'',provider)
        assert B.freeze_request(request.statement,params,context=request.context).parameters==params
    for index,values in ((5,(None,str(UUID(int=13)),1)),
                         (6,(None,b'',b'\xff',boundary+b'x','effect')),
                         (8,(b'',b'\xff',boundary+b'x','provider'))):
        for value in values:
            params=list(request.parameters);params[index]=value
            _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
    for evidence in (b'',b'\0\xff',b'x'*1048576):
        params=request.parameters[:7]+(evidence,None)
        assert B.freeze_request(request.statement,params,context=request.context).parameters==params
    for evidence in (None,'text',b'x'*1048577):
        _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters[:7]+(evidence,None),context=request.context),False)
    effect=bytearray(b'effect');evidence=bytearray(b'request');provider=bytearray(b'provider')
    frozen=B.freeze_request(request.statement,request.parameters[:6]+(effect,memoryview(evidence),provider),context=request.context)
    effect[:]=b'changed';evidence[:]=b'changed';provider[:]=b'changed!'
    assert frozen.parameters[6:]==(b'effect',b'request',b'provider')
    assert all(type(v) is bytes for v in frozen.parameters[6:])


def test_g5b2_e11_failure_root_projection():
    from datetime import datetime,timezone,timedelta
    request=_g5b2_fixture('E11')
    assert tuple(p.name for p in request.statement.parameters)==('work_id','token','ownership_revision','cycle','expected_attempt','failed_business_root','outcome','retry_at','reason','evidence')
    assert request.parameters[5:]==(7,'failed',None,'failure',b'evidence')
    _g5b2_fence_pairs(request)
    utc=datetime(2026,11,6,12,30,tzinfo=timezone.utc)
    offset=datetime(2026,11,6,14,30,tzinfo=timezone(timedelta(hours=2)))
    for root in (1,2**64-1):
        for outcome in ('failed','cancelled','retry_waiting'):
            retry=offset if outcome=='retry_waiting' else None
            params=request.parameters[:5]+(root,outcome,retry,'failure',b'evidence')
            bound=B.freeze_request(request.statement,params,context=request.context)
            assert bound.parameters==request.parameters[:5]+(root,outcome,utc if retry is not None else None,'failure',b'evidence')
            if retry is not None:assert bound.parameters[7].tzinfo is timezone.utc
            assert R.decode_event_rows(bound,[(True,)]) is True
            invalid=params[:7]+(None if retry is not None else utc,)+params[8:]
            _g1_expect_error(lambda:B.freeze_request(request.statement,invalid,context=request.context),False)
    for index,values in ((5,(0,-1,2**64,True,'7',None)),(6,('safe_retry','succeeded',None)),
                         (8,('', 'A','bad-reason','a'*257,None)),(9,(None,'text',b'x'*1048577))):
        for value in values:
            params=list(request.parameters);params[index]=value
            _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
    for reason,evidence in (('a',b''),('a'+'0_'*127+'z',b'\0\xff'),('a'*256,b'x'*1048576)):
        params=request.parameters[:8]+(reason,evidence)
        assert B.freeze_request(request.statement,params,context=request.context).parameters==params
    params=request.parameters[:6]+('retry_waiting',utc.replace(tzinfo=None))+request.parameters[8:]
    _g1_expect_error(lambda:B.freeze_request(request.statement,params,context=request.context),False)
    for rows in ([],[(True,),(True,)],[()],[(True,None)],[(False,)],[(1,)]):
        _g1_expect_error(lambda:R.decode_event_rows(request,rows),True)


def test_g5b2_e12_cancellation_projection():
    from uuid import UUID
    request=_g5b2_fixture('E12')
    assert tuple(p.name for p in request.statement.parameters)==('work_id','expected_token','expected_revision','reason')
    assert request.parameters==(UUID(int=11),None,None,'cancel') and request.context.expected==()
    for token,revision in ((None,None),(UUID(int=12),0),(UUID(int=12),2**63-1)):
        params=(UUID(int=11),token,revision,'cancel')
        bound=B.freeze_request(request.statement,params,context=request.context)
        assert bound.parameters==params
        for state in ('queued','claimed','running','retry_waiting','succeeded','failed','expired','cancelled','blocked_schema','held'):
            assert R.decode_event_rows(bound,[(state,)])==state
    for token,revision in ((None,1),(UUID(int=12),None),(UUID(int=12),-1),(UUID(int=12),2**63),
                           (UUID(int=12),True),(str(UUID(int=12)),1),(1,1)):
        _g1_expect_error(lambda:B.freeze_request(request.statement,(UUID(int=11),token,revision,'cancel'),context=request.context),False)
    for work in (None,str(UUID(int=11)),1):
        _g1_expect_error(lambda:B.freeze_request(request.statement,(work,None,None,'cancel'),context=request.context),False)
    for reason in ('a','a'*256):
        assert B.freeze_request(request.statement,request.parameters[:3]+(reason,),context=request.context).parameters[-1]==reason
    for reason in ('','A','bad-reason','a'*257,None):
        _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters[:3]+(reason,),context=request.context),False)
    wrong=_g5b2_fixture('E06').context
    _g1_expect_error(lambda:B.freeze_request(request.statement,request.parameters,context=wrong),False)
    for value in ('unknown','CANCELLED',b'cancelled',None,True,1):
        _g1_expect_error(lambda:R.decode_event_rows(request,[(value,)]),True)
    for rows in ([],[('cancelled',),('cancelled',)],[()],[('cancelled',None)]):
        _g1_expect_error(lambda:R.decode_event_rows(request,rows),True)
