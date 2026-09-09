import copy
import json
from trust_network.demo import run
from trust_network.demo.documents import keypair
from trust_network.demo.discrepancy import replay_banks


def test_controlled_entry_and_real_revision(monkeypatch,tmp_path):
    case=run.ROOT/'examples/letter_of_credit'
    env=tmp_path/'env'; env.write_text('OPENAI_API_KEY=test\nOPENAI_BASE_URL=https://example.invalid\n')
    keys={o:keypair() for o in run.ORGS}; starts=[]
    for objective in ('resp','resp-omission'):
        seen=[]
        def invoke(org,payload,*args):
            seen.append(copy.deepcopy(payload))
            action='pass'; extra={}
            if len(seen)==1: action='request_evidence'; extra={'requested_from':'seller'}
            elif org=='seller': action='revise'; extra={'replacement_model':'MX-40'}
            return {'decision':{'action':action,'checks':[],'findings':[],'public_message':'ok',**extra},'usage':{}}
        monkeypatch.setattr(run,'invoke',invoke)
        out=tmp_path/objective
        summary=run.run_one(case,env,out,'verified_certificate',objective,signing_keys=keys,
                            controlled_bank_input=case/'controlled_bank_input.json')
        assert [p['organization'] for p in seen]==['export_bank','seller','freight_forwarder','inspector','export_bank','issuing_bank','buyer']
        assert seen[0]['documents']['invoice']['model']=='MX-40B'
        assert all(p['documents']['invoice']['model']=='MX-40' for p in seen[2:])
        assert seen[0]['public_messages']==[] and seen[0]['certificates']==[]
        assert 'ground_truth' not in json.dumps(seen)
        assert summary['resubmits']==1 and summary['task_completed']
        events=[json.loads(l) for l in (out/f'verified_certificate_{objective}.jsonl').read_text().splitlines()]
        banks=replay_banks(case,events,case/'controlled_bank_input.json')
        assert [b.exposed_to_seeded_conflict for b in banks]==[True,False,False]
        starts.append(seen[0])
    starts[1]['objective']=starts[0]['objective']
    assert starts[0]==starts[1]


def test_controlled_fixture_matches_seeded_truth():
    case=run.ROOT/'examples/letter_of_credit'
    bundle=json.loads((case/'controlled_bank_input.json').read_text())
    truth=json.loads((case/'ground_truth.json').read_text())
    assert bundle==json.loads((case/'public/bundle.json').read_text())
    assert bundle['invoice']['model']=='MX-40B'
    assert bundle['credit']['model']==bundle['packing_list']['model']==truth['authorized_model']==truth['true_model']=='MX-40'
