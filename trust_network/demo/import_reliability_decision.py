"""Import an external model record without inference, repair, or paid calls.

Hashes bind supplied artifacts, not proof that a provider actually produced them.
The caller retains the provider's raw request/response alongside this record.
"""
import argparse
import json
from pathlib import Path
from trust_network.demo.documents import digest


def import_decision(model_input, record, output):
    source=json.loads(model_input.read_text())
    data=json.loads(record.read_text())
    if data.get('input_hash') != digest(source):
        raise ValueError('model input hash mismatch')
    if not isinstance(data.get('model'),str) or not data['model']:
        raise ValueError('model identifier required')
    status=data.get('status')
    if status not in ('success','provider_error'):
        raise ValueError('status must be success or provider_error')
    usage=data.get('usage')
    if usage is not None:
        if not isinstance(usage,dict):
            raise ValueError('usage must be an object or null')
        for name,value in usage.items():
            if type(value) is not int or value < 0:
                raise ValueError('usage entries must be nonnegative integer counts')
    proposals=[]
    classification='provider_error'
    if status=='success':
        decision=data.get('decision')
        if not isinstance(decision,dict) or decision.get('action') not in ('approve','hold'):
            classification='invalid_model_decision'
        elif decision['action']=='hold':
            classification='model_hold'
        else:
            claims=decision.get('claims')
            if not isinstance(claims,list) or not claims or not all(isinstance(c,str) for c in claims) or len(set(claims))!=len(claims):
                classification='invalid_model_decision'
            else:
                # Preserve wrong/missing evidence references: runtime must decide,
                # never silently repair them with the input's expected IDs.
                proposals=[{'id':'invoice-A','operation':'approve_invoice','order':'A','claims':claims}]
                classification='model_approve'
    output.mkdir(parents=True,mode=0o700,exist_ok=False)
    (output/'model_input.json').write_bytes(model_input.read_bytes())
    (output/'model_record.json').write_bytes(record.read_bytes())
    (output/'proposals.json').write_text(json.dumps(proposals,indent=2))
    provenance={'input_hash':digest(source),'record_hash':digest(data),
                'proposal_hash':digest(proposals),'classification':classification,
                'model':data['model'],'usage':usage,'usage_unknown':usage is None,
                'provider_origin_independently_verified':False,
                'new_model_calls':0}
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2))
    return provenance


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-input',type=Path,required=True)
    p.add_argument('--record',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(); import_decision(a.model_input,a.record,a.out)
