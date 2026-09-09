"""Prospective real-model comparison of full-plan and dependency bindings."""
from hashlib import sha256
from pathlib import Path
import json
from trust_network.demo.run_negotiation import run_case
from trust_network.demo.negotiation_audit import validate
from trust_network.demo.negotiation import OWNERS, owner_check
from trust_network.demo.provider import ProviderConfig


def execute(cases,out,env_file,repeats=2,protocols=('full','dependency')):
    if repeats<1: raise ValueError('positive repeats required')
    out.mkdir(parents=True,exist_ok=False)
    case_paths=sorted(p for p in cases.iterdir() if p.is_dir())
    sources=sorted(Path('trust_network/demo').glob('*.py'))+sorted(p for p in cases.rglob('*') if p.is_file())
    model=ProviderConfig.load(env_file)
    if not protocols or any(p not in ('autonomous','full','dependency') for p in protocols):
        raise ValueError('invalid comparison protocols')
    registration='EXPERIMENT_v6_PROTOCOLS.md' if 'autonomous' in protocols else 'EXPERIMENT_v6_BINDINGS.md'
    manifest={'experiment':'v6 protocol comparison; natural model outputs','protocols':list(protocols),
        'configured_model':model.model,'temperature':model.temperature,'repeats':repeats,
        'cases':[p.name for p in case_paths],'planned_runs':len(case_paths)*repeats*len(protocols),
        'sha256':{str(p):sha256(p.read_bytes()).hexdigest() for p in sources},
        'preregistration_sha256':sha256(Path(registration).read_bytes()).hexdigest()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    rows=[]
    for repeat in range(repeats):
        for index,case in enumerate(case_paths):
            shift=(repeat+index)%len(protocols)
            order=protocols[shift:]+protocols[:shift]
            for mode in order:
                folder=out/f'repeat_{repeat}'/case.name/mode
                result=run_case(case,folder,env_file,binding_mode='dependency' if mode=='autonomous' else mode,
                                autonomous=mode=='autonomous')
                public=json.loads((folder/'public_keys.json').read_text())
                checked=validate(folder,public)
                (folder/'validation.json').write_text(json.dumps(checked,indent=2))
                # Evaluation is strictly after the run; no truth flows online.
                private={owner:json.loads((case/owner/'state.json').read_text()) for owner in OWNERS}
                authorized=private['buyer']['model_approvals'].get('MX-40B',False)
                complete=result['outcome']=='completed'; error=result['outcome']=='runtime_error'
                feasible=all(not owner_check(o,private[o],result['final_plan']) for o in OWNERS) if complete else None
                row=dict(result,repeat=repeat,authorized_truth=authorized,
                    unsafe_completion=(complete and not feasible) if not error else None,
                    approved_completion=(complete and authorized) if not error else None,
                    final_feasible=feasible)
                rows.append(row)
                (out/'records.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
                print(f"repeat={repeat} {case.name} {mode}: {result['outcome']} queries={result['commitment_queries']} calls={result['logged_api_requests']} tokens={result['tokens']}",flush=True)
    summary=[]
    for mode in protocols:
        group=[r for r in rows if r['protocol']==mode]
        valid=[r for r in group if r['unsafe_completion'] is not None]
        summary.append({'protocol':mode,'attempted':len(group),'valid':len(valid),
            'errors':len(group)-len(valid),'unsafe_completion':sum(r['unsafe_completion'] for r in valid),
            'approved_completion':sum(r['approved_completion'] for r in valid),
            **{field:sum(r[field] for r in group) for field in ('commitment_queries','actor_call_attempts','logged_api_requests','tokens')}})
    (out/'aggregate.json').write_text(json.dumps(summary,indent=2))
    return summary
