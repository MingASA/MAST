"""Offline first, explicit bounded live mode; output directories are immutable."""
import argparse
import hashlib
import json
from pathlib import Path
from .spec import matrix, MAIN, LIVE_CASES
from .engine import Run
from .report import report
from .storage import write_json
from .preflight import source_hashes, verify_offline, verify_validation


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=('offline','live','tape'),default='offline')
    p.add_argument('--backend',choices=('memory','process'),default='memory')
    p.add_argument('--allow-paid',action='store_true')
    p.add_argument('--env-file',type=Path)
    p.add_argument('--tape',type=Path)
    p.add_argument('--validation',type=Path,help='Code-bound full regression and process parity result')
    p.add_argument('--preflight',type=Path,help='Completed offline metrics required before live')
    args=p.parse_args()
    if args.mode=='live':
        if not args.allow_paid or not args.env_file or not args.preflight or not args.validation:
            p.error('live requires --allow-paid --env-file --preflight --validation')
        try:
            verify_offline(args.preflight.parent)
            verify_validation(args.validation)
        except (ValueError,OSError,KeyError) as exc:p.error(str(exc))
        args.backend='process'
    if args.mode=='tape' and not args.tape:p.error('tape mode needs normalized --tape')
    args.output.mkdir(parents=True,exist_ok=False)
    rows=[];hashes={};sources=source_hashes()
    def write(name,value):
        path=args.output/name;write_json(path,value)
        hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    write('provenance.json',{'source_hashes':sources,'mode':args.mode,
        'initialization':'scripted','effects':'simulated','query_latency_ticks':0})
    combos=list(matrix()) if args.mode=='offline' else [
        ('long_chain_fork',c,l) for c in (LIVE_CASES if args.mode=='live' else ('late_notice',)) for l in MAIN]
    tape=json.loads(args.tape.read_text())['tape'] if args.tape else None
    workers=args.output/'workers'
    workers.mkdir(mode=0o700)
    write('progress.json',{'status':'initialized','planned':len(combos),'completed':0,'mode':args.mode})
    for i,(topology,case,layer) in enumerate(combos):
        if source_hashes()!=sources:raise RuntimeError('source changed during run; do not continue')
        write('progress.json',{'status':'running','index':i,'completed':i,'planned':len(combos),
            'topology':topology,'case':case,'layer':layer,'mode':args.mode})
        try:
            raw=Run(topology,case,layer,args.backend,workers/str(i),
                    live=args.mode=='live',env_file=args.env_file,tape=tape).run()
        except BaseException as exc:
            write('progress.json',{'status':'interrupted','index':i,'completed':len(rows),
                'planned':len(combos),'mode':args.mode,'error_type':type(exc).__name__,
                'automatic_paid_retry':False,'journal':str(workers/str(i))})
            write('partial_manifest.json',dict(hashes))
            raise
        if source_hashes()!=sources:raise RuntimeError('source changed during run; archive worker journal before resuming')
        name=f'{i:03d}_{topology}_{case}_{layer}.json'
        write(name,raw)
        row={'file':name,'topology':topology,'case':case,'layer':layer,
             'workload_hash':raw['workload_hash'],'event_tape_hash':raw['event_tape_hash'],
             'proposal_tape_hash':raw['proposal_tape_hash'],'metrics':raw['metrics']}
        rows.append(row)
        write('metrics.json',rows)
        write('progress.json',{'status':'between_workflows','completed':len(rows),'planned':len(combos),'mode':args.mode})
        print(json.dumps({'completed':i+1,'planned':len(combos),'case':case,'layer':layer,
            'unsafe':raw['metrics']['unsafe_completion_count'],'safe_final':raw['metrics']['safe_final_completion'],
            'calls':raw['new_model_calls'],'tokens':raw['metrics']['known_tokens']}),flush=True)
    write('progress.json',{'status':'completed','completed':len(rows),'planned':len(combos),'mode':args.mode})
    write('manifest.json',dict(hashes))
    report(args.output,args.mode)

if __name__=='__main__':main()
