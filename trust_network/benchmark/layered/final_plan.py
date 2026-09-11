"""Frozen business fixtures shared across layers; never pass evaluator fields to nodes."""
import copy
from .spec import TOPOLOGIES, CASES, MAIN
from trust_network.demo.documents import digest
from trust_network.demo.claim_channel import issue
from trust_network.benchmark.contribution.generalization import build_topology

ABLATIONS=('L4_no_push','L4_no_fact','L4_no_recovery','L3_coarse','verify_all')


def materialize(fixture):
    s=build_topology(fixture['topology'],fixture['seed'])
    s['workflow']=fixture['fixture_id']
    old={digest(p):k for k,p in s['claims'].items()};new={}
    for key,packet in s['claims'].items():
        body=copy.deepcopy(packet['body']);body['workflow']=s['workflow']
        body['parents']=[digest(new[old[parent]]) for parent in body['parents']]
        body['fact']['value'].update(cents=fixture['business']['base_cents'],currency=fixture['business']['currency'])
        owner=packet['signature']['issuer'];new[key]=issue(owner,s['keys'][owner],body)
    s['claims']=new
    for task in s['tasks']:task['claim']=digest(new[task['claim_key']])
    return s


def fixture(topology,case,repetition):
    f={'fixture_id':f'final-v1:{topology}:{case}:business-{repetition}',
       'topology':topology,'case':case,'repetition':repetition,'seed':1000+repetition,
       'business':({'base_cents':12800,'corrected_cents':15600,'maximum_cents':20000,
                    'tampered_cents':13500,'currency':'CNY'} if repetition==0 else
                   {'base_cents':43750,'corrected_cents':51250,'maximum_cents':60000,
                    'tampered_cents':45100,'currency':'USD'}),
       'notice_delay':(8+repetition if case=='late_notice' else 1),
       'timing':{'fault':10,'action':12,'repair':20,'end':30},
       'deadline_semantics':'virtual action scheduling, not a wall-clock service SLA'}
    s=materialize(f);reverse={digest(p):k for k,p in s['claims'].items()}
    def lineage(k):return {k}.union(*(lineage(reverse[p]) for p in s['claims'][k]['body']['parents']))
    fault_ref=('root_A' if case=='root_retraction' else
               s['fault_claims']['branch_middle' if case=='branch_retraction' else 'shared_upstream'])
    affected=[]
    if case!='active':
        affected=[t['id'] for t in s['tasks'] if (fault_ref in lineage(t['claim_key']) if case in
            ('root_retraction','intermediate_retraction','branch_retraction','late_notice') else
            t['id']=='A_a' if case=='tampered_handoff' else t['id'].startswith('A'))]
    wrong=case in ('signed_false','conflicting_sources','confirmed_repair','authority_unknown')
    f['evaluation']={'affected_tasks':affected,'unrelated_tasks':[t['id'] for t in s['tasks'] if t['id'] not in affected],
        'fault_ref':fault_ref if 'retraction' in case or case=='late_notice' else None,
        'fault_kind':case,'fault_injection_tick':0 if wrong or case=='tampered_handoff' else 10 if case!='active' else None,
        'private_expected_cents':{p['body']['fact']['value']['order']:(f['business']['corrected_cents'] if wrong and p['body']['fact']['value']['order']=='A' else f['business']['base_cents']) for p in s['claims'].values()},
        'authority_status':'unknown' if case=='authority_unknown' else 'confirmed',
        'expected_frontier':{t['id']:sorted(lineage(t['claim_key'])) for t in s['tasks'] if t['id'] in affected}}
    f['graph']={'organizations':[*s['organizations'],'buyer'],'edges':s['routes'],'tasks':s['tasks'],
                'claims':{k:p['body'] for k,p in s['claims'].items()},
                'private_state_owner':'buyer; revision candidate at source',
                'business_effect':'simulated invoice approval'}
    f['canonical_hash']=digest(f)
    return f


def make_plan():
    fixtures=[fixture(t,c,r) for t in TOPOLOGIES for c in CASES for r in range(2)]
    runs=[]
    for f in fixtures:
        layers=list(MAIN)
        # Complete matched ten-scene secondary matrix at one topology/business variant.
        if f['topology']==TOPOLOGIES[0] and f['repetition']==0:layers+=list(ABLATIONS)
        for layer in layers:
            runs.append({'index':len(runs),'workflow_id':f"w{len(runs):04d}",
                'fixture_id':f['fixture_id'],'fixture_hash':f['canonical_hash'],'layer':layer,
                'group':'main' if layer in MAIN else 'ablation'})
    plan={'version':'final-unified-live-v1','fixtures':fixtures,'runs':runs,
          'limits':{'decisions_per_workflow':28,'attempts_per_workflow':56,'output_tokens':2048,
                    'temperature':.2},'main_workflows':300,'ablation_workflows':50,
          'sampling':'60 controlled fixtures; two semantic variants, not independent natural-world draws'}
    plan['canonical_hash']=digest(plan)
    return plan


def verify_plan(plan):
    body={k:v for k,v in plan.items() if k!='canonical_hash'}
    if digest(body)!=plan['canonical_hash']:raise ValueError('plan hash mismatch')
    fixtures={f['fixture_id']:f for f in plan['fixtures']}
    if len(fixtures)!=60 or len(plan['runs'])!=350:raise ValueError('incomplete plan')
    for f in fixtures.values():
        if digest({k:v for k,v in f.items() if k!='canonical_hash'})!=f['canonical_hash']:
            raise ValueError('fixture hash mismatch')
        layers=[r['layer'] for r in plan['runs'] if r['fixture_id']==f['fixture_id'] and r['group']=='main']
        if sorted(layers)!=list(MAIN):raise ValueError('unpaired fixture')
    if len({r['workflow_id'] for r in plan['runs']})!=350:raise ValueError('duplicate workflow')
    for r in plan['runs']:
        if r['fixture_hash']!=fixtures[r['fixture_id']]['canonical_hash']:raise ValueError('wrong fixture binding')
    return fixtures
