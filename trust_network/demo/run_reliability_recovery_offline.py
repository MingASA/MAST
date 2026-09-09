"""Run a deterministic, no-model validation of the recovery protocol.

This is a protocol exercise, not a new model experiment. It uses the same
signed claim channel and action gate as the real runner, with scripted model
decisions only to exercise the recovery handoff and receiver redecision.
"""
import argparse
import hashlib
import json
import platform
from pathlib import Path

from trust_network.demo.claim_channel import ClaimGateway, issue
from trust_network.demo.documents import digest, keypair
from trust_network.demo.network_reliability import authority_status, run_batch
from trust_network.demo.reliability_accountability import append_event, audit_accountability
from trust_network.demo.reliability_recovery import (build_recovery_evidence,
    rebuild_derived_claim, replacement_offer, prepare_recovery)


WORKFLOW='offline-reliability-recovery'
OWNERS=('buyer','supplier','carrier','coordinator','receiver')
AUTHORITIES={'invoice_authorization':'buyer','charge_manifest':'buyer',
             'charge/goods':'supplier','charge/freight':'carrier',
             'delivery_schedule':'carrier','total_charge':'coordinator'}


def _write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def _exchange(events,owner,sender,operation,request,response):
    append_event(events,{'kind':'worker_exchange','owner':owner,'sender':sender,
                         'operation':operation,'request':request,'response':response})
    if operation=='receive':
        packet=request['packet']; event=response.get('event',{})
        append_event(events,{'kind':'claim_delivery','sender':sender or packet['signature']['issuer'],
                             'receiver':owner,'packet_digest':digest(packet),
                             'packet_kind':packet['body'].get('kind'),
                             'action':event.get('body',{}).get('action'),
                             'path_length':1 if sender in (None,packet['signature']['issuer']) else 2})


def _source(nodes,keys,owner,predicate,value):
    packet=issue(owner,keys[owner][0],{'kind':'claim','workflow':WORKFLOW,
        'parents':[],'fact':{'predicate':predicate,'value':value}})
    nodes[owner].receive(packet)
    return packet


def _run_batch(receiver,nodes,events,stage,proposals,effects):
    before=len(receiver.events)
    packet=run_batch(receiver,proposals,
        lambda owner,query:authority_status(nodes[owner],query),
        lambda proposal:effects.append({'stage':stage,'proposal':proposal['id']}))
    _exchange(events,'receiver','runtime','reliability_batch',
              {'operation':'reliability_batch','stage':stage,'proposals':proposals},
              {'batch':packet,'events':receiver.events[before:]})
    body=packet['body']
    return {'stage':stage,'proposals':proposals,'outputs':body['outputs'],
            'verification_calls':body['verification_calls'],'packet':packet}


