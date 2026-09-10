"""Same worker-shaped public API, in-memory replay or isolated subprocesses."""
from trust_network.demo.claim_derivation import proposed_fact
import copy
import json
import os
import selectors
import subprocess
import sys
import tempfile
from pathlib import Path
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
from trust_network.demo.claim_channel import ClaimGateway,issue
from trust_network.demo.documents import digest
from trust_network.demo.claim_derivation import valid_derivation
from trust_network.demo.network_reliability import run_batch,ReliabilityConfig,authority_status,ancestors
from trust_network.demo.propagation_notice import (prepare_handoff,accept_handoff,acknowledge_handoff,
    accept_notice,acknowledge_notice,pending_notifications,notification_audit)
from trust_network.demo.recovery_closure import revision_offer,prepare_closure_recovery
from trust_network.demo.recovery_frontier import frontier,rebuild_frontier_claim
from .spec import config,dossier,OWNERS


def public_view(gateway):
    return {'claims':list(gateway.claims.values()),'revocations':list(gateway.revoked.values()),
            'blocked':{c:gateway.blockers(c) for c in gateway.claims if gateway.blockers(c)}}


class MemoryBackend:
    def __init__(self,workload,arm,private_state=None):
        self._private=copy.deepcopy(private_state or {})
        self.configs={o:config(o,workload['public'],workload['workflow'],arm) for o in OWNERS}
        self.nodes={o:ClaimGateway(o,workload['keys'][o],workload['public'],workload['workflow'],
            self.configs[o]['authorities']) for o in OWNERS}
        self.observer=lambda *args:None

    def call(self,owner,request,sender=None):
        request=copy.deepcopy(request);g=self.nodes[owner];start=len(g.events);op=request['operation']
        try:
            if op=='receive':response={'event':g.receive(request['packet'])}
            elif op=='reliability_public_view':response={'view':public_view(g)}
            elif op=='reliability_sign_derived':
                packet=issue(g.owner,g.key,{'kind':'claim','workflow':g.workflow,'parents':request['parents'],
                    'fact':proposed_fact(g,request,request['parents']),'rule':request.get('rule','relay')})
                event=g.receive(packet);response={'event':event}
                if event['body']['action']=='received':response['packet']=packet
            elif op=='reliability_revoke':
                cid=request['target'];original=g.claims[cid]
                if original['signature']['issuer']!=owner:raise ValueError('foreign retraction')
                packet=issue(owner,g.key,{'kind':'revoke','workflow':g.workflow,'target':cid,'original':original})
                response={'packet':packet,'event':g.receive(packet)}
            elif op=='reliability_status':response={'reply':authority_status(g,request['query'])}
            elif op in ('reliability_batch','reliability_handoff_prepare'):
                proposals=request.get('proposals')
                if op=='reliability_handoff_prepare':
                    proposals=[{'id':request['id'],'operation':'forward','claims':request['claims'],'intent':'execute'}]
                response={'batch':run_batch(g,proposals,lambda who,q:self.call(who,{'operation':'reliability_status','query':q},owner)['reply'],
                    (lambda p:{'handoff':prepare_handoff(g,request['recipient'],p['claims'])}) if op=='reliability_handoff_prepare'
                    else (lambda p:{'simulated':True,'operation':p['operation']}),ReliabilityConfig(**self.configs[owner]['reliability']))}
            elif op in ('reliability_handoff_accept','reliability_handoff_ack','reliability_notification_accept','reliability_notification_ack'):
                fn={'reliability_handoff_accept':accept_handoff,'reliability_handoff_ack':acknowledge_handoff,
                    'reliability_notification_accept':accept_notice,'reliability_notification_ack':acknowledge_notice}[op]
                response={'result':fn(g,request['packet'])}
            elif op=='reliability_notifications':response={'pending':pending_notifications(g),'audit':notification_audit(g)}
            elif op=='reliability_claim_revision':response={'offer':revision_offer(g,request['old'],request['fact'])}
            elif op=='reliability_closure_recovery':response={'recovery':prepare_closure_recovery(g,request['batch'],request['offers'])}
            elif op in ('reliability_frontier','reliability_frontier_rebuild'):
                receiver=request['envelope']['signature']['issuer']
                if receiver not in self.configs[owner]['recovery_receivers']:raise ValueError('untrusted receiver')
                args=(g,request['envelope'],request['task_id'],request['completed'],receiver)
                state=frontier(*args)
                if op=='reliability_frontier':response={'frontier':state}
                else:
                    node=next((n for n in state['ready'] if n['old']==request['old'] and n['issuer']==g.owner),None)
                    if node is None:raise ValueError('rebuild node is not ready')
                    fact=proposed_fact(g,{**request,'rule':node['rule']},node['parents'])
                    response=rebuild_frontier_claim(*args,request['old'],fact)
            else:raise ValueError('unsupported replay operation')
        except (ValueError,KeyError) as exc:response={'error':type(exc).__name__,'message':str(exc)}
        response['events']=g.events[start:];response=copy.deepcopy(response)
        self.observer(owner,request,response,sender)
        return response


class ProcessBackend:
    def __init__(self,workload,arm,directory,env_file=None,allow_paid=False,private_state=None):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=False)
        self.env_file=Path(env_file) if env_file else self.directory/'UNUSED.env'
        self.allow_paid=allow_paid;self.observer=lambda *args:None
        for owner in OWNERS:
            path=self.directory/owner;path.mkdir(mode=0o700)
            (path/'config.json').write_text(json.dumps(config(owner,workload['public'],workload['workflow'],arm)))
            (path/'private.md').write_text(dossier(owner)+'\n本组织私有业务状态：'+json.dumps((private_state or {}).get(owner,{}),ensure_ascii=False))
            (path/'private.json').write_text(json.dumps((private_state or {}).get(owner,{})))
            (path/'signing.key').write_bytes(workload['keys'][owner].private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
            (path/'signing.key').chmod(0o600)

    def call(self,owner,request,sender=None):
        if owner not in OWNERS:raise ValueError('unknown organization endpoint')
        if request['operation']=='reliability_model_decision' and not self.allow_paid:raise ValueError('paid calls disabled')
        command=[sys.executable,'-m','trust_network.demo.claim_worker','--directory',str(self.directory/owner),'--env-file',str(self.env_file)]
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            process.stdin.write(json.dumps(request)+'\n');process.stdin.flush()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout,selectors.EVENT_READ)
                while True:
                    if not selector.select(timeout=210):raise TimeoutError('worker timeout')
                    line=process.stdout.readline()
                    if not line:raise RuntimeError('worker exited without response')
                    value=json.loads(line)
                    if 'authority_query' not in value:response=value;break
                    reply=self.call(value['authority'],{'operation':'reliability_status','query':value['authority_query']},owner)
                    process.stdin.write(json.dumps({'reply':reply.get('reply',{})})+'\n');process.stdin.flush()
            process.wait(timeout=5)
            if process.returncode:raise RuntimeError('worker failed')
        except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as exc:
            response={'error':type(exc).__name__,'message':'worker call failed; no success inferred'}
        finally:
            if process.poll() is None:process.kill();process.wait()
            process.stdin.close();process.stdout.close();process.stderr.close()
        self.observer(owner,copy.deepcopy(request),copy.deepcopy(response),sender)
        return response
