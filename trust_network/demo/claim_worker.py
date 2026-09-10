"""Owner-local persistent claim gateway and real Agent handoff decisions."""
import argparse
import json
import os
import tempfile
from pathlib import Path
import sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from trust_network.demo.claim_channel import ClaimGateway, issue, read
from trust_network.demo.documents import digest
from trust_network.demo.provider import ProviderConfig, ProviderTraceError, complete, complete_traced
from trust_network.demo.reliability_agent_protocol import COMMON_AGENT_SYSTEM


def recovery_receiver(config,gateway,envelope=None):
    """Issuer-local allowlist, supporting shared issuers and two receivers."""
    allowed=config.get('recovery_receivers')
    if allowed is None: allowed=[config.get('recovery_receiver')]
    if not isinstance(allowed,list) or not allowed or not all(isinstance(o,str) for o in allowed):
        raise ValueError('missing local recovery receiver configuration')
    if envelope is None:
        if len(allowed)!=1: raise ValueError('recovery envelope required for multiple receivers')
        return allowed[0]
    signer,_=read(envelope,gateway.public)
    if signer not in allowed: raise ValueError('untrusted recovery receiver')
    return signer


def model_decision(directory, request, env_file, gateway):
    config=json.loads((directory/'config.json').read_text())
    provider=ProviderConfig.load(env_file)
    if 'model_max_tokens' in config:
        from dataclasses import replace
        limit=config['model_max_tokens']
        if type(limit) is not int or limit<=0: raise ValueError('invalid model token limit')
        provider=replace(provider,max_tokens=limit)
    public_input=json.loads(json.dumps(request['model_input']))
    model_input=json.loads(json.dumps(public_input))
    from trust_network.demo.reliability_stage import stage_status
    role=model_input.get('role')
    if role in ('coordinator','middle','receiver'):
        phase='derive' if role in ('coordinator','middle') else 'decide_action'
        claims=model_input.get('required_parent_claims',[]) if phase=='derive' else [
            c for group in model_input.get('candidate_claims',{}).values() for c in group]
        model_input['runtime_stage_status']=stage_status(gateway,phase,claims,
            model_input.get('runtime_rebuild_scope'),
            recovery_receiver(config,gateway,model_input['runtime_rebuild_scope']['envelope'])
            if model_input.get('runtime_rebuild_scope') else None)
        model_input.pop('runtime_rebuild_scope',None)
    model_input['organization_dossier']=(directory/'private.md').read_text()
    user_prompt=json.dumps(model_input,ensure_ascii=False,indent=2)
    error=None; decision=None; usage=None
    try:
        decision,usage,attempts=complete_traced(provider,COMMON_AGENT_SYSTEM,user_prompt)
        status='success'
    except ProviderTraceError as exc:
        attempts=exc.attempts; status='provider_error'
        error={'type':type(exc).__name__,'message':str(exc)}
    except Exception as exc:
        attempts=[]; status='provider_error'
        error={'type':type(exc).__name__,'message':str(exc)}
    trace={'model':provider.model,'base_url':provider.base_url,
           'sampling':{'max_completion_tokens':provider.max_tokens,'temperature':provider.temperature,
                       'reasoning_split':True,**({'thinking':{'type':'disabled'}}
                       if provider.model=='MiniMax-M3' else {})},
           'public_input_hash':digest(public_input),'full_input_hash':digest(model_input),
           'system_prompt':COMMON_AGENT_SYSTEM,'user_prompt':user_prompt,
           'attempts':attempts,'parsed_decision':decision,'usage':usage,'error':error}
    return {'status':status,'model':provider.model,'public_input_hash':digest(public_input),
            'full_input_hash':digest(model_input),'draft':decision,'usage':usage,'trace':trace,
            **({'error':error} if error is not None else {})}


