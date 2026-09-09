"""Controlled bad claims, natural downstream Agent choices, fixed source evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
from trust_network.demo.documents import keypair,digest
from trust_network.demo.claim_channel import ClaimGateway,read


def run(out):
    source=Path('results/invoice_v17_propagation')
    report=json.loads((source/'report.json').read_text()); trace=json.loads((source/'trace.json').read_text())
    if digest(trace)!=report['trace_hash']: raise ValueError('source changed')
    faults=json.loads((source/'fault_replay.json').read_text())['rows']
    packets=[r['request']['packet'] for r in trace if r['owner']=='broker' and r['request']['operation']=='receive']
    workflow=packets[0]['body']['workflow']; public=dict(report['public_keys'])
    authorities={'charge_manifest':'buyer','invoice_authorization':'buyer','charge/goods':'supplier','charge/freight':'carrier'}
    out.mkdir(parents=True,exist_ok=False); records=[]
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); local_keys={}
        for owner in ('reviewer','accounting'):
            key,pub=keypair(); public[owner]=pub; local_keys[owner]=key
        for owner,key in local_keys.items():
            p=root/owner;p.mkdir();(p/'signing.key').write_bytes(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));(p/'signing.key').chmod(0o600)
            (p/'config.json').write_text(json.dumps({'owner':owner,'public_keys':public,'workflow':workflow,'authorities':authorities}))
        (out/'manifest.json').write_text(json.dumps({'source':str(source),'public_keys':public,
            'faults':['none','changed_total','omitted_component'],'policies':['commit_validation','receive_validation'],
            'model_task_identical':True,'scope':'controlled signed source changes; natural downstream behavior; two local processes'},indent=2))
        for fault in ('none','changed_total','omitted_component'):
            target=next(r['evaluated_packet'] for r in faults if r['fault']==fault)
            for policy in ('commit_validation','receive_validation'):
                chain=[*packets,target]; hops=[]
                for owner in ('reviewer','accounting'):
                    request=json.loads(json.dumps({'policy':policy,'packets':chain}))
                    p=subprocess.run([sys.executable,'-m','trust_network.demo.propagation_receiver',str(root/owner)],
                        input=json.dumps(request),capture_output=True,text=True,timeout=120)
                    response=json.loads(p.stdout) if p.returncode==0 else {'status':'runtime_error','model_calls':0}
                    if 'decision' in response: read(response['decision'],public)
                    hops.append({'owner':owner,'request':request,'response':response})
                    if 'packet' not in response: break
                    chain.append(response['packet'])
                gateway=ClaimGateway('accounting',local_keys['accounting'],public,workflow,authorities)
                valid=all(gateway.receive(p)['body']['action']=='received' for p in chain)
                final_eligible=len(hops)==2 and all(h['response']['status']=='forward' for h in hops) and valid
                row={'fault':fault,'policy':policy,'hops':hops,'forward_count':sum(h['response']['status']=='forward' for h in hops),
                    'model_exposure_hops':sum('draft' in h['response'] for h in hops),'final_eligible':final_eligible,
                    'model_calls':sum(h['response']['model_calls'] for h in hops),
                    'tokens':sum(h['response'].get('usage',{}).get('total_tokens',0) for h in hops)}
                records.append(row);(out/'records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
                print(json.dumps({k:v for k,v in row.items() if k!='hops'}),flush=True)


if __name__=='__main__':run(Path(sys.argv[1]))
