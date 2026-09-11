"""Resumable immutable plan, per-workflow ownership and conservative paid-call recovery."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
from dataclasses import replace
from .storage import write_json
from .final_plan import make_plan, verify_plan
from .final_score import task_rows, exposure
from .preflight import source_hashes
from .engine import Run, SYSTEM, RECOVERY_REQUEST_SYSTEM, SOURCE_REVISION_SYSTEM, RECOVERY_REBUILD_SYSTEM
from trust_network.demo.provider import ProviderConfig
from trust_network.demo.documents import digest


def provider_identity(path):
    c=replace(ProviderConfig.load(Path(path)),max_tokens=2048,temperature=.2)
    return {'model':c.model,'base_url':c.base_url,'max_tokens':c.max_tokens,'temperature':c.temperature}


def initialize(output,env_file):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    plan=make_plan();verify_plan(plan)
    write_json(output/'plan.json',plan)
    write_json(output/'provenance.json',{'source_hashes':source_hashes(),
        'plan_hash':plan['canonical_hash'],'provider':provider_identity(env_file),
        'prompt_hash':digest([SYSTEM,RECOVERY_REQUEST_SYSTEM,SOURCE_REVISION_SYSTEM,RECOVERY_REBUILD_SYSTEM]),
        'execution':'scripted initial graph, live downstream decisions, process workers, simulated effects',
        'resume':'completed never replayed; started without result remains unknown; untouched may start'})
    (output/'runs').mkdir();(output/'shards').mkdir()
    write_json(output/'progress.json',{'status':'planned','planned':350,'completed':0})


def load_bound(output,env_file=None):
    output=Path(output);plan=json.loads((output/'plan.json').read_text());fixtures=verify_plan(plan)
    provenance=json.loads((output/'provenance.json').read_text())
    if source_hashes()!=provenance['source_hashes']:raise ValueError('source changed: create a new batch version')
    if provenance['plan_hash']!=plan['canonical_hash']:raise ValueError('plan changed')
    if env_file and provider_identity(env_file)!=provenance['provider']:raise ValueError('provider configuration changed')
    return plan,fixtures


def private_manifest(directory):
    records=[]
    for p in sorted((directory/'workers').rglob('*')):
        if p.is_file():records.append({'path':str(p.relative_to(directory)),
            'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
    write_json(directory/'private_manifest.json',{'excluded_from_git':True,
        'reason':'organization private ledger, signing keys and local provider journals',
        'count':len(records),'files':records})


def inspect_journals(directory):
    starts=set();ends=set();attempts={};malformed=0
    for path in (directory/'workers').glob('*.provider.jsonl'):
        for line in path.read_text().splitlines():
            try:e=json.loads(line)
            except json.JSONDecodeError:malformed+=1;continue
            cid=e['call_id'];status=e['status']
            if status=='started':starts.add(cid)
            elif status in ('returned','failed'):ends.add(cid)
            elif status.startswith('attempt_'):attempts[(cid,e['attempt'])]=e
    known=0;unknown=0
    for e in attempts.values():
        value=(e.get('usage') or {}).get('total_tokens')
        if type(value) is int:known+=value
        else:unknown+=1
    return {'calls_started':len(starts),'calls_finished':len(ends),'unfinished_calls':sorted(starts-ends),
            'provider_attempts':len(attempts),'known_tokens':known,'unknown_usage_attempts':unknown,'malformed_lines':malformed}


def execute(output,entry,fixture,env_file=None,live=True):
    directory=Path(output)/'runs'/entry['workflow_id'];directory.mkdir(exist_ok=True)
    with (directory/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=directory/'result.json';state=directory/'state.json'
        if result.exists():
            value=json.loads(result.read_text())
            if value['entry']!=entry:raise ValueError('completed result belongs to another entry')
            if (value['raw']['mode']=='live')!=live:raise ValueError('cannot mix scripted and live results')
            return 'completed'
        if state.exists():
            # A durable start marker is conservative: may have sent a billable request.
            old=json.loads(state.read_text())
            if old['status'] not in ('unknown','failed'):
                write_json(state,{'status':'unknown','reason':'interrupted workflow; no automatic paid replay',
                    'entry':entry,'journal':inspect_journals(directory)})
            private_manifest(directory)
            return 'unknown'
        write_json(state,{'status':'started','entry':entry,'pid':os.getpid()})
        try:
            raw=Run(fixture['topology'],fixture['case'],entry['layer'],
                'process' if live else 'memory',directory/'workers',live=live,env_file=env_file,fixture=fixture).run()
            if sorted(raw['truth']['affected_tasks'])!=sorted(fixture['evaluation']['affected_tasks']):
                raise ValueError('fixed denominator disagrees with injector')
            if raw['truth']['expected_cents']!=fixture['evaluation']['private_expected_cents']:
                raise ValueError('fixture private truth does not match execution')
            if not raw['truth']['fault_realized']:raise ValueError('planned fault not realized')
            write_json(result,{'entry':entry,'raw':raw,'task_metrics':task_rows(fixture,raw),'exposure':exposure(raw)})
            private_manifest(directory)
            write_json(state,{'status':'completed','entry':entry,
                'result_sha256':hashlib.sha256(result.read_bytes()).hexdigest()})
            return 'completed'
        except BaseException as exc:
            write_json(state,{'status':'unknown','entry':entry,'error_type':type(exc).__name__,
                'message':str(exc),'journal':inspect_journals(directory)})
            private_manifest(directory)
            raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('init','run','summary'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--env-file',type=Path)
    p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=1)
    p.add_argument('--allow-paid',action='store_true');p.add_argument('--offline',action='store_true')
    p.add_argument('--only',help='Comma-separated workflow IDs, e.g. calibration outside the formal directory')
    args=p.parse_args()
    if args.command=='init':initialize(args.output,args.env_file);return
    if args.command=='summary':
        from .final_summary import summarize
        summarize(args.output);return
    if not args.offline and (not args.allow_paid or not args.env_file):p.error('live requires --allow-paid --env-file')
    if not 0<=args.shard<args.shards:p.error('invalid shard')
    plan,fixtures=load_bound(args.output,args.env_file if not args.offline else None)
    if args.offline:p.error('final batch is live-only; use Run directly for offline calibration')
    calibration_path=args.output/'calibration.json'
    if not calibration_path.exists():p.error('calibration.json required')
    calibration=json.loads(calibration_path.read_text())
    if not calibration.get('passed') or calibration.get('source_hashes')!=source_hashes():p.error('calibration not passed for current source')
    only=set(args.only.split(',')) if args.only else None
    entries=[e for e in plan['runs'] if e['index']%args.shards==args.shard and (only is None or e['workflow_id'] in only)]
    with (args.output/'shards'/f'{args.shard}.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for i,entry in enumerate(entries):
            load_bound(args.output,args.env_file if not args.offline else None)
            status=execute(args.output,entry,fixtures[entry['fixture_id']],args.env_file,not args.offline)
            write_json(args.output/'shards'/f'{args.shard}.json',{'status':'running','completed_in_shard':i+1,
                'planned_in_shard':len(entries),'last':entry,'last_status':status})
            print(json.dumps({'shard':args.shard,'index':i+1,'planned':len(entries),'workflow':entry['workflow_id'],'status':status}),flush=True)
        write_json(args.output/'shards'/f'{args.shard}.json',{'status':'completed','processed':len(entries)})

if __name__=='__main__':main()
