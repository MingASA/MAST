"""Transfer explicit terminal decisions, not historical signatures, to logical roles."""
import argparse
import hashlib
import json
from pathlib import Path
from trust_network.demo.documents import digest
from trust_network.benchmark.workflow.evaluate import decision_citations


def convert(raw):
    tape={};bindings=[];omitted=[]
    for d in raw['decisions']:
        stage=d['stage'];parts=stage.split(':');target=None
        if len(parts)>=3 and parts[0]=='forward' and parts[1] in ('middle_a','middle_b'):
            target='forward:'+parts[2]+'_'+parts[1][-1]
        elif len(parts)>=3 and parts[0]=='invoice':
            target='initial:'+parts[1]+'_'+parts[2]
        if target is None:
            omitted.append({'stage':stage,'reason':'outside_terminal_scope'});continue
        if 'after_verify' in parts:
            if parts[-1]!='1':
                omitted.append({'stage':stage,'reason':'bounded_one_post_verify_round'});continue
            target+=':after_verify'
        draft=d['draft'];action={'approve':'proceed','forward':'proceed','proceed':'proceed',
                                 'hold':'hold','verify':'verify'}.get(draft.get('action'),'hold')
        refs=decision_citations(draft,d['public_input'])
        packets={digest(p):p for p in d['public_input']['public_claims']}
        expected_order=target.split(':')[1].split('_')[0]
        roles=[]
        for cid in refs:
            f=packets.get(cid,{}).get('body',{}).get('fact',{})
            if f.get('value',{}).get('order')!=expected_order:roles.append('invalid');continue
            roles.append({'total_charge':'@total','invoice_authorization':'@authorization'}.get(f.get('predicate'),'invalid'))
        expected={'@total','@authorization'} if target.startswith('initial:') else {'@total'}
        if action!='hold' and (len(roles)!=len(expected) or set(roles)!=expected):
            action='hold';reason='invalid_original_reference_scope'
        else:reason=draft.get('reason','archived_decision')
        tape[target]={'action':action,'reason':reason}
        if target.startswith('initial:') and action!='hold':tape[target]['claim_refs']=roles
        bindings.append({'original_stage':stage,'new_stage':target,'original_claims':refs,'business_roles':roles})
    return {'tape':tape,'bindings':bindings,'omitted':omitted,
            'limits':['terminal_decision_transfer_to_new_topology_not_exact_historical_execution',
                      'no_new_model_decision_or_signature','missing_stages_hold']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=convert(json.loads(args.trace.read_text()))
    result['source_sha256']=hashlib.sha256(args.trace.read_bytes()).hexdigest()
    result['source']=str(args.trace)
    with args.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)

if __name__=='__main__':main()
