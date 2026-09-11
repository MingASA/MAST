import copy
import pytest
from trust_network.benchmark.fact_basis import run
from trust_network.benchmark.workflow.spec import workload,ARMS
from trust_network.benchmark.workflow.backend import MemoryBackend
from trust_network.demo.fact_evidence import scope_key,attest,inspect,SCOPE
from trust_network.demo.claim_channel import issue
from trust_network.demo.documents import digest


def test_selectivity_tradeoff_and_unknown_fail_closed():
    baseline=run('unconfirmed_settlement_basis','closure_only')[2]
    all_checks=run('unconfirmed_settlement_basis','verify_all')[2]
    selective=run('unconfirmed_settlement_basis','selective')[2]
    assert baseline['unsafe_completed']==2
    assert all_checks['unsafe_completed']==selective['unsafe_completed']==0
    assert all_checks['error_accepting_organizations']<selective['error_accepting_organizations']
    for policy in ('verify_all','selective'):
        unknown=run('authority_unknown',policy)[2]
        assert unknown['unsafe_completed']==0 and unknown['safe_completed']==2
        assert unknown['disputed_claims']==0
    normal_all=run('confirmed_basis','verify_all')[2];normal_selective=run('confirmed_basis','selective')[2]
    assert normal_selective['safe_completed']==normal_all['safe_completed']==4
    assert normal_selective['fact_queries']<normal_all['fact_queries']


def test_conflict_trigger_has_hidden_error_boundary():
    assert run('conflicting_basis','conflict_triggered')[2]['unsafe_completed']==0
    assert run('unconfirmed_settlement_basis','conflict_triggered')[2]['unsafe_completed']==2


def test_attestation_exact_request_expiry_and_authority():
    f=workload();b=MemoryBackend(f,ARMS['dependency']);g=b.nodes['buyer'];root=f['roots']['A']
    q={'scope':SCOPE,'workflow':g.workflow,'requester':'coordinator','authority':'buyer',
       'batch':'b1','proposal':'p1','nonce':'n1','claim':root,'claim_id':digest(root)}
    wire={'kind':'fact_evidence_query','request':issue('coordinator',f['keys']['coordinator'],q)}
    ledger={scope_key(g.workflow,root['body']['fact']):{'cents':100,'version':'v1','status':'confirmed'}}
    reply=attest(g,ledger,wire,now=10)
    assert inspect(reply,wire,g.public,'buyer',20)=='CONFIRMED'
    with pytest.raises(ValueError):inspect(reply,wire,g.public,'buyer',310)
    with pytest.raises(ValueError):inspect(reply,wire,g.public,'source',20)
    changed={'kind':'fact_evidence_query','request':issue('coordinator',f['keys']['coordinator'],{**q,'nonce':'other'})}
    with pytest.raises(ValueError):inspect(reply,changed,g.public,'buyer',20)


def test_dispute_persists_without_forged_revoke_and_C_continues():
    f=workload();ledger={scope_key(f['workflow'],f['roots'][o]['body']['fact']):
        {'cents':125 if o=='A' else 100,'version':'v1','status':'confirmed'} for o in ('A','C')}
    b=MemoryBackend(f,ARMS['dependency'],private_state={'buyer':{'settlement_registry':ledger}})
    for g in b.nodes.values():
        for o in ('A','C'):
            for p in [f['roots'][o],f['auth'][o],f['trace'][o]['coordinator'],f['trace'][o]['middle_a']]:g.receive(p)
    owner='receiver_a';b.configs[owner]['fact_policy']={'policy':'verify_all','authority':'buyer'}
    def submit(order,intent='execute'):
        return b.call(owner,{'operation':'reliability_batch','proposals':[{'id':order,'operation':'approve_invoice','intent':intent,
            'order':order,'claims':[digest(f['trace'][order]['middle_a']),digest(f['auth'][order])]}]})['batch']
    first=submit('A');assert first['body']['outputs'][0]['action']=='REQUEST_EVIDENCE'
    g=b.nodes[owner];assert g.fact_disputes and not g.revoked
    saved=g.snapshot();g.restore(saved);assert g.fact_disputes
    b._private['buyer']['settlement_registry'][scope_key(f['workflow'],f['roots']['A']['body']['fact'])]['cents']=100
    assert submit('A')['body']['outputs'][0]['action']=='REQUEST_EVIDENCE'
    assert submit('C','verify')['body']['outputs'][0]['action']=='VERIFIED'
    assert submit('C')['body']['outputs'][0]['action']=='COMPLETED'
    from trust_network.demo.reliability_audit import audit_with_authorities
    from trust_network.benchmark.workflow.spec import AUTHORITIES
    assert audit_with_authorities(first,f['public'],AUTHORITIES,{SCOPE:'buyer'})['policy_replay_valid']
    with pytest.raises(ValueError):audit_with_authorities(first,f['public'],AUTHORITIES)
    forged=copy.deepcopy(first['body']);forged['fact_checks']={};forged['fact_verification_calls']=0
    forged['outputs'][0]['action']='COMPLETED'
    with pytest.raises(ValueError):audit_with_authorities(issue(owner,f['keys'][owner],forged),f['public'],AUTHORITIES,{SCOPE:'buyer'})