def handle(directory, request, env_file):
    config=json.loads((directory/'config.json').read_text())
    key=Ed25519PrivateKey.from_private_bytes((directory/'signing.key').read_bytes())
    gateway=ClaimGateway(config['owner'],key,config['public_keys'],config['workflow'],config['authorities'])
    path=directory/'channel_state.json'
    if path.exists():
        gateway.restore(json.loads(path.read_text()))
    initial_events=len(gateway.events)
    operation=request['operation']
    if operation=='receive':
        response={'event':gateway.receive(request['packet'])}
    elif operation=='reliability_public_view':
        response={'view':{'claims':list(gateway.claims.values()),'revocations':list(gateway.revoked.values()),
            'blocked':{c:gateway.blockers(c) for c in gateway.claims if gateway.blockers(c)}}}
    elif operation=='reliability_handoff_prepare':
        from trust_network.demo.propagation_notice import prepare_handoff
        from trust_network.demo.network_reliability import ReliabilityConfig,run_batch
        proposal={'id':request['id'],'operation':'forward','intent':'execute','claims':request['claims']}
        def query(owner,query):
            if owner==gateway.owner:
                from trust_network.demo.network_reliability import authority_status
                return authority_status(gateway,query)
            print(json.dumps({'authority':owner,'authority_query':query}),flush=True)
            return json.loads(sys.stdin.readline())['reply']
        response={'batch':run_batch(gateway,[proposal],query,
            lambda p:{'handoff':prepare_handoff(gateway,request['recipient'],p['claims'])},
            ReliabilityConfig(**config.get('reliability',{})),config.get('verification_budget')),
            'events':gateway.events[initial_events:]}
    elif operation in ('reliability_handoff_accept','reliability_handoff_ack',
                       'reliability_notification_accept','reliability_notification_ack'):
        from trust_network.demo.propagation_notice import (accept_handoff,acknowledge_handoff,
                                                          accept_notice,acknowledge_notice)
        handlers={'reliability_handoff_accept':accept_handoff,'reliability_handoff_ack':acknowledge_handoff,
                  'reliability_notification_accept':accept_notice,'reliability_notification_ack':acknowledge_notice}
        response={'result':handlers[operation](gateway,request['packet']),
                  'events':gateway.events[initial_events:]}
    elif operation=='reliability_notifications':
        from trust_network.demo.propagation_notice import pending_notifications,notification_audit
        response={'pending':pending_notifications(gateway),'audit':notification_audit(gateway)}
    elif operation=='reliability_stage_status':
        from trust_network.demo.reliability_stage import stage_status
        response={'stage_status':stage_status(gateway,request['phase'],request['claims'],
            request.get('rebuild_scope'),
            recovery_receiver(config,gateway,request['rebuild_scope']['envelope'])
            if request.get('rebuild_scope') else None)}
    elif operation=='reliability_model_decision':
        response={'model_decision':model_decision(directory,request,env_file,gateway)}
    elif operation=='reliability_sign_derived':
        parents=request['parents']; blockers=[b for p in parents for b in gateway.blockers(p)]
        if blockers:
            response={'event':gateway.record('derived_sign_blocked',parents,blockers)}
        else:
            packet=issue(config['owner'],key,{'kind':'claim','workflow':config['workflow'],
                'fact':request['fact'],'parents':parents,'rule':request.get('rule','relay')})
            checked=gateway.receive(packet)
            response={'event':checked}
            if checked['body']['action']=='received': response['packet']=packet
    elif operation=='reliability_revoke':
        target=request['target']; original=gateway.claims.get(target)
        if original is None or read(original,config['public_keys'])[0]!=config['owner']:
            raise ValueError('authority does not own original claim')
        packet=issue(config['owner'],key,{'kind':'revoke','workflow':config['workflow'],
            'target':target,'original':original})
        response={'packet':packet,'event':gateway.receive(packet)}
    elif operation=='reliability_replacement_source':
        target=request['old']; original=gateway.claims.get(target)
        if original is None or read(original,config['public_keys'])[0]!=config['owner']:
            raise ValueError('authority does not own original claim')
        if original['body']['parents']:
            raise ValueError('replacement source must be a root claim')
        fact=request['new_fact']
        if config['authorities'].get(fact.get('predicate'))!=config['owner']:
            raise ValueError('replacement predicate is not authoritative here')
        packet=issue(config['owner'],key,{'kind':'claim','workflow':config['workflow'],
            'parents':[],'fact':fact})
        if gateway.receive(packet)['body']['action']!='received':
            raise ValueError('replacement source was not accepted locally')
        response={'packet':packet,'event':gateway.events[-1]}
    elif operation in ('handoff','aggregate'):
        parents=request['parents'] if operation=='aggregate' else [request['parent']]
        parent=parents[0]; blockers=[b for p in parents for b in gateway.blockers(p)]
        if blockers:
            response={'event':gateway.record('handoff_blocked',parent,blockers)}
        else:
            system=(directory/'private.md').read_text()+'''
你需要为另一组织安排备件交接。上游fact是有明确来源的事实，不能自行改变。
输出JSON：{"action":"proceed|hold","fact":原fact对象,"instruction":"你建议的具体交接安排与依据"}。
不要把建议包装成其他组织已完成的行为。'''
            if operation=='aggregate':
                system=(directory/'private.md').read_text()+'''
根据签名费用清单和各组织费用，决定是否可以向下游提交总费用，说明交接建议。
输出JSON：{"action":"proceed|hold","fact":{"predicate":"total_charge","value":{"order":"订单","currency":"币种","cents":整数分总额}},"instruction":"安排和依据"}。
不得漏掉清单必需费用，不得将建议描述为已经支付。'''
            raw,usage=complete(ProviderConfig.load(env_file),system,json.dumps({
                'upstream_facts':[gateway.claims[p]['body']['fact'] for p in parents],'task':request['task']},ensure_ascii=False))
            if raw.get('action') not in ('proceed','hold'): raise ValueError('invalid handoff decision')
            packet=issue(config['owner'],key,{'kind':'claim','workflow':config['workflow'],
                'fact':raw.get('fact'),'parents':parents,'rule':'sum_charges' if operation=='aggregate' else 'relay'})
            checked=gateway.receive(packet)
            response={'draft':raw,'usage':usage,'event':checked}
            if checked['body']['action']=='received' and raw['action']=='proceed': response['packet']=packet
            response['decision']=issue(config['owner'],key,{'kind':'agent_decision','workflow':config['workflow'],
                'input_hash':digest(request),'draft':raw,'claim_hash':digest(packet)})
    elif operation=='review_invoice':
        from trust_network.demo.claim_action_contract import approve_invoice
        facts=[gateway.claims[c]['body']['fact'] for c in request['claims'] if c in gateway.claims]
        system=(directory/'private.md').read_text()+'''
审核该订单账单是否可以确认。任务仅是确认账单，不是付款或出库。
结合提供的费用和组织授权，决定approve或hold并说明依据。
输出JSON：{"action":"approve|hold","reason":"你的判断"}。不得自行扩大授权范围。'''
        raw,usage=complete(ProviderConfig.load(env_file),system,json.dumps({'order':request['order'],'facts':facts},ensure_ascii=False))
        if raw.get('action') not in ('approve','hold'): raise ValueError('invalid invoice decision')
        decision=issue(config['owner'],key,{'kind':'invoice_decision','workflow':config['workflow'],
            'request_hash':digest(request),'order':request['order'],'claims':request['claims'],'draft':raw})
        gateway.record('agent_invoice_decision',digest(decision))
        result=None
        if raw['action']=='approve':
            try:
                result=approve_invoice(gateway,request['claims'],request['order'],
                                       lambda:{'simulated_invoice_approval':request['order']})
            except ValueError: pass
        response={'decision':decision,'draft':raw,'usage':usage,'result':result,
                  'event':gateway.events[-1],'events':gateway.events[initial_events:]}
    elif operation=='approve_invoice':
        from trust_network.demo.claim_action_contract import approve_invoice
        result=None
        try:
            result=approve_invoice(gateway,request['claims'],request['order'],
                                   lambda:{'simulated_invoice_approval':request['order']})
        except ValueError: pass
        response={'result':result,'event':gateway.events[-1],'events':gateway.events[initial_events:]}
    elif operation in ('reliability_frontier','reliability_frontier_rebuild'):
        from trust_network.demo.recovery_frontier import frontier,rebuild_frontier_claim
        receiver=recovery_receiver(config,gateway,request['envelope'])
        if operation=='reliability_frontier':
            response={'frontier':frontier(gateway,request['envelope'],request['task_id'],request['completed'],receiver)}
        else:
            response=rebuild_frontier_claim(gateway,request['envelope'],request['task_id'],request['completed'],receiver,request['old'],request['fact'])
        response['events']=gateway.events[initial_events:]
    elif operation=='reliability_claim_revision':
        from trust_network.demo.recovery_closure import revision_offer
        response={'offer':revision_offer(gateway,request['old'],request['fact']),
                  'events':gateway.events[initial_events:]}
    elif operation=='reliability_closure_recovery':
        from trust_network.demo.recovery_closure import prepare_closure_recovery
        response={'recovery':prepare_closure_recovery(gateway,request['batch'],request['offers'])}
        response['events']=gateway.events[initial_events:]
    elif operation=='reliability_recovery':
        from trust_network.demo.reliability_recovery import prepare_recovery
        response={'recovery':prepare_recovery(gateway,request['batch'],request['offers'])}
        response['events']=gateway.events[initial_events:]
    elif operation=='reliability_build_recovery_evidence':
        from trust_network.demo.reliability_recovery import build_recovery_evidence
        response={'evidence':build_recovery_evidence(
            gateway,request['envelope'],request['task'],request['replacement_offer'],
            request['coordinator_registration'],request['replacement_source'])}
    elif operation=='reliability_rebuild_derived':
        from trust_network.demo.reliability_recovery import rebuild_derived_claim
        packet=rebuild_derived_claim(gateway,request['envelope'],request['task'],
                                     request['fact'],request.get('rule'),request.get('evidence'))
        response={'packet':packet,'event':gateway.events[-1],
                  'events':gateway.events[initial_events:]}
    elif operation=='reliability_replacement_offer':
        from trust_network.demo.reliability_recovery import replacement_offer
        response={'offer':replacement_offer(gateway,request['old'],request['new'])}
    elif operation=='reliability_status':
        from trust_network.demo.network_reliability import authority_status
        response={'reply':authority_status(gateway,request['query'])}
    elif operation in ('reliability_plan','reliability_batch'):
        from trust_network.demo.network_reliability import ReliabilityConfig, plan, run_batch
        reliability_config=dict(config.get('reliability',{}))
        # A model may explicitly request freshness verification. This is a
        # shared tool available to every arm; it does not grant an action.
        proposals=json.loads(json.dumps(request['proposals']))
        if operation=='reliability_batch' and request.get('force_verify'):
            reliability_config['policy']=('verify_all_closure' if reliability_config.get('policy') in ('dependency_closure','verify_all_closure') else 'verify_all')
            for proposal in proposals: proposal['intent']='verify'
        policy=ReliabilityConfig(**reliability_config)
        if operation=='reliability_plan':
            response={'plan':plan(gateway,proposals,policy)}
        else:
            def query_reliability(owner,query):
                if owner==gateway.owner:
                    from trust_network.demo.network_reliability import authority_status
                    return authority_status(gateway,query)
                print(json.dumps({'authority':owner,'authority_query':query}),flush=True)
                return json.loads(sys.stdin.readline())['reply']
            response={'batch':run_batch(gateway,proposals,query_reliability,
                lambda p:{'simulated':True,'proposal':p['id'],'operation':p['operation']},
                policy,config.get('verification_budget'))}
        response['events']=gateway.events[initial_events:]
    elif operation=='status':
        query=request['query']; root=query['root']
        if query['kind']!='status_query' or query['workflow']!=config['workflow']:
            raise ValueError('wrong status scope')
        original=gateway.claims.get(root)
        if original is None or read(original,config['public_keys'])[0]!=config['owner']:
            status='unknown'
        else: status='revoked' if gateway.blockers(root) else 'active'
        reply=issue(config['owner'],key,{'kind':'status_reply','query':query,'status':status})
        response={'reply':reply,'event':gateway.record('status_replied',root,[digest(reply),status])}
    elif operation in ('execute','execute_checked'):
        effect=[]
        def query_authority(owner,query):
            print(json.dumps({'authority_query':query,'authority':owner}),flush=True)
            return json.loads(sys.stdin.readline())['reply']
        try:
            if operation=='execute_checked':
                gateway.execute_checked(request['claim'],'release_handoff',query_authority,lambda:effect.append('simulated_release'))
            else: gateway.execute(request['claim'],'release_handoff',lambda:effect.append('simulated_release'))
        except ValueError: pass
        response={'executed':bool(effect),'event':gateway.events[-1],
                  'events':gateway.events[initial_events:] if operation=='execute_checked' else []}
    else: raise ValueError('unsupported operation')
    # Export every emitted signed event, including cascaded outbox entries, so
    # the auditor can follow local predecessor links without artificial gaps.
    response['events']=gateway.events[initial_events:]
    saved=gateway.snapshot()
    # Serial subprocess protocol. This is not a concurrent database service.
    # Publish a packet/ACK only after the same local state (including routes
    # and outbox) is persisted. Atomic replacement survives interrupted writes.
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=directory,prefix='.channel-',delete=False) as stream:
            temporary=stream.name;json.dump(saved,stream);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path);temporary=None
        directory_fd=os.open(directory,os.O_RDONLY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:
        if temporary is not None:os.unlink(temporary)
    return response


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,required=True); args=parser.parse_args()
    print(json.dumps(handle(args.directory,json.loads(sys.stdin.readline()),args.env_file),ensure_ascii=False))
