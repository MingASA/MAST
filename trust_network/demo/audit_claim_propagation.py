"""Per-organization knowledge ordering, without assuming synchronized clocks."""
import json
from pathlib import Path
import sys
from trust_network.demo.claim_channel import read
from trust_network.demo.documents import digest
from trust_network.demo.claim_derivation import valid_derivation


def audit(root):
    report=json.loads((root/'report.json').read_text()); public=report['public_keys']
    trace=json.loads((root/'trace.json').read_text())
    if digest(trace)!=report['trace_hash']: raise ValueError('trace digest mismatch')
    heads={}; sequences={}; claims={}; notices={}; uses=[]; statuses={}; observed_status={}
    def roots(target):
        if target not in claims: raise ValueError('missing claim provenance')
        parents=claims[target]['parents']
        return set().union(*(roots(p) for p in parents)) if parents else {target}
    for index,row in enumerate(trace):
        owner=row['owner']; request=row['request']; response=row['response']
        if 'reply' in response:
            issuer,status=read(response['reply'],public)
            if issuer!=owner or status['query']!=request['query']: raise ValueError('status query mismatch')
            statuses[digest(response['reply'])]=status
        for packet in ([request['packet']] if request['operation']=='receive' else [])+([response['packet']] if 'packet' in response else []):
            _,body=read(packet,public)
            if body['kind']=='claim':
                if body['parents'] and response['event']['body']['action']=='received':
                    if any(p not in claims for p in body['parents']): raise ValueError('missing derivation input')
                    if not valid_derivation(body.get('rule','relay'),body['fact'],[claims[p]['fact'] for p in body['parents']]):
                        raise ValueError('accepted invalid derivation')
                claims[digest(packet)]=body
        segment=response.get('events') or [response['event']]
        if segment[-1]!=response['event']: raise ValueError('event segment mismatch')
        for signed_event in segment:
            signer,event=read(signed_event,public)
            if signer!=owner or event['sequence']!=sequences.get(owner,0)+1 or event['previous']!=heads.get(owner):
                raise ValueError('organization event chain mismatch')
            sequences[owner]=event['sequence']; heads[owner]=digest(signed_event)
            if event['action']=='authority_status_received':
                status=statuses[event['reasons'][0]]
                observed_status[(owner,status['query']['claim'])]=status
        if event['action']=='revocation_received':
            packet=request['packet']; issuer,body=read(packet,public)
            original_issuer,original=read(body['original'],public)
            if issuer!=original_issuer or digest(body['original'])!=body['target']:
                raise ValueError('revocation authority mismatch')
            notices.setdefault(owner,{})[body['target']]={'sequence':event['sequence'],'receipt_hash':heads[owner]}
        if event['action'] in ('use_allowed','use_blocked'):
            dependency_roots=roots(event['target'])
            received=[notices.get(owner,{}).get(r) for r in dependency_roots]
            known=[n for n in received if n]
            classification=('blocked_after_notice' if event['action']=='use_blocked' else 'allowed_despite_received_notice') if known else 'no_prior_local_revocation_receipt'
            status=observed_status.get((owner,event['target']))
            if not known and status and status['status']!='active':
                classification='blocked_after_authority_check' if event['action']=='use_blocked' else 'allowed_despite_negative_authority_check'
            uses.append({'trace_index':index,'organization':owner,'local_sequence':event['sequence'],
                'claim':event['target'],'roots':sorted(dependency_roots),'classification':classification,
                'prior_notice_receipts':known,'use_event_hash':heads[owner],
                'effect_reported_by_harness':response.get('executed'),
                'effect_proven_by_signature':False})
    result={'per_organization_chains_valid':True,'uses':uses,
        'limits':['local order is proven; wall-clock timing is not',
                  'no local receipt does not prove no knowledge through other channels',
                  'notification duty and deadline are not specified; no fault assigned for delivery delay',
                  'gateway use events authorize or block; physical effects require separate receipts',
                  'report root/public keys are supplied by experiment provisioning, not external trust anchoring']}
    (root/'responsibility_audit.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__': print(json.dumps(audit(Path(sys.argv[1]))))
