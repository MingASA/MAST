import copy
import pytest
from trust_network.benchmark.containment import fixture,AUTHORITIES,evaluate
from trust_network.benchmark.closure_v3 import run_case
from trust_network.demo.claim_channel import ClaimGateway,issue
from trust_network.demo.documents import digest
from trust_network.demo.network_reliability import run_batch,ReliabilityConfig,authority_status,apply_status_evidence
from trust_network.demo.recovery_closure import revision_offer,prepare_closure_recovery,validate_envelope
from trust_network.demo.recovery_frontier import frontier,rebuild_frontier_claim
from trust_network.demo.reliability_audit import audit_with_authorities


def setup_recovery():
    f=fixture('active')
    nodes={o:ClaimGateway(o,f['keys'][o],f['public'],f['workflow'],AUTHORITIES) for o in f['keys']}
    root=f['roots']['A'];coord=f['trace']['A']['coordinator'];mid=f['trace']['A']['middle_a'];auth=f['auth']['A']
    for g in nodes.values():
        for p in (root,coord,mid,auth):g.receive(p)
    old=digest(coord);g=nodes['coordinator']
    revoke=issue(g.owner,g.key,{'kind':'revoke','workflow':g.workflow,'target':old,'original':coord})
    g.receive(revoke)
    proposal={'id':'invoice','operation':'approve_invoice','order':'A','claims':[digest(mid),digest(auth)],'intent':'execute'}
    query=lambda owner,q:authority_status(nodes[owner],q)
    packet=run_batch(nodes['receiver_a'],[proposal],query,lambda p:pytest.fail('old action'),ReliabilityConfig('dependency_closure'))
    offer=revision_offer(g,old,coord['body']['fact'])
    return f,nodes,proposal,packet,offer


def test_middle_revision_recovers_descendant_without_resurrecting_old_claim():
    f,nodes,proposal,batch,offer=setup_recovery();g=nodes['receiver_a']
    envelope=prepare_closure_recovery(g,batch,[offer]);task=proposal['id']
    mid=nodes['middle_a'];mid.receive(offer['body']['new'])
    state=frontier(mid,envelope,task,{},g.owner)
    assert state['remaining']==1
    old=state['ready'][0]['old']
    rebuilt=rebuild_frontier_claim(mid,envelope,task,{},g.owner,old,offer['body']['new']['body']['fact'])
    g.receive(rebuilt['packet'])
    complete=frontier(g,envelope,task,{old:rebuilt['packet']},g.owner)
    renewed={**proposal,'claims':[complete['replacement_map'].get(c,c) for c in proposal['claims']]}
    effects=[]
    report=run_batch(g,[renewed],lambda o,q:authority_status(nodes[o],q),lambda p:effects.append(p),ReliabilityConfig('dependency_closure'))
    assert len(effects)==1 and report['body']['outputs'][0]['action']=='COMPLETED'
    assert g.blockers(old) and not g.blockers(digest(rebuilt['packet']))
    assert offer['body']['new']['body']['fact']==f['trace']['A']['coordinator']['body']['fact']
    assert digest(offer['body']['new'])!=offer['body']['old']
    assert audit_with_authorities(report,g.public,AUTHORITIES)['policy_replay_valid']


@pytest.mark.parametrize('corruption',['foreign_issuer','wrong_scope','invalid_fact','wrong_task','omitted_node'])
def test_invalid_recovery_evidence_rejected(corruption):
    _,nodes,proposal,batch,offer=setup_recovery();g=nodes['receiver_a']
    if corruption in ('wrong_task','omitted_node'):
        envelope=prepare_closure_recovery(g,batch,[offer]);body=copy.deepcopy(envelope['body'])
        if corruption=='wrong_task':body['tasks'][0]['proposal']['id']='unrelated'
        else:body['tasks'][0]['rebuild_required']=[]
        with pytest.raises(ValueError):validate_envelope(g,issue(g.owner,g.key,body),g.owner)
    else:
        body=copy.deepcopy(offer['body']);new=copy.deepcopy(body['new']['body'])
        if corruption=='wrong_scope':new['fact']['value']['order']='OTHER'
        if corruption=='invalid_fact':new['fact']['value']['cents']+=1
        issuer='middle_a' if corruption=='foreign_issuer' else 'coordinator'
        body['new']=issue(issuer,nodes[issuer].key,new)
        forged=issue(issuer,nodes[issuer].key,body)
        with pytest.raises(ValueError):prepare_closure_recovery(g,batch,[forged])


