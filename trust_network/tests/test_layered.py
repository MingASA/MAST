import copy
import json
import pytest
from trust_network.benchmark.layered.engine import Run, SYSTEM
from trust_network.benchmark.layered.backend import Node
from trust_network.benchmark.layered.spec import LAYERS, MAIN, matrix
from trust_network.benchmark.contribution.forensics import signed_artifacts
from trust_network.demo.claim_action_contract import validate_invoice_facts
from dataclasses import asdict


def test_l0_has_no_gateway_signature_or_private_registry_in_observations():
    r=Run('long_chain_fork','late_notice','L0').run()
    assert not list(signed_artifacts(r))
    assert r['metrics']['unsafe_completion_count']==2
    for d in r['decisions']:
        assert 'registry' not in json.dumps(d['public_input'])
    node=Node({'owner':'x','workflow':'w','layer':asdict(LAYERS['L0'])})
    assert node.g is None


@pytest.mark.parametrize('case,expected',[
    ('active',[0,0,0,0,0]),('tampered_handoff',[1,0,0,0,0]),
    ('root_retraction',[2,2,0,0,0]),('intermediate_retraction',[2,2,2,0,0]),
    ('signed_false',[2,2,2,2,0]),('authority_unknown',[2,2,2,2,0])])
def test_layers_and_fixed_reference(case,expected):
    rows=[Run('long_chain_fork',case,l).run() for l in MAIN]
    assert [r['metrics']['unsafe_completion_count'] for r in rows]==expected
    assert len({r['workload_hash'] for r in rows})==1
    assert len({r['event_tape_hash'] for r in rows})==1
    assert len({r['proposal_tape_hash'] for r in rows})==1
    if case=='active':assert all(r['metrics']['safe_final_completion']==4 for r in rows)


def test_repair_lower_layers_not_disabled_and_initial_errors_not_erased():
    for layer in ('L0','L3','L4','L4_no_recovery'):
        r=Run('long_chain_fork','confirmed_repair',layer).run()
        assert r['metrics']['recovered_tasks']==2
        assert r['metrics']['safe_final_completion']==4
        assert r['metrics']['unsafe_completion_count']==(2 if layer in ('L0','L3') else 0)


def test_live_recovery_adapter_exposes_control_plane_and_private_fact_ref():
    run=Run('long_chain_fork','confirmed_repair','L4',live=True)

    def scripted(owner,stage,claims,extra=None,system=None,allowed_actions=None):
        if stage.startswith('recovery_request:'):
            return {'action':'request_recovery','task_id':stage,
                    'claim_refs':list(claims)}
        if stage=='repair:source':
            return {'action':'propose_revision','fact_ref':'source_revision_A_v2'}
        if stage.startswith('recovery_rebuild:'):
            return {'action':'proceed','claim_refs':list(claims),
                    'fact_ref':'task[0]'}
        return {'action':'proceed'}

    run.choose=scripted
    raw=run.run()
    assert raw['metrics']['recovered_tasks']==2
    assert raw['metrics']['unsafe_completion_count']==0
    assert [r['status'] for r in raw['recovery_requests']]==['submitted','submitted']
    assert raw['source_revision']['status']=='confirmed_offer'
    assert all(r['status']=='recovery_completed' for r in raw['recoveries'])
    revision_requests=[e['request'] for e in raw['exchanges'] if e['op']=='revision']
    assert revision_requests and all('fact' not in request for request in revision_requests)


def test_live_recovery_reference_validation_accepts_only_exact_ordered_ids():
    claims=['claim-a','claim-b']
    assert Run._resolve_claim_refs({'claim_refs':claims},claims)==claims
    assert Run._resolve_claim_refs({'claim_refs':['claim-b','claim-a']},claims) is None
    assert Run._resolve_claim_refs({'claim_refs':['claim-a','claim-c']},claims) is None
    assert Run._resolve_claim_refs({'claim_refs':['task[0]','task[1]']},claims)==claims


def test_claim_reference_prompt_is_indexed_and_bounded_to_action_inputs():
    run=Run('long_chain_fork','active','L4')
    try:
        run.seed()
        claims=[run.refs['root_A'],run.refs['auth_A']]
        run.choose('receiver_a','initial:A_a',claims)
        prompt=run.decisions[-1]['public_input']
        assert prompt['claim_id_index']=={'task[0]':claims[0],'task[1]':claims[1]}
        assert prompt['claim_ref_contract']['if_present_must_have_exact_count']==2
        assert prompt['claim_ref_contract']['if_present_must_be_exact_ordered_slots']==['task[0]','task[1]']
        assert prompt['claim_ref_contract']['do_not_expand_parent_chain'] is True
        assert '省略claim_refs字段' in SYSTEM
        assert 'forward操作要用proceed' in SYSTEM
    finally:
        run.b.close()


