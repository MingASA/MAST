"""Authenticated organization endpoint for deployment on separate machines.

Remote binds require TLS. Each host gets only its own organization directory,
model configuration and service token. Never expose a signing key on the wire.
"""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import hmac
import json
import ssl
import urllib.request
from trust_network.demo.negotiation_worker import handle


class RemoteOrganization:
    def __init__(self,endpoint,token,ca_file=None):
        if not endpoint.startswith('https://') and not endpoint.startswith(('http://127.0.0.1:','http://localhost:')):
            raise ValueError('remote organization endpoints require HTTPS')
        self.endpoint=endpoint; self.token=token
        self.context=ssl.create_default_context(cafile=ca_file)

    def call(self,request):
        wire=urllib.request.Request(self.endpoint,data=json.dumps(request).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token})
        with urllib.request.urlopen(wire,timeout=120,context=self.context) as response:
            return json.load(response)


def serve(directory,env_file,token,bind,port,tls_cert=None,tls_key=None):
    if len(token)<32: raise ValueError('service token must contain at least 32 characters')
    if bool(tls_cert)!=bool(tls_key): raise ValueError('both TLS certificate and key required')
    if bind not in ('127.0.0.1','localhost','::1') and tls_cert is None:
        raise ValueError('non-loopback service requires TLS')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                self.send_response(401); self.end_headers(); return
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<1_000_000: raise ValueError('invalid request length')
                request=json.loads(self.rfile.read(size))
                response=handle(directory,request,env_file)
                data=json.dumps(response,ensure_ascii=False).encode(); self.send_response(200)
            except Exception as exc:
                data=json.dumps({'error':'organization request failed','error_type':type(exc).__name__}).encode()
                self.send_response(422)
            self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(data)
    server=HTTPServer((bind,port),Handler)
    if tls_cert:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(tls_cert,tls_key)
        server.socket=context.wrap_socket(server.socket,server_side=True)
    print(json.dumps({'listening_port':server.server_port,'tls':bool(tls_cert)}),flush=True)
    server.serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--organization-dir',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--token-file',type=Path,required=True)
    parser.add_argument('--bind',default='127.0.0.1'); parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--tls-cert',type=Path); parser.add_argument('--tls-key',type=Path)
    args=parser.parse_args()
    serve(args.organization_dir,args.env_file,args.token_file.read_text().strip(),args.bind,args.port,args.tls_cert,args.tls_key)
