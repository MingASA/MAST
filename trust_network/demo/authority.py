"""Organization-owned evidence service and narrowly scoped signed attestations.

The service process alone reads its approval registry. Runtime policy receives
only a Certificate. Local processes provide context isolation, not OS isolation.
"""
from dataclasses import asdict
from pathlib import Path
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler,HTTPServer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
from trust_network.demo.documents import Certificate,Decision,canonical

ISSUER='buyer_authority'
SCOPE='formal_model_authorization'


def attest(registry,request,key,now=None):
    bundle=request['documents']; tx=bundle['transaction']
    entry=registry.get(tx)
    status='unknown'
    if entry and entry.get('model')==bundle['invoice']['model'] and type(entry.get('approved')) is bool:
        status='approved' if entry['approved'] else 'denied'
    now=time.time() if now is None else now
    claim={'scope':SCOPE,'transaction':tx,'model':bundle['invoice']['model'],
           'status':status,'request_id':request['request_id'],
           'issued_at':now,'expires_at':now+300}
    action={'approved':'pass','denied':'reject','unknown':'escalate'}[status]
    decision=Decision(action,(SCOPE,),(canonical(claim).decode(),),'Authority attestation')
    return Certificate.issue(ISSUER,request['version'],bundle,decision,key)


def inspect(cert,bundle,version,public_key,request_id,now):
    if cert.issuer!=ISSUER or not cert.verify(public_key,bundle,version):
        raise ValueError('invalid authority signature or document binding')
    if tuple(cert.checks)!=(SCOPE,) or len(cert.findings)!=1: raise ValueError('wrong evidence scope')
    claim=json.loads(cert.findings[0])
    if (claim['scope']!=SCOPE or claim['transaction']!=bundle['transaction'] or
        claim['model']!=bundle['invoice']['model'] or claim['request_id']!=request_id):
        raise ValueError('wrong authority claim binding')
    if not claim['issued_at']<=now<claim['expires_at'] or claim['expires_at']-claim['issued_at']>300:
        raise ValueError('expired or invalid evidence lifetime')
    if claim['status'] not in ('approved','denied','unknown'): raise ValueError('wrong status')
    if cert.action!={'approved':'pass','denied':'reject','unknown':'escalate'}[claim['status']]:
        raise ValueError('inconsistent evidence action')
    return claim['status']


class AuthorityClient:
    def __init__(self,registry: Path,private_key):
        # Provisioning belongs to this local adapter, not to the online policy.
        self.registry=registry
        self.private_key=private_key

    def request(self,request):
        wire=dict(request,signing_key=self.private_key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()).hex())
        result=subprocess.run([sys.executable,'-m','trust_network.demo.authority','--registry',str(self.registry)],
                              input=json.dumps(wire),text=True,capture_output=True,timeout=15)
        if result.returncode: raise RuntimeError('authority service unavailable')
        return Certificate(**json.loads(result.stdout))


class RemoteAuthorityClient:
    """Client receives only an endpoint; signing key stays at the authority."""
    def __init__(self,endpoint): self.endpoint=endpoint

    def request(self,request):
        req=urllib.request.Request(self.endpoint,data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=15) as response:
            return Certificate(**json.load(response))


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--port',type=int); parser.add_argument('--key-file',type=Path)
    parser.add_argument('--bind',default='127.0.0.1')
    args=parser.parse_args()
    if args.port is not None:
        if args.key_file is None: parser.error('--key-file required for authority server')
        key=Ed25519PrivateKey.from_private_bytes(args.key_file.read_bytes())
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                try:
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<100000: raise ValueError('invalid request size')
                    request=json.loads(self.rfile.read(size))
                    cert=attest(json.loads(args.registry.read_text()),request,key)
                    data=json.dumps(asdict(cert)).encode(); self.send_response(200)
                except Exception:
                    data=b'{"error":"authority unavailable"}'; self.send_response(502)
                self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(data)
        server=HTTPServer((args.bind,args.port),Handler)
        print(json.dumps({'listening_port':server.server_port}),flush=True)
        server.serve_forever()
        return
    request=json.load(sys.stdin)
    key=Ed25519PrivateKey.from_private_bytes(args.key_file.read_bytes() if args.key_file is not None
                                           else bytes.fromhex(request.pop('signing_key')))
    # The registry may contain arbitrary unrelated internal facts; none leave
    # the service except the single requested transaction's authorization status.
    registry=json.loads(args.registry.read_text())
    print(json.dumps(asdict(attest(registry,request,key))))


if __name__=='__main__': main()