def test_dependency_proof_persists_actual_ancestor_revocation_only():
    _,nodes,proposal,batch,offer=setup_recovery();mid=nodes['middle_a'];g=nodes['receiver_b']
    mid.receive(offer['body']['revocation']);target=proposal['claims'][0]
    q={'kind':'reliability_query','workflow':g.workflow,'root':target}
    body=authority_status(mid,q)['body']
    assert body['status']=='revoked' and body['dependency_revocations']
    apply_status_evidence(g,body)
    assert offer['body']['old'] in g.revoked and target not in g.revoked
    assert g.blockers(target)
    bad=copy.deepcopy(body);bad['query']['root']=proposal['claims'][1]
    with pytest.raises(ValueError,match='unrelated'):apply_status_evidence(g,bad)


def test_wrong_completion_binding_and_missing_new_parent_cannot_rebuild():
    _,nodes,proposal,batch,offer=setup_recovery();g=nodes['receiver_a'];mid=nodes['middle_a']
    envelope=prepare_closure_recovery(g,batch,[offer]);old=proposal['claims'][0]
    with pytest.raises(ValueError,match='locally usable'):
        rebuild_frontier_claim(mid,envelope,proposal['id'],{},g.owner,old,offer['body']['new']['body']['fact'])
    mid.receive(offer['body']['new'])
    valid=rebuild_frontier_claim(mid,envelope,proposal['id'],{},g.owner,old,offer['body']['new']['body']['fact'])['packet']
    body=copy.deepcopy(valid['body']);body['recovery_binding']['task_id']='different'
    with pytest.raises(ValueError,match='bound'):
        frontier(g,envelope,proposal['id'],{old:issue(mid.owner,mid.key,body)},g.owner)


def test_no_retry_for_completed_or_effect_unknown():
    _,nodes,_,batch,offer=setup_recovery();g=nodes['receiver_a']
    for outcome in ('COMPLETED','EFFECT_UNKNOWN'):
        body=copy.deepcopy(batch['body']);body['outputs'][0]['action']=outcome
        with pytest.raises(ValueError):prepare_closure_recovery(g,issue(g.owner,g.key,body),[offer])


def test_shared_intermediate_counterexample_and_local_recovery():
    old,truth=run_case('shared_intermediate_revoke','simple_root_gate')
    new,new_truth=run_case('shared_intermediate_revoke','dependency_closure')
    a=evaluate(old,truth);b=evaluate(new,new_truth)
    assert old['scripted_trace_hash']==new['scripted_trace_hash']
    assert a['unsafe_completed']==2 and b['unsafe_completed']==0
    assert b['safe_completed']==4 and b['unrelated_overfreeze']==0 and b['recovery_successes']==2
    assert b['error_forward_messages']<a['error_forward_messages']


def test_single_branch_freeze_preserves_other_branch_and_unrelated_order():
    raw,truth=run_case('branch_intermediate_revoke','dependency_closure')
    m=evaluate(raw,truth)
    assert m['safe_completed']==4 and m['unsafe_completed']==0
    assert m['recovery_attempts']==1 and m['recovery_successes']==1 and m['unrelated_overfreeze']==0


