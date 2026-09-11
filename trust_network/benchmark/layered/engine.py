"""Common logical task tape; policy nodes receive no fault labels or truth."""
import copy
from dataclasses import asdict
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
from trust_network.benchmark.contribution.generalization import build_topology
from trust_network.benchmark.bus import MessageBus
from trust_network.demo.documents import digest, canonical
from trust_network.demo.fact_evidence import scope_key
from .spec import LAYERS, CASES
from .backend import Backend

SYSTEM = ('你是独立组织的业务Agent。只能使用提供的本地消息与工具结果，不知道其他组织的私有状态。'
          '任务资料充分时继续完成，不充分时可verify或hold；不要因一个订单的问题暂停另一订单。'
          '返回JSON对象，action为proceed、verify或hold，reason为简短理由。'
          'proceed仅提交候选，程序仍可能阻断。verify没有业务副作用，后续需重新决定。'
          'claim_refs是动作输入的引用选择，不是证明材料或父链报告。默认直接使用task_claims；如果返回claim_refs，必须只返回本轮claim_id_index中按顺序的全部槽位，不能展开父声明链，不能返回事实、字典或对象。'
          '如果默认使用task_claims，必须省略claim_refs字段；claim_refs为空列表不是默认写法，会被拒绝。'
          'forward和approve_invoice阶段的action只能从允许列表中选择；forward操作要用proceed提交候选，不要返回forward；verify之后仍用proceed或hold，不要返回none。'
          'approve_invoice的claim_refs必须恰好是task[0]（末端费用声明）和task[1]（授权声明）；forward的claim_refs如果出现必须恰好是task[0]。发票仍必须含费用和授权两项。')

RECOVERY_REQUEST_SYSTEM = ('你是独立组织的业务Agent。当前是控制平面的恢复请求阶段，不是发票审批、付款或转交阶段。'
                           '任务已经安全暂停；如果已提供指向该任务来源的CONTRADICTED争议证据、任务绑定完整，'
                           '就应返回request_recovery。CONTRADICTED在此阶段是启动修复的依据，不要求你等待新的CONFIRMED事实；'
                           '新的来源事实和权威确认由后续worker取得。只有争议证据缺失、任务不匹配或claim_refs不完整时才返回hold。'
                           'request_recovery只请求运行时生成verify-only恢复依据，不产生任何业务副作用。'
                           '必须返回JSON对象，包含action、准确的task_id、按顺序完整的claim_refs和简短reason。')

SOURCE_REVISION_SYSTEM = ('你是负责原始事实声明的独立组织Agent。当前是来源修订阶段，不是发票审批。'
                          '只能依据本组织私有事实索引和公开签名的争议证据决定是否提议修订。'
                          '否认证据本身不提供新金额；若本地私有事实索引支持修订，返回propose_revision并引用fact_ref，'
                          '不要抄写fact；资料不足返回hold或request_clarification。worker会重新向独立权威确认候选事实。')

RECOVERY_REBUILD_SYSTEM = ('你是负责当前派生声明的独立组织Agent。当前是恢复图重建阶段，不是业务审批。'
                           'replacement_parent_claims中的新签名父声明由上游组织提供；你不需要等待自己先签发一个父声明，'
                           '而应依据这些父声明签发你负责的新的派生声明。action_authorized=false只表示本阶段不执行业务动作，'
                           '新的父声明可能有意与被撤销的旧父声明事实不同；不得要求它先与旧事实相同。'
                           '不表示不能重建或签发声明。只要新父声明、恢复任务绑定和frontier顺序完整，就返回proceed；'
                           'claim_refs必须按顺序引用本轮task_claims；fact_ref必须恰好引用本轮task_claims中的新父声明，'
                           '不能引用local_view里已有的旧派生声明，也不能抄写、修改或自行生成fact；否则返回hold。')

