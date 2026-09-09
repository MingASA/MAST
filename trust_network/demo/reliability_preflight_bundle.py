"""Single offline delivery entrypoint; scripted proposals, zero model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
from trust_network.demo.prepare_reliability_demo import prepare
from trust_network.demo.compare_reliability_policies import compare
from trust_network.demo.evaluate_reliability_comparison import evaluate


def sources():
    root=Path(__file__).resolve().parents[2]
    # Include transitive local implementation dependencies, not private fixtures.
    files=sorted((root/'trust_network').rglob('*.py'))+[root/'pyproject.toml']
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def run(output):
    output=output.resolve(); output.mkdir(parents=True,mode=0o700,exist_ok=False)
    manifest={'kind':'offline_reliability_delivery','source_hashes':sources(),
              'python':platform.python_version(),'model_calls':0,'model_tokens':0,
              'proposal_origin':'scripted','conditions':['active','hidden_revoke'],
              'status':'running'}
    path=output/'manifest.json'; path.write_text(json.dumps(manifest,indent=2))
    scores={}
    try:
        for condition in manifest['conditions']:
            fixture=output/condition/'fixture'; prepare(fixture,condition)
            comparison=output/condition/'comparison'
            compare(fixture,fixture/'scripted_proposals.json',comparison)
            scores[condition]=evaluate(comparison,fixture/'evaluation_truth.json')
        if sources()!=manifest['source_hashes']:
            raise RuntimeError('source changed during preflight; results not frozen')
        (output/'scores.json').write_text(json.dumps(scores,indent=2))
        manifest['status']='completed'
    except Exception as exc:
        manifest['status']='failed'; manifest['error_type']=type(exc).__name__
        raise
    finally:
        path.write_text(json.dumps(manifest,indent=2))
    return scores


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True)
    run(p.parse_args().out)
