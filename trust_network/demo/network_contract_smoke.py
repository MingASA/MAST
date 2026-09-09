"""Local HTTP integration of four independently keyed services; no model calls."""
from pathlib import Path
import argparse
import json
import select
import subprocess
import sys
import tempfile
from trust_network.demo.preflight_contract import provision
from trust_network.demo.approval_scenario import ACTORS
from trust_network.demo.authority import RemoteAuthorityClient
from trust_network.demo.contract_workflow import RemoteGateway, run
from trust_network.demo.contract_audit import validate


def execute(out):
    out.mkdir(parents=True,exist_ok=False)
    processes=[]
    def launch(command):
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        processes.append(process)
        ready,_,_=select.select([process.stdout],[],[],10)
        if not ready: raise RuntimeError('service did not announce readiness')
        line=process.stdout.readline()
        if not line: raise RuntimeError('service failed to listen; environment may deny local sockets')
        return f"http://127.0.0.1:{json.loads(line)['listening_port']}/"
    try:
        with tempfile.TemporaryDirectory(prefix='contract-network-') as temporary:
            root=Path(temporary)
            public,runtime_key=provision(root,'evidence_contract',True,'quantity')
            endpoints={org:launch([sys.executable,'-m','trust_network.demo.contract_worker',
                '--organization-dir',str(root/org),'--fixture','--port','0']) for org in ACTORS}
            authority_endpoint=launch([sys.executable,'-m','trust_network.demo.authority',
                '--registry',str(root/'buyer_authority/registry.json'),
                '--key-file',str(root/'buyer_authority/signing.key'),'--port','0'])
            bundle=json.loads(Path('examples/authorization_v4/case_01/public/bundle.json').read_text())
            result=run(bundle,'evidence_contract',{o:RemoteGateway(url) for o,url in endpoints.items()},
                       public,RemoteAuthorityClient(authority_endpoint),runtime_key,out/'run')
            if not result['committed'] or result['repairs']!=1:
                raise ValueError('network flow did not repair and complete')
            validation=validate(out/'run',public)
            manifest={'label':'SCRIPTED localhost HTTP integration, no MiniMax calls',
                'public_keys':public,'services':list(endpoints)+['buyer_authority'],
                'organization_private_keys_sent_to_runtime':False,
                'separate_physical_devices':False,'validation':validation}
            (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
            return manifest
    finally:
        for process in processes:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    print(json.dumps(execute(parser.parse_args().out),indent=2))
