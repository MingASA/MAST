"""Model-independent serial runner. No provider is invoked by this module.

Manifest points to separately owned demo directories. The controller routes
queries to authority workers; the receiver only receives signed responses.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def run(manifest_path, proposals_path, output):
    manifest=json.loads(manifest_path.read_text())
    proposals=json.loads(proposals_path.read_text())
    output.mkdir(parents=True,exist_ok=False)
    request={'operation':'reliability_batch','proposals':proposals}
    def command(directory):
        return [sys.executable,'-m','trust_network.demo.claim_worker',
                '--directory',directory,'--env-file','/unused/no-provider-in-this-run']
    # Communication timeout is managed by the process controller. This is a
    # local serial adapter, not an authenticated remote deployment transport.
    process=subprocess.Popen(command(manifest['receiver']),stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    exchanges=[]
    try:
        process.stdin.write(json.dumps(request)+'\n'); process.stdin.flush()
        import selectors
        selector=selectors.DefaultSelector(); selector.register(process.stdout,selectors.EVENT_READ)
        while True:
            if not selector.select(timeout=120):
                raise TimeoutError('receiver response timeout')
            line=process.stdout.readline()
            if not line:
                raise RuntimeError('receiver exited without a result')
            message=json.loads(line)
            if 'authority_query' not in message:
                response=message; break
            owner=message['authority']; query=message['authority_query']
            authority_request={'operation':'reliability_status','query':query}
            try:
                completed=subprocess.run(command(manifest['authorities'][owner]),
                    input=json.dumps(authority_request)+'\n',capture_output=True,text=True,timeout=60,check=True)
                reply=json.loads(completed.stdout)['reply']
            except (subprocess.SubprocessError,KeyError,ValueError):
                reply={}  # Invalid reply => unavailable => protected action cannot pass.
            exchanges.append({'authority':owner,'request':authority_request,'reply':reply})
            process.stdin.write(json.dumps({'reply':reply})+'\n'); process.stdin.flush()
        process.wait(timeout=10)
        if process.returncode:
            raise RuntimeError('receiver failed')
        (output/'result.json').write_text(json.dumps(response,ensure_ascii=False,indent=2))
        config=json.loads((Path(manifest['receiver'])/'config.json').read_text())
        from trust_network.demo.reliability_audit import audit_with_authorities
        audit=audit_with_authorities(response['batch'],config['public_keys'],config['authorities'])
        (output/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
        (output/'input.json').write_text(json.dumps(request,ensure_ascii=False,indent=2))
        (output/'exchanges.json').write_text(json.dumps(exchanges,ensure_ascii=False,indent=2))
    return response


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--proposals',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    run(args.manifest,args.proposals,args.out)
