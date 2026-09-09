"""Explicit controlled HTTP protocol exercise; zero model calls.

Separate local processes are transport evidence, not physical host isolation.
"""
from pathlib import Path
import argparse
import json
import secrets
import selectors
import subprocess
import sys
import tempfile
import time
import uuid
from trust_network.demo.documents import keypair, digest
from trust_network.demo.run_negotiation import provision
from trust_network.demo.negotiation_http import RemoteOrganization
from trust_network.demo.resource_protocol import ResourceCoordinator, execute_resource_plan, signed
from trust_network.demo.negotiation_worker import verify


def run(case, out, env_file=None):
    out.mkdir(parents=True, exist_ok=False)
    processes = []
    events = []
    with tempfile.TemporaryDirectory(prefix='resource-network-') as temporary:
        root = Path(temporary)
        public, _ = provision(case, root)
        key, public['coordinator'] = keypair()
        clients = {}
        try:
            for owner in ('supplier', 'carrier', 'buyer'):
                directory = root/owner
                (directory/'config.json').write_text(json.dumps({'organization': owner, 'public_keys': public}))
                token = secrets.token_urlsafe(32)
                token_file = directory/'service.token'
                token_file.write_text(token); token_file.chmod(0o600)
                process = subprocess.Popen([sys.executable, '-m', 'trust_network.demo.negotiation_http',
                    '--organization-dir', str(directory), '--env-file', str(env_file or root/'unused.env'),
                    '--token-file', str(token_file), '--port', '0'], stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True)
                processes.append(process)
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    if not selector.select(10): raise RuntimeError('service startup timed out')
                ready = json.loads(process.stdout.readline())
                clients[owner] = RemoteOrganization('http://127.0.0.1:'+str(ready['listening_port']), token)
            def call(owner, operation, **kwargs):
                request = {'workflow_id': 'network-smoke', 'request_id': uuid.uuid4().hex,
                           'operation': operation, **kwargs}
                request = json.loads(json.dumps(request))
                response = clients[owner].call(request)
                events.append({'owner': owner, 'request': request, 'response': response})
                (out/'events.json').write_text(json.dumps(events, ensure_ascii=False, indent=2))
                if 'message' in response:
                    body = verify(response['message'], owner, public[owner], 'network-smoke')
                    if body['input_hash'] != digest(request): raise ValueError('response input mismatch')
                return response
            if env_file is not None:
                public_request = json.loads((case/'public.json').read_text())
                messages = []
                for owner in ('supplier', 'carrier'):
                    response = call(owner, 'offer', public_request=public_request, messages=messages)
                    if 'message' not in response: raise ValueError('invalid model offer; retained in events')
                    messages.append(response['message'])
                feedback = []
                result = {'status': 'negotiation_limit'}
                coordinator = ResourceCoordinator(out/'coordinator.sqlite', key, public)
                for attempt in range(3):
                    response = call('buyer', 'plan', public_request=public_request, messages=messages, feedback=feedback)
                    if 'message' not in response:
                        feedback = response['feedback']; continue
                    content = response['message']['body']['content']
                    if content['action'] == 'reject':
                        result = {'status': 'buyer_rejected'}; break
                    if content['action'] == 'verify':
                        feedback = []
                        for owner in ('supplier', 'carrier', 'buyer'):
                            receipt = call(owner, 'attest', plan=content['plan'], buyer_decision=response['message'])['commitment']
                            feedback.append(receipt)
                        continue
                    result = execute_resource_plan(coordinator, call, content['plan'], response['message'],
                                                   'network-smoke', time.time)
                    break
                report = {'status': result['status'], 'result': result, 'experiment': 'real_model_resource_pilot',
                          'transport': 'authenticated localhost HTTP processes', 'http_calls': len(events),
                          'model_api_calls': sum(e['response'].get('usage', {}).get('attempts', 0) for e in events),
                          'tokens': sum(e['response'].get('usage', {}).get('total_tokens', 0) for e in events),
                          'events_hash': digest(events), 'public_keys': public}
                (out/'report.json').write_text(json.dumps(signed('coordinator', report, key), ensure_ascii=False, indent=2))
                return {k: report[k] for k in ('status', 'http_calls', 'model_api_calls', 'tokens')}
            plan = {'transaction': 'NETWORK-RESOURCE-1', 'model': 'MX-40B', 'quantity': 10,
                    'shipments': [
                        {'lot': 'early', 'quantity': 4, 'dispatch_day': 1, 'service': 'air', 'arrival_day': 2, 'cost': 1500},
                        {'lot': 'later', 'quantity': 6, 'dispatch_day': 3, 'service': 'road', 'arrival_day': 5, 'cost': 600}]}
            votes = {o: call(o, 'resource_prepare', plan=plan)['resource'] for o in ('supplier', 'carrier')}
            # The smoke checks resource abort/recovery only; it does not fabricate
            # a buyer model decision or authorization for committing an order.
            coordinator = ResourceCoordinator(out/'coordinator.sqlite', key, public)
            decision = coordinator.decide(plan, votes, None, 'network-smoke', time.time(), action='abort')
            ack = call('supplier', 'resource_decide', plan=plan, decision=decision)['resource']
            coordinator.acknowledge(plan['transaction'], 'supplier', ack)
            assert coordinator.status(plan['transaction']) == 'recovery_pending'
            coordinator = ResourceCoordinator(out/'coordinator.sqlite', key, public)
            recovered = coordinator.recover(plan['transaction'])
            for owner in ('supplier', 'carrier'):
                ack = call(owner, 'resource_decide', plan=plan, decision=recovered)['resource']
                coordinator.acknowledge(plan['transaction'], owner, ack)
            assert coordinator.status(plan['transaction']) == 'aborted'
            other = dict(plan, transaction='NETWORK-RESOURCE-2')
            for owner in ('supplier', 'carrier'):
                assert call(owner, 'resource_prepare', plan=other)['resource']['body']['kind'] == 'prepared'
            # Cleanly release the final probe too.
            votes2 = {e['owner']: e['response']['resource'] for e in events[-2:]}
            decision2 = coordinator.decide(other, votes2, None, 'network-smoke', time.time(), action='abort')
            for owner in ('supplier', 'carrier'):
                ack = call(owner, 'resource_decide', plan=other, decision=decision2)['resource']
                coordinator.acknowledge(other['transaction'], owner, ack)
            report = {'status': 'passed', 'transport': 'authenticated HTTP, separate localhost processes',
                      'scope': 'prepare, partial abort, journal recovery, repeated abort, capacity reuse',
                      'model_api_calls': 0, 'http_calls': len(events), 'events': events, 'public_keys': public}
            (out/'report.json').write_text(json.dumps(report, indent=2))
            return {k: v for k, v in report.items() if k not in ('events', 'public_keys')}
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', type=Path, default=Path('examples/negotiation_v6/urgent'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--env-file', type=Path, help='Explicitly enable real model pilot instead of controlled smoke')
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.out, args.env_file)))
