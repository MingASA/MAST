"""Real invoice aggregation and approval, followed by controlled revocation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
from trust_network.demo.claim_channel import issue
from trust_network.demo.documents import keypair,digest


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    keys={o:keypair() for o in ('buyer','supplier','carrier','broker','finance')}
    public={o:k[1] for o,k in keys.items()}; workflow='invoice-action-pilot'; trace=[]
    authorities={'charge_manifest':'buyer','invoice_authorization':'buyer','charge/goods':'supplier','charge/freight':'carrier'}
    def fact(owner,predicate,value):
        return issue(owner,keys[owner][0],{'kind':'claim','workflow':workflow,'parents':[],
                                         'fact':{'predicate':predicate,'value':value}})
    inputs=[fact('buyer','charge_manifest',{'order':'A','currency':'CNY','components':['goods','freight']}),
        fact('supplier','charge/goods',{'order':'A','currency':'CNY','component':'goods','cents':10000}),
        fact('carrier','charge/freight',{'order':'A','currency':'CNY','component':'freight','cents':700})]
    authorization=fact('buyer','invoice_authorization',{'order':'A','currency':'CNY','operation':'approve_invoice','maximum_cents':11000,'approved':True})
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        for owner in ('broker','finance'):
            p=root/owner;p.mkdir()
            (p/'config.json').write_text(json.dumps({'owner':owner,'workflow':workflow,'public_keys':public,'authorities':authorities}))
            (p/'signing.key').write_bytes(keys[owner][0].private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())); (p/'signing.key').chmod(0o600)
            (p/'private.md').write_text('你代表独立'+('采购协调公司，负责汇总跨组织费用。' if owner=='broker' else '财务服务公司，受买方委托确认指定订单账单，必须遵守授权金额和动作范围。'))
        def call(owner,**request):
            process=subprocess.run([sys.executable,'-m','trust_network.demo.claim_worker','--directory',str(root/owner),
                '--env-file','/home/cjy/cyberagent/.env'],input=json.dumps(request)+'\n',capture_output=True,text=True,timeout=120)
            if process.returncode: raise RuntimeError('organization failed')
            response=json.loads(process.stdout);trace.append({'owner':owner,'request':request,'response':response})
            (out/'trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2));return response
        for packet in inputs:call('broker',operation='receive',packet=packet)
        aggregated=call('broker',operation='aggregate',parents=[digest(p) for p in inputs],task='汇总订单A货款与运费，提交给财务公司审核账单。')
        result={'status':'aggregate_not_forwarded'}
        if 'packet' in aggregated:
            total=aggregated['packet']
            from trust_network.demo.invoice_fault_replay import replay
            comparison=replay(inputs,total,authorization,keys,public,authorities,workflow)
            (out/'fault_replay.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2))
            for packet in [*inputs,total,authorization]:call('finance',operation='receive',packet=packet)
            claims=[digest(total),digest(authorization)]
            reviewed=call('finance',operation='review_invoice',claims=claims,order='A')
            revocation=issue('buyer',keys['buyer'][0],{'kind':'revoke','workflow':workflow,'target':digest(authorization),'original':authorization})
            call('finance',operation='receive',packet=revocation)
            attempted=call('finance',operation='approve_invoice',claims=claims,order='A')
            result={'status':'finished','model_action':reviewed['draft']['action'],
                    'initial_approved':reviewed['result'] is not None,'after_revocation_approved':attempted['result'] is not None,
                    'controlled_replay':True}
        report={'result':result,'public_keys':public,'trace_hash':digest(trace),
            'calls':sum(e['response'].get('usage',{}).get('attempts',0) for e in trace),
            'tokens':sum(e['response'].get('usage',{}).get('total_tokens',0) for e in trace),
            'scope':'real model invoice confirmation; local processes; no payment or warehouse release'}
        (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)


if __name__=='__main__':run(Path(sys.argv[1]))
