"""Fixed stages, public RPCs and independently controlled fault injection.

No reliability decision reads the evaluator truth. Both execution backends use
these same stages; only the decision source changes between tape and live mode.
"""
import copy
from trust_network.benchmark.bus import MessageBus
from trust_network.demo.claim_channel import issue
from trust_network.demo.documents import digest
from trust_network.demo.reliability_stage import STAGE_SEMANTICS
from .spec import ARMS,CASES,OWNERS,workload


def collect_packets(value,packets):
    if isinstance(value,dict):
        if isinstance(value.get('body'),dict) and value['body'].get('kind') in ('claim','revoke') and 'signature' in value:
            packets[digest(value)]=copy.deepcopy(value)
        for child in value.values():collect_packets(child,packets)
    elif isinstance(value,list):
        for child in value:collect_packets(child,packets)


class Decisions:
    def __init__(self,backend,mode='replay',tape=None,max_decisions=32,max_attempts=64):
        self.backend=backend;self.mode=mode;self.tape=tape;self.max_decisions=max_decisions
        self.max_attempts=max_attempts;self.records=[];self.attempts=0;self.calls=0

    def choose(self,owner,stage,claims,default,task,derive=False,extra=None):
        response=self.backend.call(owner,{'operation':'reliability_public_view'},sender='decision-input')
        view=response.get('view',{'claims':[],'revocations':[],'blocked':{}})
        claim_id_index={f'task[{i}]':claim for i,claim in enumerate(claims)}
        prompt={'role':'coordinator' if derive else 'receiver','organization':owner,'task':task,
            'required_parent_claims':claims if derive else [],'candidate_claims':{'task':claims},
            'claim_id_index':claim_id_index,
            'evidence_index':{digest(p):{'fact':p['body']['fact'],'issuer':p['signature']['issuer'],
                'parents':p['body']['parents']} for p in view['claims']},
            'public_claims':view['claims'],'known_revocations':view['revocations'],
            'known_fact_disputes':view.get('fact_disputes',{}),'known_blockers':view['blocked'],'stage_semantics':STAGE_SEMANTICS,
            'output_schema':({'action':'proceed|hold','claim_refs':['task[0]'],
                              'fact_ref':'task[0]；由worker按relay原样复制事实，不输出fact','reason':'string'} if derive else
                             {'action':'approve|forward|verify|hold','claim_refs':['task[0]'],'reason':'string'}),
            **(extra or {})}
        if derive:
            # The worker's relay rule is exact equality, not a semantic claim
            # that merely sounds supported. Keep this contract public and
            # identical across all policy arms so a live model can reproduce
            # the packet that the real owner gateway will accept.
            prompt['decision_protocol']='relay-reference-v1'
            prompt['derivation_rule']='relay'
            prompt['derivation_contract']='Use claim_refs and fact_ref to select exact entries from claim_id_index; worker requests an exact JSON copy from owner-local parent evidence and does not accept a repaired ID or fact. Legacy explicit fact is accepted only unchanged, never repaired.'
        row={'owner':owner,'stage':stage,'input_hash':digest(prompt),'public_input':prompt,'origin':'live' if self.mode=='live' else 'fixed_tape' if self.tape is not None else 'scripted'}
        if len(self.records)>=self.max_decisions:
            draft={'action':'hold','reason':'decision_budget_exhausted'};row['status']='budget_exhausted'
        elif self.mode=='live':
            # Reserve two possible provider attempts before authorizing a worker.
            if self.attempts+2>self.max_attempts:
                draft={'action':'hold','reason':'provider_budget_exhausted'};row['status']='budget_exhausted'
            else:
                self.calls+=1
                response=self.backend.call(owner,{'operation':'reliability_model_decision','stage':stage,'model_input':prompt},sender='runtime')
                model=response.get('model_decision',{});row['model']=model
                attempts=model.get('trace',{}).get('attempts')
                self.attempts+=len(attempts) if isinstance(attempts,list) else 2
                row['unknown_attempts']=0 if isinstance(attempts,list) else 2
                draft=model.get('draft') or {'action':'hold','reason':'model_failure'};row['status']=model.get('status','worker_error')
        else:
            # A supplied tape is authoritative. Missing entries never fabricate
            # post-verification approval or recovery decisions.
            draft=(self.tape.get(stage,{'action':'hold','reason':'tape_entry_missing'}) if self.tape is not None else default)
            row['status']='fixed_tape' if self.tape is not None else 'scripted'
        row['draft']=copy.deepcopy(draft);self.records.append(row)
        return draft


