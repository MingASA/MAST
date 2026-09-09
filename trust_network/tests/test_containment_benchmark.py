import copy
import pytest
from trust_network.benchmark.bus import MessageBus
from trust_network.benchmark.containment import fixture,run,evaluate,POLICIES
from trust_network.benchmark.accountability import audit
from trust_network.benchmark.recovery_probe import probe


def test_delay_bus_freezes_payload_and_fifo():
    bus=MessageBus(); p={'value':1};seen=[]
    bus.send('a','b',p,2);p['value']=7
    bus.send('a','c',{'value':2},1)
    bus.until(1,lambda e:seen.append(e['payload']['value']));assert seen==[2]
    bus.until(2,lambda e:seen.append(e['payload']['value']));assert seen==[2,1]


def test_paired_topology_and_negative_control():
    f=fixture('signed_false');hashes=set()
    for policy in POLICIES:
        raw=run(f,policy);m=evaluate(raw,f['truth']);hashes.add(raw['scripted_trace_hash'])
        assert m['unsafe_completed']==2 and m['max_error_acceptance_hop']==3
        assert m['contaminated_branches']==2 and m['unrelated_overfreeze']==0
        assert audit(raw)['causal_legal_blame']=='undetermined'
    assert len(hashes)==1


def test_derived_error_location_does_not_contaminate_clean_sibling():
    f=fixture('derived_error',fault_location='middle_a')
    for policy in POLICIES:
        raw=run(f,policy);m=evaluate(raw,f['truth'])
        assert m['unsafe_completed']==0 and m['safe_completed']==3
        assert m['max_error_acceptance_hop']==0
        assert audit(raw)['invalid_transformations'][0]['issuer']=='middle_a'


def test_partial_notice_not_global_knowledge_and_trace_tamper():
    f=fixture('delayed_revoke');raw=run(f,'unmediated')
    m=evaluate(raw,f['truth']);a=audit(raw)
    assert m['unsafe_completed']==1
    uses=[x for x in a['findings'] if x['organization']=='receiver_b']
    assert uses and all(x['classification']=='no_proven_notice_violation' for x in uses)
    raw['events'][0]['tick']=999
    with pytest.raises(ValueError,match='chain'):audit(raw)


def test_new_frontier_closes_multilayer_recovery_gap_without_changing_v1():
    f=fixture('delayed_revoke')
    old=probe(f,'dependency');new=probe(f,'frontier_v2');notice=probe(f,'recovery_ablation')
    assert not old['recovered'] and 'one derived' in old['error']
    assert new['recovered'] and new['derived_rebuilt']==2 and new['old_revocation_retained']
    assert notice['recovered']  # Correct fixed output alone does not prove evidence usability benefit.


def test_frontier_rejects_out_of_order_completion_wrong_receiver_and_wrong_fact(monkeypatch):
    import trust_network.benchmark.recovery_probe as module
    from trust_network.demo.recovery_frontier import frontier
    original=module.rebuild_frontier_claim
    checked=[]
    def guarded(gateway,envelope,task_id,completed,receiver,old_id,fact):
        state=frontier(gateway,envelope,task_id,completed,receiver)
        if gateway.owner=='coordinator':
            task=envelope['body']['tasks'][0]
            later=next(n for n in task['rebuild_required'] if n['issuer'].startswith('middle_'))
            assert later['old'] not in {n['old'] for n in state['ready']}
            with pytest.raises(ValueError,match='unfinished parent'):
                frontier(gateway,envelope,task_id,{later['old']:gateway.claims[later['old']]},receiver)
            with pytest.raises(ValueError,match='authority'):
                frontier(gateway,envelope,task_id,completed,'another_receiver')
            wrong=copy.deepcopy(fact);wrong['value']['cents']+=1
            before=(len(gateway.claims),len(gateway.events))
            with pytest.raises(ValueError,match='derivation'):
                original(gateway,envelope,task_id,completed,receiver,old_id,wrong)
            assert before==(len(gateway.claims),len(gateway.events))
            checked.append(True)
        return original(gateway,envelope,task_id,completed,receiver,old_id,fact)
    monkeypatch.setattr(module,'rebuild_frontier_claim',guarded)
    assert module.probe(fixture('delayed_revoke'),'frontier_v2')['recovered'] and checked


def test_audit_detects_signed_use_after_own_notice_without_assigning_legal_blame():
    from trust_network.demo.claim_channel import issue
    from trust_network.demo.documents import digest
    f=fixture('delayed_revoke');raw=run(f,'unmediated')
    # Deliberately faulty actor reports use after its own signed notice receipt.
    proposal={'id':'fault-injection','operation':'forward','claims':[digest(f['roots']['A'])]}
    receipt=issue('receiver_a',f['keys']['receiver_a'],{'kind':'benchmark_use','workflow':f['workflow'],
        'proposal':proposal,'action':'COMPLETED'})
    raw['events'].append({'kind':'gate','tick':13,'sequence':len(raw['events']),
        'previous':digest(raw['events'][-1]),'owner':'receiver_a','order':'A',
        'outcome':{'action':'COMPLETED','use_receipt':receipt}})
    findings=audit(raw)['findings']
    assert findings[-1]['classification']=='use_after_own_notice'
    assert findings[-1]['causal_legal_blame']=='undetermined'


def test_closed_loop_keeps_state_and_task_denominator_and_does_not_retry_unsafe_completion():
    f=fixture('delayed_revoke');f['truth']['invalid_from']=5
    for policy,safe in [('dependency',2),('frontier_v2',4),('unmediated',2)]:
        raw=run(f,policy,lifecycle=True);m=evaluate(raw,f['truth'])
        assert m['task_denominator']==4 and m['safe_completed']==safe
        assert m['unrelated_overfreeze']==0
        if policy=='frontier_v2':
            assert m['recovery_successes']==2 and m['unsafe_completed']==0
            assert len([e for e in raw['events'] if e['kind']=='task_end'])==6
            assert all(r['old_revocation_retained'] for r in raw['recovery'])
        if policy=='unmediated':
            assert m['unsafe_completed']==1
            assert not next(r for r in raw['recovery'] if r['branch']=='b')['attempted']
        audit(raw)


def test_accountability_label_suite_has_no_cross_receiver_false_accusation():
    from trust_network.benchmark.accountability_cases import evaluate_cases
    scores=evaluate_cases()
    assert all(r['matched'] for r in scores['cases'])
    assert scores['false_accusations']=={'count':0,'negative_cases':3}
    assert scores['duty_detection']=={'detected':1,'positive_cases':1}
    assert scores['localization_accuracy']=={'correct':3,'cases':3}
