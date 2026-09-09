"""Real-model conditional recovery ablation. No historical order is executed."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from trust_network.demo.documents import keypair, digest
from trust_network.demo.negotiation import CommitmentBook, owner_check, OWNERS
from trust_network.demo.negotiation_audit import validate
from trust_network.demo.repair_envelope import build_repair_envelope, compact_repair_view


def prefix(source):
    public=json.loads((source/'public_keys.json').read_text()); validate(source,public)
    events=json.loads((source/'events.json').read_text())
    book=CommitmentBook(public,events[0]['workflow_id'])
    plan=None; now=None
    for event in events[1:]:
        if event['kind']=='request' and event['request']['operation']=='plan' and event['request'].get('feedback'):
            request=event['request']; break
        if event['kind']=='response':
            now=event['received_at']; response=event['response']
            if event['owner']=='buyer' and 'message' in response:
                plan=response['message']['body']['content']['plan']
            if 'commitment' in response:
                book.add(event['owner'],plan,response['commitment'],now)
    else: raise ValueError('no recovery prefix')
    full=build_repair_envelope(book,plan,now,request['messages'])
    candidate=compact_repair_view(book,plan,now,request['messages'])
    compact=copy.deepcopy(candidate); compact['counterproposal']=None
    return public,request,{'full':full,'compact':compact,'candidate':candidate}


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    case=Path('examples/negotiation_v6/economy')
    sources=[Path('results/counterproposal_v11_rate')/f'{r}-frontier' for r in range(2)]
    (out/'manifest.json').write_text(json.dumps({'sources':[str(p) for p in sources],
        'repeats':2,'arms':['full','compact','candidate'],'scope':'conditional one-step recovery, not whole-workflow completion',
        'selection':'both V11 frontier prefixes, selected after observing successful recovery; not a population sample'},indent=2))
    records=[]
    for index,source in enumerate(sources):
        public,request,views=prefix(source)
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp); key,pub=keypair()
            for name in ('state.json','private.md'): shutil.copyfile(case/'buyer'/name,directory/name)
            (directory/'signing.key').write_bytes(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
            (directory/'signing.key').chmod(0o600)
            (directory/'config.json').write_text(json.dumps({'organization':'buyer','public_keys':public}))
            for repeat in range(2):
                arms=('full','compact','candidate'); offset=(index+repeat)%3
                for arm in arms[offset:]+arms[:offset]:
                    wire=copy.deepcopy(request); wire['feedback']=[views[arm]]
                    process=subprocess.run([sys.executable,'-m','trust_network.demo.negotiation_worker',
                        '--organization-dir',str(directory),'--env-file','/home/cjy/cyberagent/.env'],
                        input=json.dumps(wire),text=True,capture_output=True,timeout=120)
                    response=json.loads(process.stdout) if process.returncode==0 else {'error':'worker_failed'}
                    violations={}; content=response.get('message',{}).get('body',{}).get('content',{})
                    plan=content.get('plan')
                    if plan is not None:
                        for owner in OWNERS:
                            private=json.loads((case/owner/'state.json').read_text())
                            if owner=='carrier':
                                for service in private['services'].values(): service['price']+=100
                            violations[owner]=list(owner_check(owner,private,plan))
                    record={'source':index,'repeat':repeat,'arm':arm,'request':wire,'response':response,
                        'request_hash':digest(wire),'buyer_public_key':pub,'violations_posthoc':violations,
                        'valid_repair_proposed':content.get('action')=='propose' and plan is not None and not any(violations.values()),
                        'tokens':response.get('usage',{}).get('total_tokens',0)}
                    records.append(record); (out/'records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
                    print(json.dumps({k:record[k] for k in ('source','repeat','arm','valid_repair_proposed','tokens')}),flush=True)


if __name__=='__main__': run(Path(sys.argv[1]))
