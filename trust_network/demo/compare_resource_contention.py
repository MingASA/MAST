"""Controlled same-plan replay, not additional natural model samples."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
from trust_network.demo.documents import keypair, digest
from trust_network.demo.negotiation import OWNERS, attest, CommitmentBook, ExecutionSink
from trust_network.demo.negotiation_worker import sign
from trust_network.demo.reservations import ReservationStore
from trust_network.demo.resource_protocol import ResourceParticipant, ResourceCoordinator, execute_resource_plan, verified


def run(source, case, out):
    out.mkdir(parents=True, exist_ok=False)
    envelope = json.loads((source/'report.json').read_text())
    report = verified(envelope, 'coordinator', envelope['body']['public_keys']['coordinator'])
    events = json.loads((source/'events.json').read_text())
    if digest(events) != report['events_hash']: raise ValueError('source events changed')
    original = report['result']['decision']['body']['buyer_decision']['body']['content']['plan']
    records = []
    for capacity_factor in (1, 2):
        private = {o: json.loads((case/o/'state.json').read_text()) for o in OWNERS}
        for lot in private['supplier']['lots'].values(): lot['quantity'] *= capacity_factor
        for service in private['carrier']['services'].values(): service['capacity'] *= capacity_factor
        for protocol in ('snapshot_verify_all', 'resource_reservation'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                keys = {o: keypair() for o in (*OWNERS, 'coordinator')}
                public = {o: pair[1] for o, pair in keys.items()}
                participants = {o: ResourceParticipant(ReservationStore(root/(o+'.sqlite'), o, private[o]),
                    keys[o][0], public['coordinator']) for o in ('supplier', 'carrier')}
                coordinator = ResourceCoordinator(root/'decisions.sqlite', keys['coordinator'][0], public)
                consumed = {'supplier': {}, 'carrier': {}}
                for index in range(2):
                    plan = copy.deepcopy(original); plan['transaction'] = 'CONTROLLED-'+str(index)
                    workflow = 'controlled-'+str(index)
                    # New signatures are explicitly fixture authorization. We do
                    # not rewrite or impersonate the original model signature.
                    intent = sign('buyer', keys['buyer'][0], {'organization': 'buyer', 'workflow_id': workflow,
                        'content': {'action': 'propose', 'plan': plan}})
                    calls = []
                    def call(owner, operation, **kwargs):
                        calls.append({'owner': owner, 'operation': operation})
                        if operation == 'attest':
                            return {'commitment': attest(owner, private[owner], kwargs['plan'], workflow,
                                                         1, keys[owner][0], 100)}
                        if operation == 'resource_prepare':
                            return {'resource': participants[owner].prepare(kwargs['plan'], 100)}
                        return {'resource': participants[owner].decide(kwargs['plan'], kwargs['decision'], 101)}
                    if protocol == 'snapshot_verify_all':
                        book = CommitmentBook(public, workflow)
                        for owner in OWNERS:
                            book.add(owner, plan, call(owner, 'attest', plan=plan)['commitment'], 100)
                        ExecutionSink(root/'executions.sqlite', public).commit(plan, book, 100)
                        status = 'completed'
                    else:
                        status = execute_resource_plan(coordinator, call, plan, intent, workflow, lambda: 100)['status']
                    violations = []
                    if status == 'completed':
                        for owner, field, table, capacity in (
                            ('supplier', 'lot', 'lots', 'quantity'), ('carrier', 'service', 'services', 'capacity')):
                            for row in plan['shipments']:
                                resource = row[field]
                                consumed[owner][resource] = consumed[owner].get(resource, 0) + row['quantity']
                            if any(amount > private[owner][table][resource][capacity]
                                   for resource, amount in consumed[owner].items()):
                                violations.append(owner+'_overallocated')
                    records.append({'capacity_factor': capacity_factor, 'protocol': protocol, 'order': index,
                        'status': status, 'unsafe_completion': bool(violations), 'violations': violations,
                        'organization_calls': len(calls), 'calls': calls, 'plan': plan})
    result = {'kind': 'controlled_same_plan_replay', 'model_calls': 0, 'source_report_hash': digest(envelope),
              'limitations': ['sequential competing orders, not concurrent model runs',
                              'fixture buyer signatures; original model plan reused with new transaction IDs',
                              'static comparison has no cross-order capacity ledger by design',
                              'in-process services, no latency or network-failure estimate'], 'records': records}
    (out/'report.json').write_text(json.dumps(result, indent=2))
    for factor in (1, 2):
        for protocol in ('snapshot_verify_all', 'resource_reservation'):
            rows = [r for r in records if r['capacity_factor'] == factor and r['protocol'] == protocol]
            print(json.dumps({'capacity_factor': factor, 'protocol': protocol,
                'unsafe': sum(r['unsafe_completion'] for r in rows),
                'safe_completed': sum(r['status'] == 'completed' and not r['unsafe_completion'] for r in rows),
                'calls': sum(r['organization_calls'] for r in rows)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path('results/resource_v7_minimax_pilot_retry'))
    parser.add_argument('--case', type=Path, default=Path('examples/negotiation_v6/urgent'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); run(args.source, args.case, args.out)
