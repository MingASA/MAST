"""Inspect durable call journals after interruption; never restart paid calls."""
import argparse
import json
from pathlib import Path


def inspect(directory):
    directory=Path(directory);started={};finished={};malformed=[]
    for p in sorted((directory/'workers').rglob('*.provider.jsonl')):
        for i,line in enumerate(p.read_text().splitlines()):
            try:r=json.loads(line)
            except json.JSONDecodeError:
                malformed.append({'path':str(p),'line':i+1});continue
            key=(str(p),r['call_id'])
            if r['status']=='started':started[key]=r
            else:finished[key]=r
    attempts=[a for r in finished.values() for a in r['result'].get('attempts',[])]
    known=[a['usage']['total_tokens'] for a in attempts if isinstance(a.get('usage'),dict)
           and type(a['usage'].get('total_tokens')) is int]
    return {'progress':json.loads((directory/'progress.json').read_text()),
        'model_calls_started':len(started),'model_calls_returned_or_failed':len(finished),
        'unfinished_calls':[{'path':p,'call_id':cid} for p,cid in started.keys()-finished.keys()],
        'known_attempts':len(attempts),'known_tokens':sum(known),'unknown_usage_attempts':len(attempts)-len(known),
        'malformed_journal_lines':malformed,'automatic_retry':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    args=p.parse_args();print(json.dumps(inspect(args.directory),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
