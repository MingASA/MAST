"""Real Agent handoffs plus explicitly controlled revocation delivery."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
from trust_network.demo.claim_channel import issue, read
from trust_network.demo.documents import keypair,digest


def run(out,aggregate=False):
    out.mkdir(parents=True,exist_ok=False)
    keys={o:keypair() for o in ('authority','broker','warehouse','supplier','carrier')}; public={o:k[1] for o,k in keys.items()}
    workflow='claim-propagation-pilot'; trace=[]
    root_claim=issue('authority',keys['authority'][0],{'kind':'claim','workflow':workflow,
        'fact':{'predicate':'formal_approval','value':{'order':'ORDER-A','model':'MX-40B','approved':True}},'parents':[]})
    other=issue('authority',keys['authority'][0],{'kind':'claim','workflow':workflow,
        'fact':{'predicate':'formal_approval','value':{'order':'ORDER-B','model':'MX-40B','approved':True}},'parents':[]})
    initial=[root_claim]
    if aggregate:
        initial=[issue('authority',keys['authority'][0],{'kind':'claim','workflow':workflow,'parents':[],
            'fact':{'predicate':'charge_manifest','value':{'order':'ORDER-A','currency':'CNY','components':['goods','freight']}}})]
        for owner,component,cents in [('supplier','goods',10000),('carrier','freight',700)]:
            initial.append(issue(owner,keys[owner][0],{'kind':'claim','workflow':workflow,'parents':[],
                'fact':{'predicate':'charge/'+component,'value':{'order':'ORDER-A','currency':'CNY','component':component,'cents':cents}}}))
        root_claim=initial[-1]
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        for owner in keys:
            directory=root/owner; directory.mkdir()
            (directory/'config.json').write_text(json.dumps({'owner':owner,'public_keys':public,
                'workflow':workflow,'authorities':{'formal_approval':'authority','charge_manifest':'authority',
                                                 'charge/goods':'supplier','charge/freight':'carrier'}}))
            (directory/'signing.key').write_bytes(keys[owner][0].private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
            (directory/'signing.key').chmod(0o600)
            (directory/'private.md').write_text('你代表'+('采购协调公司，负责组织供应商与仓储交接。' if owner=='broker' else '独立仓储公司，负责备件交接安排。')+'你无法访问其他组织内部状态。')
        def call(owner,**request):
            process=subprocess.Popen([sys.executable,'-m','trust_network.demo.claim_worker','--directory',str(root/owner),
                '--env-file','/home/cjy/cyberagent/.env'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
            try:
                process.stdin.write(json.dumps(request)+'\n'); process.stdin.flush()
                response=json.loads(process.stdout.readline())
                while 'authority_query' in response:
                    answer=call(response['authority'],operation='status',query=response['authority_query'])
                    process.stdin.write(json.dumps({'reply':answer['reply']})+'\n'); process.stdin.flush()
                    response=json.loads(process.stdout.readline())
                if process.wait(timeout=120): raise RuntimeError('claim organization failed')
            finally:
                if process.poll() is None: process.kill(); process.wait()
            if 'event' in response: read(response['event'],public)
            trace.append({'owner':owner,'request':request,'response':response})
            (out/'trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2))
            return response
        for packet in initial: call(packet['signature']['issuer'],operation='receive',packet=packet)
        call('authority',operation='receive',packet=other)
        chain=list(initial)
        for owner in ('broker','warehouse'):
            for packet in chain: call(owner,operation='receive',packet=packet)
            if aggregate and owner=='broker':
                reply=call(owner,operation='aggregate',parents=[digest(p) for p in initial],task='汇总采购费用并安排向下游仓储提交。')
            else:
                reply=call(owner,operation='handoff',parent=digest(chain[-1]),task='依据上游声明决定是否继续交接，并提出本组织的下一步安排。')
            if 'packet' not in reply:
                (out/'incomplete.json').write_text(json.dumps({'reason':'agent_or_gateway_did_not_forward','owner':owner})); return
            chain.append(reply['packet'])
        call('warehouse',operation='receive',packet=other)
        issuer=root_claim['signature']['issuer']
        revoke=issue(issuer,keys[issuer][0],{'kind':'revoke','workflow':workflow,
            'target':digest(root_claim),'original':root_claim})
        # Observe visibility boundary before delivering the notice to warehouse.
        call('broker',operation='receive',packet=revoke)
        call(issuer,operation='receive',packet=revoke)
        before=call('warehouse',operation='execute',claim=digest(chain[-1]))
        checked=call('warehouse',operation='execute_checked',claim=digest(chain[-1]))
        checked_other=call('warehouse',operation='execute_checked',claim=digest(other))
        call('warehouse',operation='receive',packet=revoke)
        after=call('warehouse',operation='execute',claim=digest(chain[-1]))
        unaffected=call('warehouse',operation='execute',claim=digest(other))
        report={'kind':'controlled_revocation_real_agent_handoffs','public_keys':public,
            'aggregate':aggregate,
            'agent_hops':2,'before_notice_executed':before['executed'],'after_notice_executed':after['executed'],
            'checked_before_notice_executed':checked['executed'],'checked_unaffected_executed':checked_other['executed'],
            'unaffected_executed':unaffected['executed'],'trace_hash':digest(trace),
            'model_calls':sum(e['response'].get('usage',{}).get('attempts',0) for e in trace),
            'tokens':sum(e['response'].get('usage',{}).get('total_tokens',0) for e in trace),
            'limitations':['controlled notice timing; no natural error-rate claim','separate local processes, not physical devices',
                           'simulated effects; pre-notice stale execution intentionally measured','exact fact relay, no arbitrary semantic inference']}
        (out/'report.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report),flush=True)


if __name__=='__main__':run(Path(sys.argv[1]),aggregate='--aggregate' in sys.argv[2:])
