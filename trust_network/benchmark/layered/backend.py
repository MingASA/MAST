"""Identical RPC logic in memory and isolated persistent organization workers."""
import copy
import json
import subprocess
import sys
from pathlib import Path
from dataclasses import replace
from trust_network.demo.documents import digest
from trust_network.demo.claim_action_contract import validate_invoice_facts
from .spec import Layer, AUTHORITIES

class Node:
    def __init__(self, config):
        self.config = config
        self.owner = config['owner']
        self.layer = Layer(**config['layer'])
        self.messages = {}
        self.revoked = set()
        self.log = []
        self.g = None
        self.effects = []
        self.batches = []
        if self.layer.signed:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from trust_network.demo.claim_channel import ClaimGateway
            self.g = ClaimGateway(self.owner, Ed25519PrivateKey.from_private_bytes(bytes.fromhex(config['key'])),
                config['public'], config['workflow'], AUTHORITIES, {'settlement_basis_v1':'buyer'})

    def call(self, r, query):
        # Public candidate facts captured before any check; evaluator-only use.
        candidates={}
        if r.get('op')=='act':
            for cid in r['proposal'].get('claims',[]):
                packet=(self.g.claims if self.g else self.messages).get(cid)
                if packet:
                    candidates[cid]=copy.deepcopy(packet['body']['fact'] if self.g else packet['fact'])
        result=self._call(r,query)
        if r.get('op')=='act':result['candidate_facts']=candidates
        return result

    def _call(self, r, query):
        from trust_network.demo.claim_channel import issue
        from trust_network.demo.network_reliability import run_batch, ReliabilityConfig, authority_status
        from trust_network.demo.propagation_notice import (prepare_handoff, accept_handoff, acknowledge_handoff,
            accept_notice, acknowledge_notice, pending_notifications)
        op = r['op']; g = self.g
        if op == 'receive':
            p = r['packet']
            if g:
                return {'event':g.receive(p)}
            if not isinstance(p.get('fact'),dict) or not isinstance(p.get('id'),str):
                raise ValueError('invalid ordinary message')
            self.messages[p['id']] = copy.deepcopy(p)
            return {'accepted':True}
        if op == 'issue':
            fact = r.get('fact')
            if 'parent_refs' in r:
                parents = r['parent_refs']
                first = g.claims[parents[0]]['body']['fact'] if g else self.messages[parents[0]]['fact']
                fact = copy.deepcopy(first)
            if g:
                p = issue(self.owner, g.key, {'kind':'claim','workflow':g.workflow,
                    'parents':r.get('parent_refs',[]),'rule':'relay','fact':fact,
                    **({'revision':r['revision']} if 'revision' in r else {})})
                if g.receive(p)['body']['action'] != 'received':
                    raise ValueError('invalid issued claim')
            else:
                p = {'id':r['ref'],'sender':self.owner,'fact':fact}
                self.messages[p['id']] = p
            return {'packet':p}
        if op == 'send':
            if g:
                return {'packet':prepare_handoff(g,r['recipient'],r['claims'])}
            return {'packet':{'sender':self.owner,'recipient':r['recipient'],
                             'messages':[self.messages[c] for c in r['claims']]}}
        if op == 'accept':
            if g:
                return {'receipt':accept_handoff(g,r['packet'])}
            p = r['packet']
            if p['recipient'] != self.owner:
                raise ValueError('wrong recipient')
            for msg in p['messages']:
                self.call({'op':'receive','packet':msg},query)
            return {'receipt':{'sender':p['sender'],'recipient':self.owner,'accepted':True}}
        if op == 'ack':
            return acknowledge_handoff(g,r['packet']) if g else {'ack':True}
        if op == 'revoke':
            if g:
                old = g.claims[r['target']]
                if old['signature']['issuer'] != self.owner:
                    raise ValueError('foreign revoke')
                p = issue(self.owner,g.key,{'kind':'revoke','workflow':g.workflow,'target':r['target'],'original':old})
                g.receive(p)
            else:
                if self.messages[r['target']]['sender'] != self.owner:
                    raise ValueError('foreign revoke')
                self.revoked.add(r['target'])
                p = {'target':r['target'],'sender':self.owner,'status':'revoked'}
            return {'packet':p}
        if op == 'status':
            q = r['query']
            if q.get('kind') == 'fact_evidence_query':
                from trust_network.demo.fact_evidence import attest
                return {'reply':attest(g,self.config['registry'],q)}
            return {'reply':authority_status(g,q)}
        if op == 'ordinary_status':
            return {'status':'revoked' if r['target'] in self.revoked else 'active' if r['target'] in self.messages else 'unknown'}
        if op == 'ordinary_fact':
            from trust_network.demo.fact_evidence import scope_key
            entry = self.config['registry'].get(scope_key(self.config['workflow'],r['fact']),{})
            status = ('UNKNOWN' if entry.get('status') != 'confirmed' else
                      'CONFIRMED' if entry['cents'] == r['fact']['value']['cents'] else 'CONTRADICTED')
            return {'status':status}
        if op == 'pending':
            return {'packets':pending_notifications(g) if g else []}
        if op == 'notice':
            return {'receipt':accept_notice(g,r['packet'])}
        if op == 'notice_ack':
            return acknowledge_notice(g,r['packet'])
        if op == 'act':
            proposal = r['proposal']
            if proposal.get('operation') not in ('forward','approve_invoice'):
                raise ValueError('unsupported business operation')
            if proposal.get('intent','execute') not in ('execute','verify'):
                raise ValueError('unsupported intent')
            if bool(r.get('verify')) != (proposal.get('intent','execute')=='verify'):
                raise ValueError('ambiguous verification intent')
            if g:
                if self.layer.coarse and (g.revoked or g.fact_disputes):
                    g.record('coarse_freeze',digest(proposal))
                    return {'action':'BLOCKED','reason':'coarse_freeze'}
                def effect(p):
                    if p['operation']=='forward':
                        return {'handoff':prepare_handoff(g,r['recipient'],p['claims'])}
                    self.effects.append(p['id'])
                    return {'simulated':True,'task':p['id'], 'executed_facts':[g.claims[c]['body']['fact'] for c in p['claims']]}
                batch = run_batch(g,[proposal],lambda who,q:query(who,{'op':'status','query':q})['reply'],
                    effect,ReliabilityConfig(policy=self.layer.policy),
                    fact_config={'policy':'verify_all','authority':'buyer'} if self.layer.facts or r.get('verify') else None)
                self.batches.append(batch)
                return {'action':batch['body']['outputs'][0]['action'],'batch':batch}
            if r.get('verify'):
                statuses=[query(self.messages[c]['sender'],{'op':'ordinary_status','target':c}) for c in proposal['claims']]
                if any(s['status']!='active' for s in statuses):
                    return {'action':'REQUEST_EVIDENCE','statuses':statuses}
            if proposal['operation']=='forward':
                if r.get('verify'):
                    answers=[query('buyer',{'op':'ordinary_fact','fact':self.messages[c]['fact']}) for c in proposal['claims']]
                    return {'action':'VERIFIED' if all(a['status']=='CONFIRMED' for a in answers) else 'REQUEST_EVIDENCE','answers':answers}
                return {'action':'COMPLETED','handoff':self.call({'op':'send','recipient':r['recipient'],'claims':proposal['claims']},query)['packet']}
            facts = {}
            for c in proposal['claims']:
                p = self.messages[c]
                predicate = p['fact']['predicate']
                if predicate in facts:
                    raise ValueError('duplicate_evidence_type')
                facts[predicate] = p['fact']['value']
            if len(proposal['claims']) != 2 or len(set(proposal['claims'])) != 2:
                raise ValueError('exactly_two_distinct_claims_required')
            validate_invoice_facts(facts,proposal['order'])
            if r.get('verify'):
                answer = query('buyer',{'op':'ordinary_fact','fact':{'predicate':'total_charge','value':facts['total_charge']}})
                return {'action':'VERIFIED' if answer['status']=='CONFIRMED' else 'REQUEST_EVIDENCE', 'answer':answer}
            self.effects.append(proposal['id'])
            return {'action':'COMPLETED','simulated':True,'executed_facts':[self.messages[c]['fact'] for c in proposal['claims']]}
        if op == 'view':
            return {'claims':list(g.claims.values()) if g else list(self.messages.values()),
                    'revocations':list(g.revoked.values()) if g else list(self.revoked),
                    'blocked':{c:g.blockers(c) for c in g.claims if g.blockers(c)} if g else {},
                    'disputes':g.fact_disputes if g else {}}
        if op == 'export':
            return {'events':g.events if g else [],'claims':list(g.claims.values()) if g else [],
                    'batches':self.batches,'effects':self.effects}
        if op == 'revision':
            from trust_network.demo.dispute_protocol import register_dispute, propose_revision
            if 'fact_ref' in r:
                private=self.config.get('private_facts',{})
                if r['fact_ref'] not in private:
                    raise ValueError('unknown private fact reference')
                fact=copy.deepcopy(private[r['fact_ref']])
            else:
                fact=copy.deepcopy(r.get('fact'))
            register_dispute(g,r['proof'])
            return {'offer':propose_revision(g,r['proof'],fact,
                lambda who,q:query(who,{'op':'status','query':q})['reply'])}
        if op == 'envelope':
            from trust_network.demo.recovery_closure import prepare_closure_recovery
            return {'envelope':prepare_closure_recovery(g,r['batch'],[r['offer']])}
        if op in ('frontier','rebuild'):
            from trust_network.demo.recovery_frontier import frontier, rebuild_frontier_claim
            args = (g,r['envelope'],r['task'],r['completed'],r['receiver'])
            if r['receiver'] not in self.config['receivers']:
                raise ValueError('unknown recovery receiver')
            state = frontier(*args)
            if op == 'frontier':
                return state
            node = next(n for n in state['ready'] if n['old']==r['old'] and n['issuer']==self.owner)
            fact_ref=r.get('fact_ref',node['parents'][0])
            if fact_ref not in node['parents']:
                raise ValueError('fact reference is not a recovery parent')
            fact = g.claims[fact_ref]['body']['fact']
            return rebuild_frontier_claim(*args,r['old'],fact)
        if op == 'decide':
            if not self.config.get('allow_paid',False):raise ValueError('paid calls disabled')
            from trust_network.demo.provider import ProviderConfig, complete_traced, ProviderTraceError
            from .storage import append_json
            import uuid
            if not self.config.get('archive_directory'):raise ValueError('paid calls require durable archive')
            ledger=Path(self.config['archive_directory'])/(self.owner+'.provider.jsonl')
            call_id=uuid.uuid4().hex
            config = replace(ProviderConfig.load(Path(r['env_file'])),max_tokens=2048,temperature=.2)
            append_json(ledger,{'call_id':call_id,'status':'started','input':r['input'],'system':r['system'],'model':config.model})
            try:
                draft,usage,attempts = complete_traced(config,r['system'],json.dumps(r['input'],ensure_ascii=False),
                    journal=lambda event:append_json(ledger,{'call_id':call_id,**event}))
                result={'draft':draft,'usage':usage,'attempts':attempts}
                append_json(ledger,{'call_id':call_id,'status':'returned','result':result})
                return result
            except ProviderTraceError as exc:
                result={'draft':None,'attempts':exc.attempts,'provider_error':str(exc)}
                append_json(ledger,{'call_id':call_id,'status':'failed','result':result})
                return result
        raise ValueError('unsupported operation')

