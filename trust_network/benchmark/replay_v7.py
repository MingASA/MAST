"""Re-execute archived v7 proposals and derived rebuilds without calling a model.

Signatures, original proposals and evidence are retained. Fresh query challenges
are re-signed by local archived authority keys; outcomes, not random bytes, are
compared. Archived model decisions are not counted as new independent samples.
"""
import copy
import hashlib
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from trust_network.demo.claim_channel import ClaimGateway,issue
from trust_network.demo.documents import digest
from trust_network.demo.network_reliability import run_batch,ReliabilityConfig
from trust_network.demo.reliability_audit import audit_with_authorities
from trust_network.demo.reliability_recovery import rebuild_derived_claim


def replay(directory):
    directory=Path(directory)
    integrity=json.loads((directory/'raw_integrity_manifest.json').read_text())
    for entry in integrity['files']:
        path=directory/entry['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('archived integrity failure: '+entry['path'])
    rows=[]
    for path in sorted(directory.glob('hidden_revoke/repeat_*/*/run_record.json')):
        run_dir=path.parent; record=json.loads(path.read_text())
        config=json.loads((run_dir/'orgs'/'receiver'/'config.json').read_text())
        keys={o:Ed25519PrivateKey.from_private_bytes((run_dir/'orgs'/o/'signing.key').read_bytes()) for o in config['public_keys']}
        comparisons=[]
        for item in record['batches']:
            saved=json.loads((run_dir/item['path']).read_text())
            # Batch files contain the signed packet directly in current v7.
            if 'body' not in saved: saved=saved['response']['batch']
            body=saved['body']; original_plan=body['plan']['body']['plan']
            audit_with_authorities(saved,config['public_keys'],config['authorities'])
            gateway=ClaimGateway('receiver',keys['receiver'],config['public_keys'],record['workflow'],config['authorities'])
            pending=list(body['evidence']['claims'])
            while pending:
                ready=[p for p in pending if all(c in gateway.claims for c in p['body']['parents'])]
                if not ready: raise ValueError('incomplete archived graph')
                for packet in ready: gateway.receive(packet); pending.remove(packet)
            for packet in body['evidence']['revocations']: gateway.receive(packet)
            replies={r['body']['query']['root']:r for r in body['replies']}
            def answer(owner,query):
                prior=replies.get(query['root'])
                if prior is None: raise ValueError('unobserved counterfactual reply')
                reply=copy.deepcopy(prior['body']); reply['query']=query
                return issue(owner,keys[owner],reply)
            generated=run_batch(gateway,body['plan']['body']['proposals'],answer,
                lambda p:{'simulated':True,'proposal':p['id'],'operation':p['operation']},
                ReliabilityConfig(**original_plan['config']))
            expected=[(o['proposal'],o['action']) for o in body['outputs']]
            actual=[(o['proposal'],o['action']) for o in generated['body']['outputs']]
            comparisons.append({'stage':item['stage'],'expected':expected,'actual':actual,'matched':actual==expected,
                                'original_proposal_hash':digest(body['plan']['body']['proposals'])})
        rebuilt=None; ablation=None
        if (run_dir/'recovery_evidence.json').exists():
            evidence=json.loads((run_dir/'recovery_evidence.json').read_text())
            c=json.loads((run_dir/'orgs'/'coordinator'/'config.json').read_text())
            state=json.loads((run_dir/'orgs'/'coordinator'/'channel_state.json').read_text())
            gateway=ClaimGateway('coordinator',keys['coordinator'],c['public_keys'],c['workflow'],c['authorities'])
            gateway.claims=state['claims']; gateway.revoked=state['revoked']; gateway.events=state['events']
            draft=next(d['draft'] for d in record['model_decisions'] if d['stage']=='recovery_coordinator')
            new_id=record['recovery']['new_total']; gateway.claims.pop(new_id,None)
            packet=rebuild_derived_claim(gateway,evidence['signed_artifacts']['recovery_envelope'],evidence['task'],draft['fact'],evidence=evidence)
            rebuilt={'matched_archived_claim':digest(packet)==new_id,'source':'archived_actual_model_fact'}
            # Mechanical proof-omission boundary only. Not the model-availability
            # ablation: a proper notice-only arm must change the adapter contract.
            try:
                rebuild_derived_claim(gateway,evidence['signed_artifacts']['recovery_envelope'],evidence['task'],draft['fact'],evidence=None)
                ablation='unexpected_accept'
            except ValueError: ablation='missing_bundle_rejected'
        rows.append({'run':str(run_dir.relative_to(directory)),'batch_replays':comparisons,
                     'rebuild':rebuilt,'binding_boundary':ablation})
    return {'source_directory':str(directory),'integrity_files':len(integrity['files']),
            'runs':rows,'all_batches_matched':all(b['matched'] for r in rows for b in r['batch_replays']),
            'new_model_calls':0,'scope':'same-policy archived decision replay, not new live samples'}