def run(output):
    output=Path(output).resolve()
    output.mkdir(parents=True,mode=0o700,exist_ok=False)
    keys={owner:keypair() for owner in OWNERS}
    public={owner:pair[1] for owner,pair in keys.items()}
    nodes={owner:ClaimGateway(owner,keys[owner][0],public,WORKFLOW,AUTHORITIES)
           for owner in OWNERS}
    events=[]
    append_event(events,{'kind':'start','workflow':WORKFLOW,'mode':'offline_protocol_validation',
                         'model_calls':0})

    packets={
        'manifest':_source(nodes,keys,'buyer','charge_manifest',
            {'order':'A','currency':'CNY','components':['goods','freight']}),
        'authorization':_source(nodes,keys,'buyer','invoice_authorization',
            {'order':'A','operation':'approve_invoice','currency':'CNY',
             'maximum_cents':11000,'approved':True}),
        'goods':_source(nodes,keys,'supplier','charge/goods',
            {'order':'A','currency':'CNY','component':'goods','cents':10000}),
        'freight':_source(nodes,keys,'carrier','charge/freight',
            {'order':'A','currency':'CNY','component':'freight','cents':700}),
        'schedule':_source(nodes,keys,'carrier','delivery_schedule',
            {'order':'A','currency':'CNY','window':'2026-10-01/2026-10-03',
             'reference_only':True}),
    }
    ids={name:digest(packet) for name,packet in packets.items()}
    for name,packet in packets.items():
        response={'event':nodes['coordinator'].receive(packet)}
        _exchange(events,'coordinator',packet['signature']['issuer'],'receive',
                  {'operation':'receive','packet':packet},response)
        response={'event':nodes['receiver'].receive(packet)}
        _exchange(events,'receiver','coordinator','receive',
                  {'operation':'receive','packet':packet},response)

    old_total=issue('coordinator',keys['coordinator'][0],{
        'kind':'claim','workflow':WORKFLOW,
        'parents':[ids['manifest'],ids['goods'],ids['freight']],
        'fact':{'predicate':'total_charge','value':{'order':'A','currency':'CNY','cents':10700}},
        'rule':'sum_charges'})
    old_total_id=digest(old_total)
    response={'event':nodes['coordinator'].receive(old_total),'packet':old_total}
    _exchange(events,'coordinator','coordinator-model','reliability_sign_derived',
              {'operation':'reliability_sign_derived','parents':old_total['body']['parents']},response)
    response={'event':nodes['receiver'].receive(old_total)}
    _exchange(events,'receiver','coordinator','receive',
              {'operation':'receive','packet':old_total},response)
    append_event(events,{'kind':'offline_model_decision','stage':'initial_coordinator',
                         'owner':'coordinator','action':'proceed','claim_id':old_total_id})
    append_event(events,{'kind':'offline_model_decision','stage':'initial_receiver',
                         'owner':'receiver','actions':[{'id':'invoice-A','action':'approve',
                         'claims':[ids['authorization'],old_total_id]},
                         {'id':'schedule-reference','action':'forward','claims':[ids['schedule']]}]})

    revoke=issue('carrier',keys['carrier'][0],{'kind':'revoke','workflow':WORKFLOW,
        'target':ids['freight'],'original':packets['freight']})
    nodes['carrier'].receive(revoke)
    append_event(events,{'kind':'controlled_event','type':'carrier_freight_revocation',
                         'packet_digest':digest(revoke),'target':ids['freight'],
                         'delivered_to':[]})
    initial_proposals=[
        {'id':'invoice-A','operation':'approve_invoice','order':'A',
         'claims':[ids['authorization'],old_total_id]},
        {'id':'schedule-reference','operation':'forward','claims':[ids['schedule']]},
    ]
    effects=[]
    initial=_run_batch(nodes['receiver'],nodes,events,'initial',initial_proposals,effects)

    new_fact={'predicate':'charge/freight','value':{'order':'A','currency':'CNY',
        'component':'freight','cents':900}}
    new_source=issue('carrier',keys['carrier'][0],{'kind':'claim','workflow':WORKFLOW,
        'parents':[],'fact':new_fact})
    new_root=digest(new_source)
    source_response={'packet':new_source,'event':nodes['carrier'].receive(new_source)}
    _exchange(events,'carrier','controlled-recovery','reliability_replacement_source',
              {'operation':'reliability_replacement_source','old':ids['freight'],
               'new_fact':new_fact},source_response)
    offer=replacement_offer(nodes['carrier'],ids['freight'],new_source)
    _exchange(events,'carrier','controlled-recovery','reliability_replacement_offer',
              {'operation':'reliability_replacement_offer','old':ids['freight'],'new':new_source},
              {'offer':offer})
    before=len(nodes['receiver'].events)
    envelope=prepare_recovery(nodes['receiver'],initial['packet'],[offer])
    _exchange(events,'receiver','controlled-recovery','reliability_recovery',
              {'operation':'reliability_recovery','batch':initial['packet'],'offers':[offer]},
              {'recovery':envelope,'events':nodes['receiver'].events[before:]})
    task=envelope['body']['tasks'][0]
    coordinator_response={'event':nodes['coordinator'].receive(new_source)}
    _exchange(events,'coordinator','carrier','receive',
              {'operation':'receive','packet':new_source},coordinator_response)
    evidence=build_recovery_evidence(nodes['coordinator'],envelope,task,offer,
                                     coordinator_response['event'],new_source)
    _exchange(events,'coordinator','coordinator-scheduler',
              'reliability_build_recovery_evidence',
              {'operation':'reliability_build_recovery_evidence','envelope':envelope,
               'task':task,'replacement_offer':offer,
               'coordinator_registration':coordinator_response['event'],
               'replacement_source':new_source}, {'evidence':evidence})
    append_event(events,{'kind':'offline_model_decision','stage':'recovery_coordinator',
                         'owner':'coordinator','action':'proceed',
                         'replacement_root':new_root,'old_derived':old_total_id,
                         'new_fact':{'predicate':'total_charge','value':{
                             'order':'A','currency':'CNY','cents':10900}}})
    rebuilt=rebuild_derived_claim(nodes['coordinator'],envelope,task,
        {'predicate':'total_charge','value':{'order':'A','currency':'CNY','cents':10900}},
        'sum_charges',evidence)
    new_total_id=digest(rebuilt)
    _exchange(events,'coordinator','coordinator-model','reliability_rebuild_derived',
              {'operation':'reliability_rebuild_derived','envelope':envelope,
               'task':task,'fact':rebuilt['body']['fact'],'rule':'sum_charges',
               'evidence':evidence},
              {'packet':rebuilt,'event':nodes['coordinator'].events[-2],
               'events':[nodes['coordinator'].events[-2],nodes['coordinator'].events[-1]]})
    receiver_response={'event':nodes['receiver'].receive(rebuilt)}
    _exchange(events,'receiver','coordinator','receive',
              {'operation':'receive','packet':rebuilt},receiver_response)
    append_event(events,{'kind':'offline_model_decision','stage':'recovery_receiver',
                         'owner':'receiver','action':'approve',
                         'claims':[ids['authorization'],new_total_id]})
    recovery_proposals=[{'id':'invoice-A','operation':'approve_invoice','order':'A',
                         'claims':[ids['authorization'],new_total_id]}]
    recovery=_run_batch(nodes['receiver'],nodes,events,'recovery',recovery_proposals,effects)

    run_record={'kind':'offline_reliability_recovery_run','workflow':WORKFLOW,
                'condition':'hidden_revoke','policy':'dependency','model_decisions':[
                    {'stage':'initial_coordinator','owner':'coordinator','status':'scripted',
                     'draft':{'action':'proceed','claim_id':old_total_id}},
                    {'stage':'initial_receiver','owner':'receiver','status':'scripted',
                     'draft':{'actions':initial_proposals}},
                    {'stage':'recovery_coordinator','owner':'coordinator','status':'scripted',
                     'draft':{'action':'proceed','claim_id':new_total_id}},
                    {'stage':'recovery_receiver','owner':'receiver','status':'scripted',
                     'draft':{'action':'approve','claims':[ids['authorization'],new_total_id]}},
                ],
                'batches':[{k:v for k,v in initial.items() if k!='packet'},
                           {k:v for k,v in recovery.items() if k!='packet'}],
                'effects':effects,'initial_total':old_total_id,'old_root':ids['freight'],
                'replacement_root':new_root,
                'recovery':{'attempted':True,'blocked_initial':True,'succeeded':True,
                            'old_root':ids['freight'],'new_root':new_root,
                            'new_total':new_total_id,'envelope':envelope},
                'runtime_truth_accessed':False}
    append_event(events,{'kind':'run_completed','recovered_total':new_total_id,
                         'effects':effects})
    run_record['event_chain_root']=events[-1]['event_hash']
    manifest={'kind':'offline_reliability_recovery_validation','status':'completed',
              'python':platform.python_version(),'workflow':WORKFLOW,
              'model_calls':0,'conditions':['hidden_revoke'],'policies':['dependency'],
              'signed_public_keys':public,'public_keys':public,
              'runtime_truth_accessed':False,
              'source_command':'.venv/bin/python -m trust_network.demo.run_reliability_recovery_offline '
                               f'--out {output}',
              'validation_scope':'protocol and event-chain validation; scripted model decisions only'}
    control={'type':'carrier_freight_revocation','old_root':ids['freight'],
             'new_fact':new_fact}
    accountability=audit_accountability(run_record,events,manifest,control)
    metrics={'model_calls':0,'initial_invoice_action':initial['outputs'][0]['action'],
             'initial_schedule_action':next(o['action'] for o in initial['outputs']
                                            if o['proposal']=='schedule-reference'),
             'recovery_invoice_action':recovery['outputs'][0]['action'],
             'initial_invoice_blocked':initial['outputs'][0]['action']=='REQUEST_EVIDENCE',
             'recovery_completed':recovery['outputs'][0]['action']=='COMPLETED',
             'unaffected_schedule_completed':any(o['proposal']=='schedule-reference' and
                                                  o['action']=='COMPLETED'
                                                  for o in initial['outputs']),
             'old_revocation_preserved':ids['freight'] in nodes['receiver'].revoked,
             'old_total_still_blocked':bool(nodes['receiver'].blockers(old_total_id)),
             'new_total_unblocked':not nodes['receiver'].blockers(new_total_id),
             'event_chain_valid':accountability['event_chain']['valid'],
             'responsibility_status':accountability['responsibility']['status']}
    report='# 离线恢复闭环验证\n\n'
    report+=('本目录不产生真实模型调用；使用固定脚本决策验证签名证据、撤销、派生重建、'
             'receiver 重决策和动作门禁。\n\n')
    report+=f"- 初始账单结果：{metrics['initial_invoice_action']}；旧 freight 未执行。\n"
    report+=f"- 无关交付时间任务：{metrics['initial_schedule_action']}，继续完成。\n"
    report+=f"- 恢复账单结果：{metrics['recovery_invoice_action']}，新 total {new_total_id}。\n"
    report+=f"- 旧撤销保留：{metrics['old_revocation_preserved']}；旧 total 仍阻断：{metrics['old_total_still_blocked']}。\n"
    report+=f"- 事件账本校验：{metrics['event_chain_valid']}；责任结论：{metrics['responsibility_status']}。\n\n"
    report+=('该结果证明协议闭环在离线固定决策下可执行，不增加真实模型效果样本，'
             '也不证明跨物理主机部署、物理副作用或责任归因。\n')
    _write(output/'manifest.json',manifest)
    _write(output/'control_event.json',control)
    _write(output/'run_record.json',run_record)
    _write(output/'events.json',events)
    _write(output/'accountability.json',accountability)
    _write(output/'metrics.json',metrics)
    (output/'report.md').write_text(report)
    tracked=['manifest.json','control_event.json','run_record.json','events.json',
             'accountability.json','metrics.json','report.md']
    integrity={'kind':'offline_artifact_integrity_manifest','files':[
        {'path':name,'sha256':hashlib.sha256((output/name).read_bytes()).hexdigest()}
        for name in tracked]}
    _write(output/'raw_integrity_manifest.json',integrity)
    return metrics


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.out),ensure_ascii=False,indent=2))