class Backend:
    def __init__(self, configs, mode='memory', directory=None):
        self.mode = mode; self.clock=lambda:0; self.logs = []; self.workers = {}; self.nodes = {}
        self.directory=Path(directory) if directory is not None else None
        if self.directory is not None:self.directory.mkdir(parents=True,exist_ok=False,mode=0o700)
        if self.directory is not None:
            configs={o:{**c,'archive_directory':str(self.directory.resolve())} for o,c in configs.items()}
        if mode == 'memory':
            self.nodes = {o:Node(c) for o,c in configs.items()}
        elif mode == 'process':
            if self.directory is None:raise ValueError('process backend requires persistent directory')
            directory=self.directory
            for owner,config in configs.items():
                p = directory / (owner+'.json'); p.write_text(json.dumps(config)); p.chmod(0o600)
                self.workers[owner] = subprocess.Popen([sys.executable,'-m',
                    'trust_network.benchmark.layered.worker',str(p)],stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        else:
            raise ValueError('unknown backend')

    def call(self, owner, request, sender='controller'):
        request = copy.deepcopy(request)
        def query(who,r):
            return self.call(who,r,owner)
        if self.mode == 'memory':
            try: result = self.nodes[owner].call(request,query)
            except (ValueError,KeyError,StopIteration) as exc: result = {'error':type(exc).__name__,'message':str(exc)}
        else:
            import select
            p = self.workers[owner]
            p.stdin.write(json.dumps(request)+'\n'); p.stdin.flush()
            while True:
                if not select.select([p.stdout],[],[],210)[0]:
                    raise TimeoutError('organization worker timeout')
                line = p.stdout.readline()
                if not line: raise RuntimeError('organization worker exited')
                result = json.loads(line)
                if '_query' not in result: break
                answer = query(result['owner'],result['_query'])
                p.stdin.write(json.dumps(answer)+'\n');p.stdin.flush()
        start=len(self.logs)
        for entry in result.pop('_local_exchanges',[]):
            self.logs.append({'tick':self.clock(),**entry})
        self.logs.append({'tick':self.clock(),'owner':owner,'sender':sender,'op':request['op'],
                          'request':request if request['op']!='decide' else {'op':'decide','input':request['input']},
                          'response':copy.deepcopy(result)})
        if self.directory is not None:
            from .storage import append_json
            for entry in self.logs[start:]:append_json(self.directory/'rpc.jsonl',entry)
        return copy.deepcopy(result)

    def close(self):
        for p in self.workers.values():
            if p.poll() is None:
                p.stdin.close()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
            p.stdout.close();p.stderr.close()
