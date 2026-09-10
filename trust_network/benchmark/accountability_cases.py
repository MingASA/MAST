"""Small explicit duty-label suite. Labels are never passed to the auditor.

Claims of accuracy concern this declared receipt/use duty, not legal blame.
Positive cases deliberately model an actor violating the enforced protocol.
"""
import copy
from trust_network.demo.claim_channel import ClaimGateway,issue
from trust_network.demo.documents import digest
from trust_network.benchmark.containment import fixture,run,AUTHORITIES
from trust_network.benchmark.accountability import audit


def evaluate_cases():
    f=fixture('active');base=run(f,'unmediated');root=digest(f['roots']['A'])
    specifications=[
        ('own_notice_then_use','a','a','before','use_after_own_notice'),
        ('other_notice_then_use','a','b','before','no_proven_notice_violation'),
        ('notice_after_use','b','b','after','no_proven_notice_violation'),
        ('missing_notice',None,'b',None,'no_proven_notice_violation'),
        ('tampered_use_signature',None,'b',None,'invalid_evidence'),
        ('missing_middle_event',None,'b',None,'invalid_evidence')]
    rows=[]
    for name,notified,actor,when,expected in specifications:
        raw=copy.deepcopy(base)
        def append(kind,**fields):
            e={'kind':kind,'tick':15+len(raw['events']),'sequence':len(raw['events']),
               'previous':digest(raw['events'][-1]),**fields}
            raw['events'].append(e);return e['sequence']
        local_gateways={}
        def notice(branch):
            owner='receiver_'+branch
            g=ClaimGateway(owner,f['keys'][owner],f['public'],f['workflow'],AUTHORITIES)
            local_gateways[owner]=g
            receipt=g.receive(f['revoke'])
            append('notice',owner=owner,root=root,receipt=receipt)
        if when=='before':notice(notified)
        owner='receiver_'+actor;proposal={'id':'duty-case','operation':'forward','claims':[root]}
        receipt=issue(owner,f['keys'][owner],{'kind':'benchmark_use','workflow':f['workflow'],
                                            'proposal':proposal,'action':'COMPLETED',
                                            'local_head':digest(local_gateways[owner].events[-1]) if owner in local_gateways else None})
        target=append('gate',owner=owner,order='A',outcome={'action':'COMPLETED','use_receipt':receipt})
        if when=='after':notice(notified)
        if name=='tampered_use_signature':raw['events'][target]['outcome']['use_receipt']['body']['proposal']['id']='changed'
        if name=='missing_middle_event':raw['events'].pop(1)
        try:
            findings=audit(raw)['findings']
            actual=next(e['classification'] for e in findings if e['event']==target)
        except (ValueError,KeyError):actual='invalid_evidence'
        rows.append({'case':name,'expected':expected,'actual':actual,'matched':actual==expected})
    positive=[r for r in rows if r['expected']=='use_after_own_notice']
    abstain=[r for r in rows if r['expected']=='no_proven_notice_violation']
    corrupted=[r for r in rows if r['expected']=='invalid_evidence']
    # Independently supplied fixture identity labels: not inferred from auditor.
    localization=[]
    for scenario,location,expected_issuer in [('signed_false','coordinator','source'),
                                             ('derived_error','coordinator','coordinator'),
                                             ('derived_error','middle_a','middle_a')]:
        case=fixture(scenario,fault_location=location);raw=run(case,'unmediated');report=audit(raw)
        if scenario=='signed_false':actual=report['source_issuers'].get(digest(case['roots']['A']))
        else:
            target=digest(case['trace']['A'][location])
            actual=next((r['issuer'] for r in report['invalid_transformations'] if r['claim']==target),None)
        localization.append({'case':scenario+':'+location,'expected':expected_issuer,'actual':actual,
                             'matched':actual==expected_issuer})
    return {'cases':rows,'localization':localization,
        'duty_detection':{'detected':sum(r['matched'] for r in positive),'positive_cases':len(positive)},
        'false_accusations':{'count':sum(r['actual']=='use_after_own_notice' for r in abstain),'negative_cases':len(abstain)},
        'evidence_limited_abstention':{'correct':sum(r['matched'] for r in abstain),'eligible_cases':len(abstain)},
        'corruption_detection':{'detected':sum(r['matched'] for r in corrupted),'corrupt_cases':len(corrupted)},
        'localization_accuracy':{'correct':sum(r['matched'] for r in localization),'cases':len(localization)},
        'limits':['tiny_constructed_label_suite_not_population_accuracy',
                  'source_identity_is_not_proof_of_source_factual_error',
                  'controller_record_deletion_is_detected_against_existing_chain_not_against_rewritten_history'],
        'new_model_calls':0}
