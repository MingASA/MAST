"""Bounded transport adapter for signed notices; works with Controller.call.

The adapter reads exported queues, never another worker's private state. A
failed delivery/ACK stays pending. A later invocation retries the same envelope.
"""
from trust_network.demo.documents import digest


def pump_notifications(call,owners,max_deliveries=32):
    if type(max_deliveries) is not int or max_deliveries<0:raise ValueError('invalid delivery budget')
    owners=tuple(dict.fromkeys(owners));known=set(owners);seen=set()
    stats={'delivery_attempts':0,'acknowledged':0,'worker_calls':0,'failures':[],
           'budget_exhausted':False,'model_calls':0}
    def invoke(owner,request,sender):
        stats['worker_calls']+=1
        return call(owner,request,sender=sender)
    while True:
        progressed=False
        for owner in owners:
            try:
                response=invoke(owner,{'operation':'reliability_notifications'},'notification-pump')
                pending=response['pending']
            except (KeyError,ValueError,RuntimeError,OSError) as exc:
                stats['failures'].append({'owner':owner,'phase':'poll','error':type(exc).__name__});continue
            for notice in pending:
                key=(owner,digest(notice))
                if key in seen:continue
                if stats['delivery_attempts']>=max_deliveries:
                    stats['budget_exhausted']=True;return stats
                seen.add(key);progressed=True;stats['delivery_attempts']+=1
                try:
                    recipient=notice['body']['recipient']
                    if recipient not in known:raise ValueError('no configured notification endpoint')
                    response=invoke(recipient,{'operation':'reliability_notification_accept','packet':notice},owner)
                    receipt=response['result']
                    ack=invoke(owner,{'operation':'reliability_notification_ack','packet':receipt},recipient)
                    if ack.get('result',{}).get('acknowledged') is not True:raise ValueError('ACK not persisted')
                    stats['acknowledged']+=1
                except (KeyError,ValueError,RuntimeError,OSError) as exc:
                    stats['failures'].append({'owner':owner,'notice':key[1],'phase':'delivery_or_ack','error':type(exc).__name__})
        if not progressed:return stats


def guarded_handoff(call,sender,recipient,claims,proposal_id):
    """Policy-gated prepare -> peer registration -> signed ACK persistence.

    Returning PREPARED does not mean delivered. No business action is executed
    by the receiving organization. Both helpers accept WorkflowController.call.
    """
    prepared=call(sender,{'operation':'reliability_handoff_prepare','id':proposal_id,
        'recipient':recipient,'claims':claims},sender='handoff-runtime')
    batch=prepared.get('batch')
    if not batch:return {'status':'PREPARATION_UNKNOWN','response':prepared,'action_authorized':False}
    outcome=batch['body']['outputs'][0]
    result={'status':'PREPARATION_BLOCKED','batch':batch,'action_authorized':False}
    if outcome['action']=='EFFECT_UNKNOWN':result['status']='PREPARATION_UNKNOWN'
    if outcome['action']!='COMPLETED':return result
    packet=outcome['result']['handoff'];result.update(status='DELIVERY_UNKNOWN',handoff=packet)
    try:
        received=call(recipient,{'operation':'reliability_handoff_accept','packet':packet},sender=sender)
        receipt=received['result'];result.update(status='ACK_PENDING',receipt=receipt)
        ack=call(sender,{'operation':'reliability_handoff_ack','packet':receipt},sender=recipient)
        if ack.get('result',{}).get('registered') is not True:return result
        result['status']='RECEIVED_BLOCKED' if receipt['body']['status']=='blocked' else 'RECEIVED'
    except (KeyError,ValueError,RuntimeError,OSError) as exc:
        result['transport_error']=type(exc).__name__
    return result