class Workflow:
    def __init__(self,backend,case,arm,seed=0,mode='replay',tape=None,max_decisions=32,max_attempts=64):
        if case not in CASES or arm not in ARMS:raise ValueError('unknown experimental factor')
        self.f=workload(seed);self.backend=backend;self.case=case;self.arm=ARMS[arm];self.arm_name=arm
        self.bus=MessageBus();self.packets={};self.scheduled=set();self.batches=[];self.tasks=[]
        self.decisions=Decisions(backend,mode,tape,max_decisions,max_attempts)
        self.truth={'faults':[],'private_facts':{'source':{'actual_cents':125 if case=='signed_false' else 120 if case=='conflicting_sources' else 100}}}
        self.backend.observer=self.observe
        self.retracted=None;self.offer=None;self.corrupted=False

    def observe(self,owner,request,response,sender):
        collect_packets(request,self.packets);collect_packets(response,self.packets)
        self.bus.record('worker_exchange',owner=owner,sender=sender,operation=request['operation'],request=request,response=response)

    def rpc(self,owner,operation,**kwargs):return self.backend.call(owner,{'operation':operation,**kwargs},sender='runtime')

    def queue_notices(self):
        if not self.arm.push:return
        delay=8 if self.case=='late_notice' else 1
        for owner in OWNERS:
            for packet in self.rpc(owner,'reliability_notifications').get('pending',[]):
                nid=digest(packet)
                if nid in self.scheduled:continue
                self.scheduled.add(nid)
                self.bus.send(owner,packet['body']['recipient'],packet,delay,channel='notice')

    def deliver(self,item):
        receiver=item['receiver'];packet=item['payload'];kind=item['channel']
        if kind=='handoff':
            response=self.backend.call(receiver,{'operation':'reliability_handoff_accept','packet':packet},item['sender'])
            receipt=response.get('result')
            if receipt:
                self.bus.record('handoff_registered',owner=receiver,packet=packet,receipt=receipt,
                    claims=packet['body']['claims'],hop=item['hop'],phase=item.get('phase','work'))
                self.bus.send(receiver,item['sender'],receipt,1,channel='handoff_ack')
        elif kind=='notice':
            response=self.backend.call(receiver,{'operation':'reliability_notification_accept','packet':packet},item['sender'])
            if response.get('result'):self.bus.send(receiver,item['sender'],response['result'],1,channel='notice_ack')
        else:
            operation='reliability_handoff_ack' if kind=='handoff_ack' else 'reliability_notification_ack'
            self.backend.call(receiver,{'operation':operation,'packet':packet},item['sender'])
        self.queue_notices()

    def until(self,tick):self.bus.until(max(self.bus.tick,tick),self.deliver)

    def fault(self,target,issuer,kind):
        self.truth['faults'].append({'target':target,'issuer':issuer,'kind':kind,'tick':self.bus.tick,'sequence':len(self.bus.events),'origin_hop':0 if issuer in ('source','buyer') else 1 if issuer=='coordinator' else 2})
        self.bus.record('fault_injection',target=target,issuer=issuer,fault_kind=kind)

    def withdraw(self,owner,target,kind='retraction'):
        result=self.rpc(owner,'reliability_revoke',target=target)
        if result.get('packet'):
            self.fault(target,owner,kind);self.retracted=(owner,target)
        else:self.bus.record('fault_not_realized',owner=owner,target=target,response=result)
        self.queue_notices()

    def derive(self,owner,parents,fact,stage,order,recovery=None):
        default={'action':'proceed','claims':parents,'fact_ref':parents[0],'reason':'依据收到的父证据形成核验意见'}
        draft=self.decisions.choose(owner,stage,parents,default,'审核签名费用依据；有充分依据则提议派生意见，否则hold。',True,
            {'runtime_rebuild_scope':{'envelope':recovery['envelope'],'task_id':recovery['task_id'],
                'completed':recovery['completed'],'old':recovery['node']['old']}} if recovery else None)
        self.bus.record('agent_decision',owner=owner,stage=stage,claims=parents,draft=draft,phase='recovery' if recovery else 'work')
        resolved=self.resolve_claims(draft,parents)
        fact_ref=draft.get('fact_ref')
        claim_index={f'task[{i}]':p for i,p in enumerate(parents)}
        if isinstance(fact_ref,str) and fact_ref in claim_index:
            fact_ref=claim_index[fact_ref]
        if (draft.get('action')!='proceed' or resolved!=parents or
                ('fact' in draft)==('fact_ref' in draft) or
                ('fact' in draft and not isinstance(draft['fact'],dict)) or
                ('fact_ref' in draft and fact_ref not in parents)):
            self.bus.record('stage_not_realized',owner=owner,stage=stage,order=order,
                phase='recovery' if recovery else 'work',reason='model_hold_or_invalid_derived_proposal')
            return None
        fact_args={'fact_ref':fact_ref} if 'fact_ref' in draft else {'fact':draft['fact']}
        if recovery:
            return fact_args
        if owner=='coordinator' and order=='A' and self.case in ('derived_error','missing_dependency'):
            body={'kind':'claim','workflow':self.f['workflow'],'parents':parents,'rule':'relay','fact':copy.deepcopy(draft.get('fact',fact))}
            if self.case=='derived_error':body['fact']['value']['cents']+=7
            else:body['parents']=[]
            # Explicit faulty signing boundary, outside the protected worker.
            packet=issue(owner,self.f['keys'][owner],body)
            self.fault(digest(packet),owner,self.case)
            response=self.rpc(owner,'receive',packet=packet)
            return packet if response.get('event',{}).get('body',{}).get('action')=='received' else None
        packet=self.rpc(owner,'reliability_sign_derived',parents=parents,rule='relay',**fact_args).get('packet')
        if packet is None:
            self.bus.record('stage_not_realized',owner=owner,stage=stage,order=order,
                phase='work',reason='worker_rejected_derived_proposal')
        return packet

    def resolve_claims(self,draft,claims):
        if 'claim_refs' in draft:
            refs=draft.get('claim_refs');index={f'task[{i}]':claim for i,claim in enumerate(claims)}
            if ('claims' in draft or not isinstance(refs,list) or not refs or
                    any(ref not in index for ref in refs) or len(set(refs))!=len(refs)):
                return None
            return [index[ref] for ref in refs]
        return claims if draft.get('claims')==claims else None

    def fixture_or_none(self,packet,fallback):
        """Use a fixture only for scripted replay, never for live state.

        A fallback packet is useful for the deterministic scripted fault cases,
        but it is not present in a real process worker. Reusing it in live mode
        turns a missing local claim into a fake target for later stages.
        Fixed tapes also need the same no-fabrication boundary.
        """
        if packet is not None:return packet
        if self.decisions.mode=='live' or self.decisions.tape is not None:return None
        return fallback

    def batch(self,owner,proposal,stage,recipient=None,hop=0,phase='work'):
        if recipient:
            response=self.rpc(owner,'reliability_handoff_prepare',id=proposal['id'],recipient=recipient,claims=proposal['claims'])
        else:response=self.rpc(owner,'reliability_batch',proposals=[proposal])
        packet=response.get('batch')
        action=packet['body']['outputs'][0]['action'] if packet else 'WORKER_ERROR'
        self.bus.record('action_result',owner=owner,stage=stage,proposal=proposal,action=action,batch=packet,phase=phase)
        if packet:self.batches.append(packet)
        if recipient and action=='COMPLETED':
            handoff=packet['body']['outputs'][0]['result']['handoff']
            self.bus.send(owner,recipient,handoff,1,channel='handoff',hop=hop,phase=phase)
        self.queue_notices()
        return packet

    def act(self,owner,claims,stage,order,recipient=None,hop=0,phase='work'):
        desired='forward' if recipient else 'approve'
        default={'action':desired,'claims':claims,'reason':'提交明确动作，接受运行时门禁'}
        evidence=None
        for turn in range(3):
            name=stage if turn==0 else stage+f':after_verify:{turn}'
            draft=self.decisions.choose(owner,name,claims,default,'决定是否继续转交证据。' if recipient else '决定是否批准账单；verify只查证，不批准账单。',
                extra={'verification_evidence':evidence} if evidence else None)
            self.bus.record('agent_decision',owner=owner,stage=name,claims=claims,draft=draft,phase=phase)
            if draft.get('action')=='hold':return {'action':'MODEL_HOLD','batch':None}
            resolved=self.resolve_claims(draft,claims)
            if draft.get('action') not in (desired,'verify') or resolved!=claims:
                return {'action':'MODEL_INVALID','batch':None}
            proposal={'id':stage,'operation':'forward' if recipient else 'approve_invoice',
                'claims':claims,'intent':'verify' if draft['action']=='verify' else 'execute'}
            if not recipient:proposal['order']=order
            packet=self.batch(owner,proposal,name,recipient if draft['action']!= 'verify' else None,hop,phase)
            if not packet:return {'action':'WORKER_ERROR','batch':None}
            action=packet['body']['outputs'][0]['action']
            if action!='VERIFIED':return {'action':action,'batch':packet}
            evidence=packet
        return {'action':'AWAITING_EXPLICIT_ACTION','batch':evidence}

    def evidence(self,owner,packets):
        for packet in packets:
            self.backend.call(owner,{'operation':'receive','packet':packet},sender='public-evidence-relay')
            self.bus.record('recovery_evidence',owner=owner,claim=digest(packet))

    def recover(self):
        if self.retracted is None:return
        issuer,old=self.retracted;original=self.packets[old]
        self.offer=self.rpc(issuer,'reliability_claim_revision',old=old,fact=original['body']['fact']).get('offer')
        if not self.offer:return
        seed=self.offer['body']['new']
        for task in self.tasks:
            if task['order']!='A' or task['action'] not in ('REQUEST_EVIDENCE','ESCALATE','BLOCKED'):continue
            owner=task['owner'];old_graph=[p for p in list(self.packets.values()) if p['body']['kind']=='claim']
            # Sort public evidence parents before children, not organization state.
            ordered=[];seen=set()
            def visit(p):
                cid=digest(p)
                if cid in seen:return
                for parent in p['body']['parents']:
                    if parent in self.packets:visit(self.packets[parent])
                seen.add(cid);ordered.append(p)
            for p in old_graph:visit(p)
            self.evidence(owner,ordered)
            result=self.rpc(owner,'reliability_closure_recovery',batch=task['batch'],offers=[self.offer])
            envelope=result.get('recovery')
            if not envelope:
                self.bus.record('recovery_stopped',owner=owner,reason='offer_unrelated_or_invalid');continue
            selected=next(t for t in envelope['body']['tasks'] if t['proposal']['id']==task['stage'])
            completed={};mapping=dict(selected['replacement_sources']);error=None
            for _ in range(len(selected['rebuild_required'])+1):
                if self.arm.bound_recovery:
                    state=self.rpc(owner,'reliability_frontier',envelope=envelope,task_id=task['stage'],completed=completed).get('frontier')
                    if state is None:error='completion_evidence_rejected';break
                else:
                    graph={n['old']:n for n in selected['rebuild_required']}
                    ready=[{**n,'parents':[mapping.get(p,p) for p in n['parents']]}
                        for cid,n in graph.items() if cid not in completed and all(p not in graph or p in completed for p in n['parents'])]
                    state={'remaining':len(graph)-len(completed),'ready':ready,'replacement_map':mapping}
                if not state['remaining']:mapping=state['replacement_map'];break
                if not state['ready']:error='recovery_requires_replan';break
                node=state['ready'][0];actor=node['issuer']
                self.evidence(actor,ordered+[seed]+list(completed.values()))
                parents=node['parents'];parent_packet=self.packets[parents[0]]
                fact=self.derive(actor,parents,parent_packet['body']['fact'],task['stage']+':rebuild:'+actor,'A',
                    {'envelope':envelope,'task_id':task['stage'],'completed':completed,'node':node})
                if fact is None:error='recovery_model_hold_or_invalid';break
                if self.arm.bound_recovery:
                    result=self.rpc(actor,'reliability_frontier_rebuild',envelope=envelope,task_id=task['stage'],completed=completed,old=node['old'],**fact)
                    packet=result.get('packet')
                else:
                    # Same structural worker checks, but no recovery task validation.
                    packet=self.rpc(actor,'reliability_sign_derived',parents=parents,rule=node['rule'],**fact).get('packet')
                if packet is None:error='rebuild_rejected';break
                if self.case=='bad_recovery_binding' and not self.corrupted:
                    body={**packet['body'],'supersedes':node['old'],
                        'recovery_binding':{'envelope':digest(envelope),'task_id':'foreign-task'}}
                    packet=issue(actor,self.f['keys'][actor],body);self.rpc(actor,'receive',packet=packet)
                    self.fault(digest(packet),actor,'bad_recovery_binding');self.corrupted=True
                completed[node['old']]=packet;mapping[node['old']]=digest(packet)
                self.evidence(owner,[packet]);self.bus.record('rebuild_completed',owner=actor,claim=digest(packet),task=task['stage'])
                if self.case=='recovery_retraction' and not self.corrupted:
                    response=self.rpc(actor,'reliability_revoke',target=digest(packet))
                    if response.get('packet'):
                        self.fault(digest(packet),actor,'recovery_retraction');self.evidence(owner,[response['packet']]);self.corrupted=True
            if error:
                self.bus.record('recovery_stopped',owner=owner,task=task['stage'],reason=error);continue
            claims=[mapping.get(c,c) for c in task['claims']]
            outcome=self.act(owner,claims,task['stage']+':recovery','A',phase='recovery')
            self.bus.record('task_end',owner=owner,task=task['stage'],order='A',claims=claims,phase='recovery',**outcome)

    def run(self):
        # Authoritative services publish pre-existing documents; these are not
        # counted as model decisions. Five downstream roles make live decisions.
        for order in ('A','C'):
            root=self.f['roots'][order];auth=self.f['auth'][order]
            self.rpc('source','receive',packet=root);self.rpc('buyer','receive',packet=auth)
            self.batch('source',{'id':'publish:'+order,'claims':[digest(root)],'operation':'forward','intent':'execute'},'publish:'+order,'coordinator',1)
            for branch in ('a','b'):
                self.batch('buyer',{'id':'authorize:'+order+branch,'claims':[digest(auth)],'operation':'forward','intent':'execute'},'authorize:'+order+branch,'receiver_'+branch,1)
        if self.case=='signed_false':self.fault(digest(self.f['roots']['A']),'source','signed_false')
        if self.case=='conflicting_sources':
            extra=self.f['conflict'];self.rpc('source','receive',packet=extra);self.rpc('coordinator','receive',packet=extra)
            self.fault(digest(self.f['roots']['A']),'source','conflicting_sources')
        self.until(1);coord={};middle={}
        for order in ('A','C'):
            root=self.f['roots'][order]
            packet=self.derive('coordinator',[digest(root)],root['body']['fact'],'derive:coordinator:'+order,order)
            coord[order]=self.fixture_or_none(packet,self.f['trace'][order]['coordinator'])
            if coord[order] is None:
                for branch in ('a','b'):
                    self.bus.record('stage_skipped',owner='coordinator',stage='forward:coordinator:'+order+branch,
                        order=order,branch=branch,reason='derived_claim_not_realized')
                continue
            for branch in ('a','b'):
                self.act('coordinator',[digest(coord[order])],'forward:coordinator:'+order+branch,order,'middle_'+branch,2)
        self.until(2)
        for branch in ('a','b'):
            for order in ('A','C'):
                owner='middle_'+branch
                if coord[order] is None:
                    middle[(branch,order)]=None
                    self.bus.record('stage_skipped',owner=owner,stage='derive:'+owner+':'+order,
                        order=order,branch=branch,reason='parent_claim_not_realized')
                    continue
                packet=self.derive(owner,[digest(coord[order])],coord[order]['body']['fact'],'derive:'+owner+':'+order,order)
                middle[(branch,order)]=self.fixture_or_none(packet,self.f['trace'][order][owner])
                if middle[(branch,order)] is None:
                    self.bus.record('stage_skipped',owner=owner,stage='forward:'+owner+':'+order,
                        order=order,branch=branch,reason='derived_claim_not_realized')
        self.until(10)
        if self.case in ('root_retraction','intermediate_retraction','branch_retraction','late_notice','bad_recovery_binding','recovery_retraction'):
            owner='source' if self.case=='root_retraction' else 'middle_a' if self.case=='branch_retraction' else 'coordinator'
            target_packet=self.f['roots']['A'] if owner=='source' else middle.get(('a','A')) if owner=='middle_a' else coord.get('A')
            if target_packet is None:
                self.bus.record('fault_not_realized',owner=owner,target=None,
                    reason='retraction_target_claim_not_realized')
            else:
                self.withdraw(owner,digest(target_packet))
        self.until(12)
        for branch in ('a','b'):
            for order in ('A','C'):
                if middle[(branch,order)] is None:
                    self.bus.record('stage_skipped',owner='middle_'+branch,
                        stage='forward:middle_'+branch+':'+order,order=order,branch=branch,
                        reason='derived_claim_not_realized')
                    continue
                self.act('middle_'+branch,[digest(middle[(branch,order)])],
                    'forward:middle_'+branch+':'+order,order,'receiver_'+branch,3)
        self.until(14)
        for branch in ('a','b'):
            for order in ('A','C'):
                owner='receiver_'+branch;stage='invoice:'+order+':'+branch
                if middle[(branch,order)] is None:
                    claims=[]
                    result={'action':'UPSTREAM_NOT_REALIZED','batch':None,
                        'reason':'required_derived_claim_not_realized'}
                else:
                    claims=[digest(middle[(branch,order)]),digest(self.f['auth'][order])]
                    result=self.act(owner,claims,stage,order)
                task={'owner':owner,'stage':stage,'order':order,'claims':claims,**result};self.tasks.append(task)
                self.bus.record('task_end',owner=owner,task=stage,order=order,claims=claims,phase='work',**result)
        self.until(20);self.recover();self.until(40)
        return {'case':self.case,'arm':self.arm_name,'mode':self.decisions.mode,'events':self.bus.events,
            'public_keys':self.f['public'],'packets':self.packets,'batches':self.batches,
            'decisions':self.decisions.records,'model_calls':self.decisions.calls,'provider_attempts':self.decisions.attempts,
            'decision_source':'live' if self.decisions.mode=='live' else 'fixed_tape' if self.decisions.tape is not None else 'scripted',
            'tape_hash':digest(self.decisions.tape) if self.decisions.tape is not None else None,
            'workload_hash':digest({'roots':self.f['roots'],'auth':self.f['auth'],'trace':self.f['trace']}),
            'effects_are_simulated':True},self.truth
