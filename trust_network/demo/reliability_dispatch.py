"""Bounded VERIFY -> evidence -> explicit decision dispatch, shared by runners."""
from trust_network.demo.reliability_stage import STAGE_SEMANTICS
from trust_network.demo.reliability_accountability import append_event


def apply_actions(controller,parsed,stage,parse_receiver):
    proposals,forced,stats=parsed
    if not isinstance(stats,dict):return [],stats
    stats=dict(stats);batches=[];round_number=0
    while proposals:
        forced_ids=set(forced)
        normal=[p for p in proposals if p['id'] not in forced_ids and p.get('intent')!='verify']
        checking=[dict(p,intent='verify') for p in proposals if p['id'] in forced_ids or p.get('intent')=='verify']
        recent=[]
        if normal:recent.append(controller.run_batch(normal,stage,False))
        if checking:recent.append(controller.run_batch(checking,stage,True))
        recent=[b for b in recent if b is not None];batches.extend(recent)
        pending=[];packets=[];public={}
        for batch in recent:
            verified={o['proposal'] for o in batch['outputs'] if o['action']=='VERIFIED'}
            pending.extend(p for p in batch['proposals'] if p['id'] in verified)
            if verified and batch.get('packet'):
                packets.append(batch['packet'])
                for packet in batch['packet']['body']['evidence']['claims']:
                    from trust_network.demo.documents import digest
                    public[digest(packet)]=packet
        if not pending:break
        # VERIFY never grants permission to execute. In particular, do not call
        # model()'s exhausted-budget fallback and do not manufacture an approval.
        if controller.model_count>=controller.max_model_decisions:
            append_event(controller.events,{'kind':'awaiting_explicit_action','stage':stage,
                'proposals':[p['id'] for p in pending],'reason':'model_decision_budget_exhausted'})
            stats['awaiting_explicit_action']=len(pending);break
        specs=[(p['id'],('approve','verify','hold') if p['operation']=='approve_invoice' else ('forward','verify','hold'),p['claims']) for p in pending]
        model_input={'role':'receiver','task':'权威核验已结束但尚未执行任何业务动作。根据返回证据明确选择approve/forward、再次verify或hold；VERIFIED不是自动执行许可。',
            'candidate_claims':{p['id']:p['claims'] for p in pending},
            'public_claims':[{'claim_id':cid,**p} for cid,p in public.items()],
            'verification_evidence':packets,'stage_semantics':STAGE_SEMANTICS,
            'output_schema':{'actions':[{'id':pid,'action':'|'.join(actions),'claims':claims,'reason':'string'} for pid,actions,claims in specs]}}
        round_number+=1
        summary=controller.model('receiver',model_input,f'{stage}_receiver_after_verify_{round_number}')
        proposals,forced,next_stats=parse_receiver(summary,specs)
        if not isinstance(next_stats,dict):
            stats['post_verification_model_error']=next_stats;break
        for key,value in next_stats.items():stats[key]=stats.get(key,0)+value
    return batches,stats