def test_persistent_worker_revision_recovery_and_shared_receiver_allowlist(tmp_path):
    import json
    from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
    from trust_network.demo.claim_worker import handle,recovery_receiver
    _,nodes,proposal,batch,offer=setup_recovery()
    def save(owner):
        g=nodes[owner];directory=tmp_path/owner;directory.mkdir()
        (directory/'config.json').write_text(json.dumps({'owner':owner,'workflow':g.workflow,
            'public_keys':g.public,'authorities':g.authorities,
            'recovery_receivers':['receiver_a','receiver_b']}))
        (directory/'signing.key').write_bytes(g.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
        (directory/'channel_state.json').write_text(json.dumps({'claims':g.claims,'revoked':g.revoked,'events':g.events}))
        return directory
    receiver=save('receiver_a');mid=save('middle_a');issuer=save('coordinator')
    offer=handle(issuer,{'operation':'reliability_claim_revision','old':offer['body']['old'],
        'fact':offer['body']['new']['body']['fact']},tmp_path/'unused.env')['offer']
    envelope=handle(receiver,{'operation':'reliability_closure_recovery','batch':batch,'offers':[offer]},tmp_path/'unused.env')['recovery']
    handle(mid,{'operation':'receive','packet':offer['body']['new']},tmp_path/'unused.env')
    result=handle(mid,{'operation':'reliability_frontier_rebuild','envelope':envelope,
        'task_id':proposal['id'],'completed':{},'old':proposal['claims'][0],
        'fact':offer['body']['new']['body']['fact']},tmp_path/'unused.env')
    assert result['packet']['body']['recovery_binding']['task_id']==proposal['id']
    with pytest.raises(ValueError,match='untrusted'):
        recovery_receiver({'recovery_receivers':['receiver_b']},nodes['middle_a'],envelope)


@pytest.mark.parametrize('case,arm,recovery',[
    ('active','verify_all_closure','bound'),
    ('root_revoke','dependency_closure','bound'),
    ('partial_notice_old_packet','dependency_closure','notice_only')])
def test_remaining_harness_paths_finish_safely(case,arm,recovery):
    raw,truth=run_case(case,arm,recovery);m=evaluate(raw,truth)
    assert m['unsafe_completed']==0 and m['safe_completed']==4
    assert not any(r['error'] for r in raw['recovery'])
    assert m['unrelated_overfreeze']==0


def test_ablation_exposes_task_binding_difference_without_weakening_shared_derivation_checks():
    _,nodes,proposal,batch,offer=setup_recovery();receiver=nodes['receiver_a'];mid=nodes['middle_a']
    envelope=prepare_closure_recovery(receiver,batch,[offer]);old=proposal['claims'][0]
    mid.receive(offer['body']['new'])
    valid=rebuild_frontier_claim(mid,envelope,proposal['id'],{},receiver.owner,old,offer['body']['new']['body']['fact'])['packet']
    body=copy.deepcopy(valid['body']);body['recovery_binding']['task_id']='foreign-task'
    foreign=issue(mid.owner,mid.key,body)
    # An ordinary signed claim passes the unchanged structural channel. The
    # bound recovery protocol rejects it as completion of this particular task.
    assert mid.receive(foreign)['body']['action']=='received'
    with pytest.raises(ValueError,match='bound'):
        frontier(receiver,envelope,proposal['id'],{old:foreign},receiver.owner)
    body['fact']['value']['cents']+=1
    invalid=issue(mid.owner,mid.key,body)
    assert mid.receive(invalid)['body']['action']=='blocked'


def test_revoked_completion_requires_replan_and_is_never_reported_complete():
    _,nodes,proposal,batch,offer=setup_recovery();g=nodes['receiver_a'];mid=nodes['middle_a']
    envelope=prepare_closure_recovery(g,batch,[offer]);old=proposal['claims'][0]
    mid.receive(offer['body']['new'])
    completed=rebuild_frontier_claim(mid,envelope,proposal['id'],{},g.owner,old,offer['body']['new']['body']['fact'])['packet']
    g.receive(completed)
    new_id=digest(completed)
    revoke=issue(mid.owner,mid.key,{'kind':'revoke','workflow':g.workflow,'target':new_id,'original':completed})
    g.receive(revoke)
    state=frontier(g,envelope,proposal['id'],{old:completed},g.owner)
    assert state['requires_replan'] and not state['recovery_complete']
    assert state['invalidated_replacements']=={old:[new_id]}
    assert old not in state['replacement_map'] and state['remaining']==1
    assert state['ready']==[]  # don't reissue the same now-revoked revision
    with pytest.raises(ValueError,match='frontier'):
        rebuild_frontier_claim(g,envelope,proposal['id'],{old:completed},g.owner,old,completed['body']['fact'])


def test_revoked_seed_stops_pending_rebuild_before_model_action():
    _,nodes,proposal,batch,offer=setup_recovery();g=nodes['receiver_a'];mid=nodes['middle_a']
    envelope=prepare_closure_recovery(g,batch,[offer]);seed=offer['body']['new'];mid.receive(seed)
    revoke=issue('coordinator',nodes['coordinator'].key,{'kind':'revoke','workflow':g.workflow,'target':digest(seed),'original':seed})
    mid.receive(revoke)
    state=frontier(mid,envelope,proposal['id'],{},g.owner)
    assert state['requires_replan'] and not state['ready'] and not state['recovery_complete']
    assert proposal['claims'][0] in state['suspended']


def test_recovery_invalidation_preserves_independent_completed_branch():
    f,nodes,_,_,offer=setup_recovery();g=nodes['receiver_a']
    old_b=f['trace']['A']['middle_b']
    for node in nodes.values():node.receive(old_b)
    ids=[digest(f['trace']['A']['middle_a']),digest(old_b)]
    proposal={'id':'two-branches','operation':'forward','claims':ids,'intent':'execute'}
    batch=run_batch(g,[proposal],lambda *args:pytest.fail('known retraction'),lambda p:pytest.fail('blocked'),ReliabilityConfig('dependency_closure'))
    envelope=prepare_closure_recovery(g,batch,[offer]);completed={}
    for issuer,old in zip(('middle_a','middle_b'),ids):
        node=nodes[issuer];node.receive(offer['body']['new'])
        packet=rebuild_frontier_claim(node,envelope,proposal['id'],{},g.owner,old,offer['body']['new']['body']['fact'])['packet']
        completed[old]=packet;g.receive(packet)
    revoke=issue('middle_a',nodes['middle_a'].key,{'kind':'revoke','workflow':g.workflow,
        'target':digest(completed[ids[0]]),'original':completed[ids[0]]})
    g.receive(revoke)
    state=frontier(g,envelope,proposal['id'],completed,g.owner)
    assert state['usable_completed']=={ids[1]:digest(completed[ids[1]])}
    assert list(state['invalidated_replacements'])==[ids[0]]
    assert ids[1] not in state['suspended'] and state['remaining']==1