class Run:
    def __init__(self, topology, case, layer, backend='memory', directory=None, live=False, env_file=None, tape=None, fixture=None):
        if case not in CASES: raise ValueError('unknown scenario')
        self.fixture=fixture
        if fixture is None:
            self.spec = build_topology(topology)
        else:
            from .final_plan import materialize
            self.spec = materialize(fixture)
        business=(fixture or {}).get('business', {})
        self.base_cents=business.get('base_cents',100)
        self.corrected_cents=business.get('corrected_cents',125)
        self.currency=business.get('currency','CNY')
        self.maximum_cents=business.get('maximum_cents',200)
        self.tampered_cents=business.get('tampered_cents',107)
        self.notice_delay=(fixture or {}).get('notice_delay',8 if case=='late_notice' else 1)
        self.case=case;self.layer_name=layer;self.layer=LAYERS[layer]
        self.live=live;self.env_file=env_file;self.tape=tape
        s=self.spec
        buyer = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(digest(['layered','buyer',s['workflow']])))
        s['keys']['buyer']=buyer
        s['public']['buyer']=buyer.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex()
        s['organizations'].append('buyer')
        wrong=case in ('signed_false','conflicting_sources','confirmed_repair','authority_unknown')
        roots={k:p['body']['fact'] for k,p in s['claims'].items() if not p['body']['parents']}
        self.orders=sorted({f['value']['order'] for f in roots.values()})
        registry={scope_key(s['workflow'],f):
                  {'cents':self.corrected_cents if f['value']['order']=='A' and wrong else self.base_cents,'version':'ledger-v1',
                   'status':'unknown' if f['value']['order']=='A' and case=='authority_unknown' else 'confirmed'}
                  for f in roots.values()}
        self.expected_cents={o:self.corrected_cents if o=='A' and wrong else self.base_cents for o in self.orders}
        self.revision_fact=copy.deepcopy(s['claims']['root_A']['body']['fact'])
        self.revision_fact['value']['cents']=self.corrected_cents
        self.revision_fact_ref='source_revision_A_v2'
        self.tamper_ref=next(t['claim_key'] for t in s['tasks'] if t['id']=='A_a')
        self.injections=[]
        configs={}
        for owner in s['organizations']:
            configs[owner]={'owner':owner,'workflow':s['workflow'],'layer':asdict(self.layer),
                'registry':registry if owner=='buyer' else {},'receivers':sorted({t['owner'] for t in s['tasks']}),'allow_paid':live}
            if owner=='source':
                configs[owner]['private_facts']={self.revision_fact_ref:self.revision_fact}
            if self.layer.signed:
                configs[owner].update(public=s['public'],key=s['keys'][owner].private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()).hex())
        self.b=Backend(configs,backend,directory)
        self.refs={};self.packets={};self.bus=MessageBus();self.sent=set()
        self.b.clock=lambda:self.bus.tick
        self.routes=[];self.outcomes=[];self.decisions=[];self.calls=0;self.attempts=0
        self.truth={'affected_tasks':[],'fault_realized':case=='active','fault_tick':None}
        self.first_batches={};self.initial_claims={};self.last_feedback={}
        self.recovery_requests=[];self.recovery_batches={};self.source_revision_record=None;self.recoveries=[]
        self.workload={'topology':topology,'tasks':s['tasks'],'routes':s['routes'],
                       'claims':{k:p['body'] for k,p in s['claims'].items()}}

    def rpc(self,owner,op,**kw): return self.b.call(owner,{'op':op,**kw})
    def identity(self,p): return digest(p) if self.layer.signed else p['id']
    def fact(self,p):return p['body']['fact'] if self.layer.signed else p['fact']

    def issue(self,ref,owner,fact=None,parents=None,revision=None):
        r={'ref':ref}
        if parents is not None:r['parent_refs']=[self.refs[k] for k in parents]
        else:r['fact']=fact
        if revision is not None:r['revision']=revision
        result=self.rpc(owner,'issue',**r)
        if 'packet' not in result:return None
        p=result['packet'];self.refs[ref]=self.identity(p);self.packets[ref]=p
        return p

    def handoff(self,sender,receiver,refs,tamper=False):
        result=self.rpc(sender,'send',recipient=receiver,claims=[self.refs[k] for k in refs])
        if 'packet' not in result:return False
        p=result['packet']
        if tamper:
            self.injections.append({'kind':'tamper','ref':self.tamper_ref,'tick':self.bus.tick})
            if self.layer.signed:
                target=self.refs[self.tamper_ref]
                victim=next(e for e in p['body']['evidence'] if digest(e)==target)
                victim['body']['fact']['value']['cents']=self.tampered_cents
            else:next(m for m in p['messages'] if m['id']==self.refs[self.tamper_ref])['fact']['value']['cents']=self.tampered_cents
        result=self.rpc(receiver,'accept',packet=p)
        accepted=('receipt' in result and (not self.layer.signed or result['receipt']['body']['status']=='accepted'))
        if accepted:self.rpc(sender,'ack',packet=result['receipt'])
        self.routes.append({'sender':sender,'recipient':receiver,'refs':refs,'accepted':accepted,
                            'packet':p,'receipt':result.get('receipt'),'tick':self.bus.tick})
        return accepted

    def seed(self):
        s=self.spec; reverse={digest(p):k for k,p in s['claims'].items()}
        for step in s['routes']:
            for ref in step['claims']:
                if ref not in self.refs:
                    body=s['claims'][ref]['body']
                    parents=[reverse[x] for x in body['parents']]
                    if self.issue(ref,step['sender'],body['fact'],parents if parents else None) is None:
                        raise ValueError('initialization failed to issue '+ref)
            self.handoff(step['sender'],step['receiver'],step['claims'],
                         tamper=self.case=='tampered_handoff' and self.tamper_ref in step['claims'])
        for o in self.orders:
            fact={'predicate':'invoice_authorization','value':{'order':o,'operation':'approve_invoice',
                    'currency':self.currency,'maximum_cents':self.maximum_cents,'approved':True}}
            self.issue('auth_'+o,'buyer',fact)
            for owner in sorted({t['owner'] for t in s['tasks']}):
                self.handoff('buyer',owner,['auth_'+o])
        self.initial_claims=copy.deepcopy(self.refs)
        self.truth['affected_tasks']=[t['id'] for t in s['tasks'] if t['id'].startswith('A')]
        if self.case=='active':self.truth['affected_tasks']=[]
        if self.case=='tampered_handoff':
            self.truth['affected_tasks']=[t['id'] for t in s['tasks'] if t['claim_key']==self.tamper_ref]
            self.truth.update(fault_realized=bool(self.injections),fault_tick=0)
        if self.case in ('signed_false','confirmed_repair','authority_unknown','conflicting_sources'):
            self.truth.update(fault_realized=True,fault_tick=0)
        if self.case=='conflicting_sources':
            fact=copy.deepcopy(s['claims']['root_A']['body']['fact']);fact['value']['cents']=self.corrected_cents
            p=self.issue('conflict','source',fact)
            for owner in sorted({t['owner'] for t in s['tasks']}):
                self.handoff('source',owner,['conflict'])

    def enqueue(self):
        if not self.layer.push:return
        for owner in self.spec['organizations']:
            for p in self.rpc(owner,'pending')['packets']:
                pid=digest(p)
                if pid in self.sent:continue
                self.sent.add(pid)
                self.bus.send(owner,p['body']['recipient'],p,self.notice_delay)

    def deliver(self,item):
        result=self.rpc(item['receiver'],'notice',packet=item['payload'])
        if 'receipt' in result:self.rpc(item['sender'],'notice_ack',packet=result['receipt'])
        self.enqueue()

    def inject(self):
        self.bus.until(10,self.deliver)
        if self.case in ('root_retraction','intermediate_retraction','branch_retraction','late_notice'):
            ref=('root_A' if self.case=='root_retraction' else self.spec['fault_claims'][
                  'branch_middle' if self.case=='branch_retraction' else 'shared_upstream'])
            p=self.spec['claims'][ref];owner=p['signature']['issuer']
            response=self.rpc(owner,'revoke',target=self.refs[ref])
            self.truth.update(fault_realized='packet' in response,fault_tick=10,fault_ref=ref)
            def depends(key):
                return key==ref or any(depends(k) for k,p in self.spec['claims'].items()
                    if digest(p) in self.spec['claims'][key]['body']['parents'])
            self.truth['affected_tasks']=[t['id'] for t in self.spec['tasks'] if depends(t['claim_key'])]
            self.enqueue()
        self.bus.until(12,self.deliver)

    def choose(self,owner,stage,claims,extra=None,system=None,allowed_actions=None):
        allowed_actions=tuple(allowed_actions or ('proceed','verify','hold'))
        view=self.rpc(owner,'view')
        if self.layer.signed:
            view={'claims':[{'ref':digest(p),'issuer':p['signature']['issuer'],
                             'fact':p['body']['fact'],'parents':p['body']['parents'],
                             'signature_available':True} for p in view['claims']],
                  'revocations':[p['body']['target'] for p in view['revocations']],
                  'blocked':view['blocked'],'disputed_claims':list(view['disputes'])}
        claim_id_index={f'task[{i}]':claim for i,claim in enumerate(claims)}
        prompt={'organization':owner,'stage':stage,'task_claims':claims,
                'claim_id_index':claim_id_index,
                'claim_ref_contract':{
                    'field':'claim_refs','default':'omit_to_use_task_claims',
                    'if_present_must_be_exact_ordered_slots':[f'task[{i}]' for i in range(len(claims))],
                    'if_present_must_have_exact_count':len(claims),
                    'do_not_expand_parent_chain':True,
                    'do_not_return_facts_or_evidence_objects':True,
                },
                'local_view':view,
                'last_tool_result':self.last_feedback.get(stage),
                'capabilities':{'verify':True,'programmatic_evidence_checks':self.layer.signed,
                    'bound_recovery':self.layer.recovery},
                'allowed_actions':list(allowed_actions),**(extra or {})}
        if self.live:
            if self.calls>=28 or self.attempts+2>56:
                result={'draft':{'action':'hold','reason':'budget_exhausted'}}
            else:
                self.calls+=1
                result=self.rpc(owner,'decide',input=prompt,system=system or SYSTEM,env_file=str(self.env_file))
                self.attempts+=len(result.get('attempts',[]))
        elif self.tape is not None:
            result={'draft':self.tape.get(stage,{'action':'hold','reason':'tape_entry_missing'})}
        else:result={'draft':{'action':'proceed','reason':'fixed_explicit_proposal'}}
        draft=copy.deepcopy(result.get('draft')) or {'action':'hold','reason':'provider_or_parse_failure'}
        if not isinstance(draft,dict):draft={'action':'hold','reason':'invalid_decision_shape'}
        if self.tape is not None and 'claim_refs' in draft:
            roles={'@total':claims[0] if claims else None,'@authorization':claims[1] if len(claims)>1 else None}
            draft['claim_refs']=[roles.get(c,c) for c in draft['claim_refs']]
        if draft.get('action') not in allowed_actions:
            draft={'action':'hold','reason':'invalid_action'}
        self.decisions.append({'stage':stage,'owner':owner,'public_input':prompt,
                               'input_hash':digest(prompt),'draft':draft,
                               'allowed_actions':list(allowed_actions),
                               'decision_origin':('budget' if draft.get('reason')=='budget_exhausted' else
                                   'provider_failure' if result.get('provider_error') else
                                   'invalid' if draft.get('reason') in ('invalid_action','invalid_decision_shape') else
                                   'model' if self.live else 'fixed'),
                               'model':result if self.live else None})
        return draft

    def forwards(self):
        # Reuse cached claims but execute actual post-fault edges at every hop.
        # A blocked upstream edge never creates a new downstream claim; already
        # cached evidence may still be proposed, which is precisely the hazard.
        entries=[]
        for step in self.spec['routes']:
            for ref in step['claims']:
                terminal=next((t for t in self.spec['tasks']
                    if t['claim_key']==ref and t['owner']==step['receiver']),None)
                t=terminal or {'id':'relay:'+step['label']+':'+ref,'claim_key':ref,'owner':step['receiver']}
                entries.append((t,step['sender']))
        for t,owner in entries:
            ref=t['claim_key'];claims=[self.refs[ref]];stage='forward:'+t['id']
            response={'action':'HOLD'}
            for round_ in range(2):
                name=stage if not round_ else stage+':after_verify'
                draft=self.choose(owner,name,claims,{'recipient':t['owner'],'operation':'forward'})
                if draft['action']=='hold':
                    response={'action':'HOLD','previous_tool_result':response};break
                verify=draft['action']=='verify'
                response=self.rpc(owner,'act',proposal={'id':stage,'operation':'forward',
                    'claims':claims,'intent':'verify' if verify else 'execute'},recipient=t['owner'],verify=verify)
                self.last_feedback[stage+':after_verify']=response
                if not verify:break
            packet=response.get('handoff')
            if response.get('action')=='COMPLETED' and self.layer.signed:
                packet=response['batch']['body']['outputs'][0]['result'].get('handoff')
            if packet:
                packet=copy.deepcopy(packet)
                if self.case=='tampered_handoff' and ref==self.tamper_ref:
                    if self.layer.signed:
                        cid=packet['body']['claims'][0]
                        next(p for p in packet['body']['evidence'] if digest(p)==cid)['body']['fact']['value']['cents']=self.tampered_cents
                    else:packet['messages'][0]['fact']['value']['cents']=self.tampered_cents
                result=self.rpc(t['owner'],'accept',packet=packet)
                if 'receipt' in result:self.rpc(owner,'ack',packet=result['receipt'])
                self.routes.append({'sender':owner,'recipient':t['owner'],'refs':[ref],
                    'accepted':('receipt' in result and (not self.layer.signed or result['receipt']['body']['status']=='accepted')),'packet':packet,'receipt':result.get('receipt'),
                    'tick':self.bus.tick,'phase':'propagation','post_fault_task':t['id']})
            self.outcomes.append({'task':t['id'],'owner':owner,'phase':'forward','tick':self.bus.tick,
                'action':response.get('action','BLOCKED'),'result':response,'claims':claims,'proposed_action':draft['action']})
            self.enqueue()

    def task(self,t,phase='initial',claim=None,extra=None):
        order=self.spec['claims'][t['claim_key']]['body']['fact']['value']['order']
        claims=[claim or self.refs[t['claim_key']],self.refs['auth_'+order]]
        stage=phase+':'+t['id'];proposal={'id':stage,'operation':'approve_invoice','order':order,'claims':claims}
        result={'action':'HOLD'}
        for round_ in range(2):
            draft=self.choose(t['owner'],stage if not round_ else stage+':after_verify',claims,
                              extra=extra)
            if draft['action']=='hold':
                result={'action':'HOLD','previous_tool_result':result};break
            if 'claim_refs' in draft:
                chosen=self._resolve_claim_refs(draft,claims)
                if chosen is None:
                    result={'action':'INVALID','reason':'invalid_claim_refs'};break
                claims=chosen;proposal={**proposal,'claims':claims}
            p={**proposal,'intent':'verify' if draft['action']=='verify' else 'execute'}
            result=self.rpc(t['owner'],'act',proposal=p,verify=draft['action']=='verify')
            self.last_feedback[stage+':after_verify']=result
            if phase=='initial' and 'batch' in result:self.first_batches[t['id']]=result['batch']
            self.enqueue()
            if draft['action']!='verify':break
        if phase=='initial' and 'batch' in result:self.first_batches[t['id']]=result['batch']
        action=result.get('action','BLOCKED')
        self.outcomes.append({'task':t['id'],'owner':t['owner'],'phase':phase,'tick':self.bus.tick,
                              'claims':claims,'action':action,'result':result,'proposed_action':draft['action']})
        return result

    @staticmethod
    def _resolve_claim_refs(draft,claims):
        """Accept only an exact ordered selection or its explicit task aliases."""
        if not isinstance(draft,dict):return None
        refs=draft.get('claim_refs')
        if not isinstance(refs,list) or len(refs)!=len(claims) or len(set(refs))!=len(refs):return None
        # The prompt exposes the concrete local IDs.  A model may return those
        # IDs directly; accepting them is safe only when the whole ordered list
        # is byte-for-byte the controller's expected list.  This is equivalent
        # to task[i] aliases and avoids treating a correct request as malformed.
        if refs==list(claims):return list(claims)
        index={f'task[{i}]':claim for i,claim in enumerate(claims)}
        if any(not isinstance(ref,str) or ref not in index for ref in refs):return None
        resolved=[index[ref] for ref in refs]
        return resolved if resolved==list(claims) else None

    def _find_contradiction_proof(self):
        batches=[*self.first_batches.values(),*self.recovery_batches.values()]
        batches.extend(x.get('response',{}).get('batch') for x in self.b.logs
                       if x.get('response',{}).get('batch'))
        target=self.refs.get('root_A')
        for batch in batches:
            for checks in batch.get('body',{}).get('fact_checks',{}).values():
                for exchange in checks.get('exchanges',[]):
                    if (exchange.get('claim_id')==target and
                            exchange.get('status')=='CONTRADICTED' and exchange.get('reply')):
                        return copy.deepcopy(exchange['reply'])
        return None

    def _request_recovery_live(self,t,proof):
        initial=next((o for o in self.outcomes
                      if o.get('phase')=='initial' and o.get('task')==t['id']),None)
        if initial is None or initial.get('action') not in (
                'HOLD','REQUEST_EVIDENCE','BLOCKED','ESCALATE'):
            return None
        claims=[self.refs[t['claim_key']],self.refs['auth_A']]
        stage='recovery_request:'+t['id']
        extra={
            'role':'receiver',
            'task':('该订单A任务已经安全暂停。此阶段只决定是否创建控制平面的恢复请求，'
                    '不能重新提交approve、forward或任何有业务副作用的动作。'),
            'recovery_request_context':{
                'task_id':stage,'claim_refs':claims,'dispute_target':self.refs['root_A'],
                'initial_action':initial.get('action'),
                'initial_batch_present':t['id'] in self.first_batches,
                'authority_evidence':proof,
                'authority_evidence_status':'CONTRADICTED',
                'recovery_entry_precondition_met':proof is not None,
                'new_confirmation_not_yet_expected':True,
                'request_is_control_plane_only':True,'no_business_effect':True,
            },
            'output_schema':{'action':'request_recovery|hold','task_id':stage,
                             'claim_refs':['exact claim ID 0','exact claim ID 1 or task[i] aliases'],
                             'reason':'string'},
        }
        draft=self.choose(t['owner'],stage,claims,extra=extra,
                          system=RECOVERY_REQUEST_SYSTEM,
                          allowed_actions=('request_recovery','hold'))
        record={'task_id':t['id'],'owner':t['owner'],'stage':stage,
                'initial_action':initial.get('action'),'draft':copy.deepcopy(draft),
                'status':None,'runtime_action':None,'batch':None}
        valid=(draft.get('action')=='request_recovery' and
               draft.get('task_id')==stage and
               self._resolve_claim_refs(draft,claims)==claims)
        if not valid:
            record['status']='model_hold' if draft.get('action')=='hold' else 'model_invalid'
            self.recovery_requests.append(record)
            return record
        proposal={'id':stage,'operation':'approve_invoice','order':'A','claims':claims,
                  'intent':'verify','recovery_request':{
                      'task_id':stage,'claim_refs':claims,
                      'dispute_target':self.refs['root_A'],
                      'no_business_effect':True}}
        result=self.rpc(t['owner'],'act',proposal=proposal,verify=True)
        batch=result.get('batch')
        record['runtime_action']=result.get('action')
        record['result']=result
        record['batch']=batch
        if batch is not None and result.get('action') in ('REQUEST_EVIDENCE','ESCALATE','BLOCKED'):
            record['status']='submitted'
            self.recovery_batches[t['id']]=batch
        elif batch is not None:
            record['status']='runtime_not_blocked'
        else:
            record['status']='worker_error'
        self.recovery_requests.append(record)
        return record

    def _recover_task_live(self,t,offer):
        receiver=t['owner'];basis=self.recovery_batches.get(t['id'])
        recovery={'task_id':t['id'],'owner':receiver,'status':'not_attempted',
                  'request_status':next((r.get('status') for r in self.recovery_requests
                                         if r.get('task_id')==t['id']),None),
                  'envelope':None,'rebuilds':[],'final_action':None}
        if basis is None:
            recovery['reason']='no_submitted_recovery_request'
            self.recoveries.append(recovery)
            return recovery
        response=self.rpc(receiver,'envelope',batch=basis,offer=offer)
        if 'envelope' not in response:
            recovery['status']='envelope_failed';recovery['error']=response
            self.recoveries.append(recovery)
            return recovery
        envelope=response['envelope'];recovery['envelope']=envelope
        recovery['status']='attempted'
        resolution=(offer.get('body',{}).get('fact_resolution',{})
                    if isinstance(offer,dict) else {})
        authority_reply=resolution.get('reply')
        authority_status=(authority_reply.get('body',{}).get('status')
                          if isinstance(authority_reply,dict) else None)
        recovery['authority_confirmation']=authority_status
        recovery_task='recovery_request:'+t['id'];completed={};state={}
        for i in range(16):
            state=self.rpc(receiver,'frontier',envelope=envelope,task=recovery_task,
                           completed=completed,receiver=receiver)
            if 'remaining' not in state:
                recovery['status']='frontier_failed';recovery['error']=state;break
            if not state['remaining']:
                break
            if not state.get('ready'):
                recovery['status']='recovery_requires_replan';break
            node=state['ready'][0];actor=node['issuer']
            evidence=[*basis.get('body',{}).get('evidence',{}).get('claims',[]),
                      offer['body']['new'],*completed.values()]
            for packet in evidence:self.rpc(actor,'receive',packet=packet)
            stage=f'recovery_rebuild:{t["id"]}:{i}'
            parents=list(node['parents'])
            extra={'role':'middle' if actor!='coordinator' else 'coordinator',
                   'recovery_context':{
                       'protocol':'recovery-frontier-v3','envelope_digest':digest(envelope),
                       'task_id':recovery_task,'old_claim':node['old'],'issuer':actor,
                       'replacement_parent_claims':parents,
                       'replacement_parent_is_upstream_signed':True,
                       'replacement_parent_fact_is_authority_confirmed':authority_status=='CONFIRMED',
                       'replacement_parent_fact_may_differ_from_old':True,
                       'old_parent_is_superseded_not_a_required_match':True,
                       'source_revision_authority':{
                           'status':authority_status,
                           'reply':copy.deepcopy(authority_reply),
                       },
                       'current_actor_must_issue_derived_replacement':True,
                       'action_authorized':False,'action_authorized_means_no_business_effect':True,
                       'fresh_status_check_still_required':True,
                       'fact_ref_required':True,'new_fact_is_not_an_input_to_this_stage':True,
                       'fact_ref_must_equal_one_of_task_claims':True,
                       'do_not_use_existing_derived_claim_as_fact_ref':True,
                       'available_operation':'rebuild_derived_claim'},
                   'output_schema':{'action':'proceed|hold','claim_refs':
                                    [f'task[{j}]' for j in range(len(parents))],
                                    'fact_ref':'one of the exact task claim IDs (for this stage, task[0])',
                                    'reason':'string'}}
            draft=self.choose(actor,stage,parents,extra=extra,
                              system=RECOVERY_REBUILD_SYSTEM,
                              allowed_actions=('proceed','hold'))
            step={'old':node['old'],'issuer':actor,'parents':parents,
                  'stage':stage,'draft':copy.deepcopy(draft),'packet':None}
            if (draft.get('action')!='proceed' or
                    self._resolve_claim_refs(draft,parents)!=parents):
                step['status']='model_hold' if draft.get('action')=='hold' else 'model_invalid'
                recovery['rebuilds'].append(step);recovery['status']='rebuild_model_stopped';break
            fact_ref=draft.get('fact_ref')
            index={f'task[{j}]':parent for j,parent in enumerate(parents)}
            fact_ref=index.get(fact_ref,fact_ref)
            if fact_ref not in parents:
                step['status']='model_invalid';recovery['rebuilds'].append(step)
                recovery['status']='rebuild_model_stopped';break
            rebuilt=self.rpc(actor,'rebuild',envelope=envelope,task=recovery_task,
                             completed=completed,receiver=receiver,old=node['old'],
                             fact_ref=fact_ref)
            step['result']=rebuilt
            if 'packet' not in rebuilt:
                step['status']='program_rejected';recovery['rebuilds'].append(step)
                recovery['status']='rebuild_rejected';break
            step['status']='completed';step['packet']=rebuilt['packet']
            recovery['rebuilds'].append(step);completed[node['old']]=rebuilt['packet']
            self.rpc(receiver,'receive',packet=rebuilt['packet'])
        else:
            recovery['status']='recovery_step_budget_exhausted'
        if recovery['status'] in ('rebuild_model_stopped','rebuild_rejected',
                                   'frontier_failed','recovery_requires_replan',
                                   'recovery_step_budget_exhausted'):
            self.recoveries.append(recovery)
            return recovery
        if state.get('remaining')!=0 or state.get('recovery_complete') is not True:
            recovery['status']='rebuild_incomplete';self.recoveries.append(recovery);return recovery
        new=state.get('replacement_map',{}).get(self.refs[t['claim_key']])
        if new is None:
            recovery['status']='replacement_missing';self.recoveries.append(recovery);return recovery
        final_extra={'role':'receiver','recovery_validation':{
            'recovery_complete':True,
            'new_source_authority_confirmation':authority_status,
            'old_source_is_historical_only':True,
            'new_claim':new,
            'fresh_business_status_check_required':True,
            'this_stage_is_the_final_business_decision':True,
        }}
        result=self.task(t,'repaired',new,extra=final_extra);recovery['final_action']=result
        recovery['status']='recovery_completed' if result.get('action')=='COMPLETED' else 'final_model_stopped'
        self.recoveries.append(recovery)
        return recovery

    def _repair_live(self):
        """Expose the recovery control plane to live agents before running it."""
        self.bus.until(20,self.deliver)
        proof=self._find_contradiction_proof()
        candidates=[t for t in self.spec['tasks']
                    if self.spec['claims'][t['claim_key']]['body']['fact']['value']['order']=='A']
        for t in candidates:self._request_recovery_live(t,proof)
        submitted=[t for t in candidates if t['id'] in self.recovery_batches]
        if not submitted:
            self.source_revision_record={'status':'no_model_recovery_request','proof_available':proof is not None}
            return
        proof=self._find_contradiction_proof()
        if proof is None:
            self.source_revision_record={'status':'no_contradiction_proof','proof_available':False}
            return
        revision_extra={'role':'source','revision_context':{
            'old_claim_id':self.refs['root_A'],'old_public_fact':
                self.spec['claims']['root_A']['body']['fact'],'dispute_proof':proof,
                'authority_reply_status':'CONTRADICTED',
                'authority_reply_contains_replacement_amount':False,
                'new_fact_must_come_from_source_private_fact_ref':True,
                'private_fact_index':{self.revision_fact_ref:{
                    'predicate':'total_charge','order':'A','currency':self.currency,
                    'cents':self.revision_fact['value']['cents'],'version':'v2'}},
                'candidate_confirmation_required_by_worker':True,
                'recovery_request_task_ids':[t['id'] for t in submitted]},
            'output_schema':{'action':'propose_revision|hold|request_clarification',
                             'fact_ref':self.revision_fact_ref,'reason':'string'},
            'decision_protocol':'dispute-revision-v1'}
        draft=self.choose('source','repair:source',[],extra=revision_extra,
                          system=SOURCE_REVISION_SYSTEM,
                          allowed_actions=('propose_revision','hold','request_clarification'))
        record={'status':None,'draft':copy.deepcopy(draft),'offer':None,
                'proof_available':True,'requested_tasks':[t['id'] for t in submitted]}
        self.source_revision_record=record
        if draft.get('action')!='propose_revision' or draft.get('fact_ref')!=self.revision_fact_ref:
            record['status']='model_hold_or_invalid'
            return
        response=self.rpc('source','revision',proof=proof,fact_ref=draft['fact_ref'])
        record['revision_response']=response;offer=response.get('offer')
        if offer is None:
            record['status']='revision_rejected_or_unknown';return
        record['offer']=offer;record['status']='confirmed_offer'
        for t in submitted:self._recover_task_live(t,offer)

    def repair(self):
        # Same source business correction becomes available to every layer at tick 20.
        self.bus.until(20,self.deliver)
        fact=copy.deepcopy(self.spec['claims']['root_A']['body']['fact']);fact['value']['cents']=self.corrected_cents
        draft=self.choose('source','repair:source',[],{'own_business_revision':fact})
        if draft['action']!='proceed':return
        if self.layer.recovery and self.layer.facts:
            proof=None
            # Public authority replies already returned to collaborating actors;
            # relay them explicitly to the source, never inspect its registry.
            public_batches=[x['response']['batch'] for x in self.b.logs if 'batch' in x['response']]
            for b in public_batches:
                for checks in b['body'].get('fact_checks',{}).values():
                    for e in checks['exchanges']:
                        if e.get('status')=='CONTRADICTED' and e['claim_id']==self.refs['root_A']:
                            proof=e['reply'];break
            if proof is None:return
            response=self.rpc('source','revision',proof=proof,fact=fact)
            if 'offer' not in response:return
            offer=response['offer']
            for t in self.spec['tasks']:
                if self.spec['claims'][t['claim_key']]['body']['fact']['value']['order']!=fact['value']['order']:continue
                batch=self.first_batches.get(t['id'])
                if batch is None:continue
                response=self.rpc(t['owner'],'envelope',batch=batch,offer=offer)
                if 'envelope' not in response:continue
                envelope=response['envelope'];completed={};state={}
                for i in range(16):
                    state=self.rpc(t['owner'],'frontier',envelope=envelope,task='initial:'+t['id'],
                                   completed=completed,receiver=t['owner'])
                    if 'remaining' not in state:break
                    if not state['remaining']:break
                    if not state.get('ready'):break
                    node=state['ready'][0];owner=node['issuer']
                    for packet in [*batch['body']['evidence']['claims'],offer['body']['new'],*completed.values()]:
                        self.rpc(owner,'receive',packet=packet)
                    draft=self.choose(owner,'repair:'+t['id']+':'+str(i),node['parents'])
                    if draft['action']!='proceed':break
                    rebuilt=self.rpc(owner,'rebuild',envelope=envelope,task='initial:'+t['id'],completed=completed,
                                     receiver=t['owner'],old=node['old'])
                    if 'packet' not in rebuilt:break
                    completed[node['old']]=rebuilt['packet']
                    self.rpc(t['owner'],'receive',packet=rebuilt['packet'])
                if state.get('remaining')==0 and state.get('recovery_complete') is True:
                    new=state['replacement_map'].get(self.refs[t['claim_key']])
                    if new:self.task(t,'repaired',new)
        else:
            # Ordinary re-publication remains possible at every lower layer.
            reverse={digest(p):k for k,p in self.spec['claims'].items()};newrefs={}
            p=self.issue('revision:root_A','source',fact,revision='v2')
            if p is None:return
            newrefs['root_A']='revision:root_A'
            for step in self.spec['routes']:
                send=[]
                for ref in step['claims']:
                    old=self.spec['claims'][ref]['body'];parents=[reverse[c] for c in old['parents']]
                    if old['fact']['value']['order']!='A':continue
                    if ref not in newrefs:
                        if not all(x in newrefs for x in parents):continue
                        owner=step['sender']
                        new='revision:'+ref
                        if self.choose(owner,'repair:derive:'+ref,[self.refs[newrefs[x]] for x in parents])['action']!='proceed':continue
                        if self.issue(new,owner,parents=[newrefs[x] for x in parents],revision='v2') is None:continue
                        newrefs[ref]=new
                    send.append(newrefs[ref])
                if send:self.handoff(step['sender'],step['receiver'],send)
            for t in self.spec['tasks']:
                if t['claim_key'] in newrefs:self.task(t,'repaired',self.refs[newrefs[t['claim_key']]])

    def run(self):
        try:
            self.seed();self.inject();self.forwards()
            for t in self.spec['tasks']:self.task(t)
            if self.case=='confirmed_repair':
                if self.live and self.layer.recovery and self.layer.facts:self._repair_live()
                else:self.repair()
            self.bus.until(30,self.deliver)
            reverse={digest(p):k for k,p in self.spec['claims'].items()}
            def lineage(k):
                return {self.initial_claims[k]}.union(*(lineage(reverse[c]) for c in self.spec['claims'][k]['body']['parents']))
            self.truth['task_lineage']={t['id']:sorted(lineage(t['claim_key'])) for t in self.spec['tasks']}
            self.truth['expected_cents']=self.expected_cents
            self.truth['invalid_claim_ids']=[]
            if self.truth.get('fault_ref'):
                target=self.truth['fault_ref'];reverse={digest(p):k for k,p in self.spec['claims'].items()}
                def tainted(k):
                    return k==target or any(tainted(reverse[c]) for c in self.spec['claims'][k]['body']['parents'])
                self.truth['invalid_claim_ids']=[self.initial_claims[k] for k in self.spec['claims'] if tainted(k)]
            exports={o:self.rpc(o,'export') for o in self.spec['organizations']}
            from .score import score
            raw={'topology':self.spec['topology'],'case':self.case,'layer':self.layer_name,
                 'configuration':asdict(self.layer),'mode':'live' if self.live else 'fixed_tape' if self.tape is not None else 'scripted',
                 'workload_hash':digest(self.workload),'event_tape_hash':digest([self.case,10,12,20,30,self.notice_delay]),
                 'proposal_tape_hash':digest(self.tape if self.tape is not None else ['fixed',self.spec['tasks']]),
                 'workflow':self.spec['workflow'],'public_keys':self.spec['public'] if self.layer.signed else {},
                 'truth':self.truth,'injections':self.injections,'reference_ids':self.initial_claims,'tasks':self.spec['tasks'],'outcomes':self.outcomes,'routes':self.routes,
                 'recovery_requests':self.recovery_requests,'source_revision':self.source_revision_record,
                 'recoveries':self.recoveries,
                 'decisions':self.decisions,'exchanges':self.b.logs,'transport':self.bus.events,'exports':exports,
                 'new_model_calls':self.calls,'provider_attempts':self.attempts,
                 'limits':['seeded_graph_not_model_generated_upstream','synchronous_rpc_queries_zero_simulated_latency',
                           'business_effects_simulated','no_physical_or_legal_responsibility_claim']}
            raw['metrics']=score(raw)
            return raw
        finally:self.b.close()
