"""Fixed-proposal policy ablation, deliberately not an autonomous-agent eval."""
import argparse
import json
from pathlib import Path
import shutil
from trust_network.demo.documents import digest
from trust_network.demo.reliability_runner import run


def compare(fixture, proposals, output, provenance=None):
    output=output.resolve(); output.mkdir(parents=True,mode=0o700,exist_ok=False)
    manifest=json.loads((fixture/'manifest.json').read_text())
    request=json.loads(proposals.read_text())
    imported=None
    if provenance is not None:
        imported=json.loads(provenance.read_text())
        model_input=json.loads((fixture/'model_input.json').read_text())
        record=json.loads((provenance.parent/'model_record.json').read_text())
        if (imported['proposal_hash']!=digest(request) or imported['input_hash']!=digest(model_input)
                or imported['record_hash']!=digest(record)):
            raise ValueError('imported decision provenance mismatch')
        # Derive again from archived input/record rather than trust a relabeled
        # provenance file that could turn hold/error into an approval.
        from trust_network.demo.import_reliability_decision import import_decision
        regenerated=import_decision(fixture/'model_input.json',provenance.parent/'model_record.json',output/'imported')
        if regenerated != imported:
            raise ValueError('imported classification mismatch')
    rows=[]
    for policy in ('autonomous','verify_all','dependency'):
        directory=output/policy; directory.mkdir(mode=0o700)
        locations={}
        for owner,path in {'receiver':manifest['receiver'],**manifest['authorities']}.items():
            target=directory/owner
            shutil.copytree(path,target)
            locations[owner]=str(target)
        config_path=Path(locations['receiver'])/'config.json'
        config=json.loads(config_path.read_text())
        config.setdefault('reliability',{})['policy']=policy
        config_path.write_text(json.dumps(config,indent=2))
        local_manifest={'receiver':locations['receiver'],
                        'authorities':{o:locations[o] for o in manifest['authorities']}}
        manifest_path=directory/'manifest.json'; manifest_path.write_text(json.dumps(local_manifest))
        report=run(manifest_path,proposals,directory/'run')['batch']['body']
        counts={}
        for item in report['outputs']:
            counts[item['action']]=counts.get(item['action'],0)+1
        rows.append({'policy':policy,'outcomes':counts,
                     'verification_calls':report['verification_calls'],
                     'model_decision_classification':imported['classification'] if imported else 'scripted_or_unattributed',
                     'model_hold_count':int(imported is not None and imported['classification']=='model_hold'),
                     'model_failure_count':int(imported is not None and imported['classification'] in ('provider_error','invalid_model_decision')),
                     'unsafe_completion_rate':None, 'ground_truth_not_scored':True})
    result={'protocol':'fixed_proposal_freshness_ablation','proposal_hash':digest(request),
            'model_input_hash':digest(json.loads((fixture/'model_input.json').read_text())),
            'rows':rows,'imported_provenance':imported,'new_model_calls':0,'new_model_tokens':0,
            'limits':['autonomous_arm_retains_structural_and_action_contracts',
                      'not_an_end_to_end_agent_comparison',
                      'completion_is_simulated_adapter_result',
                      'private_directories_are_local_process_conventions_not_OS_isolation']}
    (output/'comparison.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--proposals',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--provenance',type=Path)
    a=p.parse_args(); compare(a.fixture,a.proposals,a.out,a.provenance)