@pytest.mark.parametrize('topology,case,layer',[
    ('long_chain_fork','late_notice','L0'),('long_chain_fork','late_notice','L3'),
    ('reused_org_independent','confirmed_repair','L0'),
    ('converge_then_fork','confirmed_repair','L4'),
    ('reused_org_independent','confirmed_repair','L4')])
def test_process_matches_memory(tmp_path,topology,case,layer):
    memory=Run(topology,case,layer).run()['metrics']
    process=Run(topology,case,layer,backend='process',directory=tmp_path/layer).run()['metrics']
    # Signed attestations contain wall-clock float timestamps; serialized byte
    # lengths can differ slightly, although messages and all outcomes match.
    a=memory.pop('notification_bytes');b=process.pop('notification_bytes')
    assert abs(a-b)<=max(64,max(a,b)*.01)
    assert memory==process


def test_tape_missing_holds_not_fallback():
    r=Run('long_chain_fork','late_notice','L0',tape={}).run()
    assert r['metrics']['explicit_action_opportunities']==0
    assert r['metrics']['unsafe_completion_count']==0
    assert r['metrics']['safe_final_completion']==0
    assert all(d['draft']['reason']=='tape_entry_missing' for d in r['decisions'])


def test_shared_contract_rejects_bad_authorization():
    total={'order':'A','currency':'CNY','cents':100}
    auth={'order':'A','operation':'approve_invoice','currency':'CNY','maximum_cents':200,'approved':True}
    validate_invoice_facts({'total_charge':total,'invoice_authorization':auth},'A')
    for wrong in ({**auth,'approved':False},{**auth,'maximum_cents':90},{**auth,'order':'C'}):
        with pytest.raises(ValueError):validate_invoice_facts({'total_charge':total,'invoice_authorization':wrong},'A')


def test_matrix_size_and_ablation_identity():
    assert len(list(matrix()))==210
    assert asdict(LAYERS['L4_no_push'])=={**asdict(LAYERS['L4']),'push':False}


def test_verification_never_executes_l0_effect():
    run=Run('long_chain_fork','active','L0')
    try:
        run.seed()
        task=run.spec['tasks'][0]
        claims=[run.refs[task['claim_key']],run.refs['auth_A']]
        proposal={'id':'verify-only','operation':'approve_invoice','order':'A','claims':claims,'intent':'verify'}
        answer=run.rpc(task['owner'],'act',proposal=proposal,verify=True)
        assert answer['action']=='VERIFIED'
        assert run.rpc(task['owner'],'export')['effects']==[]
        bad=run.rpc(task['owner'],'act',proposal=proposal,verify=False)
        assert bad['error']=='ValueError'
    finally:run.b.close()


def test_unknown_fact_hold_is_not_protocol_block():
    tape={'initial:A_a':{'action':'verify'},'initial:A_a:after_verify':{'action':'hold'}}
    r=Run('long_chain_fork','authority_unknown','L0',tape=tape).run()
    assert r['metrics']['error_action_blocks']==0
    assert r['metrics']['unsafe_completion_count']==0
    assert next(o for o in r['outcomes'] if o['task']=='A_a' and o['phase']=='initial')['action']=='HOLD'


def test_actual_multihop_error_and_no_truth_in_repair_scheduler():
    import ast,inspect
    r=Run('long_chain_fork','late_notice','L0').run()
    assert r['metrics']['post_fault_propagation_hops']>=2
    tree=ast.parse(inspect.getsource(__import__('trust_network.benchmark.layered.engine',fromlist=['Run'])))
    repair=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='repair')
    assert not any(isinstance(n,ast.Attribute) and n.attr=='truth' for n in ast.walk(repair))


def test_paid_operation_fails_closed_without_authorization():
    node=Node({'owner':'x','workflow':'w','layer':asdict(LAYERS['L0'])})
    with pytest.raises(ValueError,match='paid calls disabled'):
        node.call({'op':'decide'},lambda *_:None)
