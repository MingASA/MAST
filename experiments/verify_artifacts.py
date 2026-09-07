"""Read-only verification of the saved mathematical and MiniMax artifacts."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import csv
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from trust_network.demo.documents import Certificate


def main():
    root=Path(__file__).resolve().parents[1]/'results'
    with (root/'poa.csv').open() as stream: rows=list(csv.DictReader(stream))
    assert len(rows)>=12
    for row in rows:
        if row['converged']=='True':
            assert float(row['exploitability'])<1e-8
            assert float(row['observed_poa'])>=1-1e-8
    verified=0
    for directory in ('minimax_v2','minimax_containers'):
        folder=root/directory
        if not (folder/'summary.json').exists(): continue
        summaries=json.loads((folder/'summary.json').read_text())
        for summary in summaries:
            log=folder/f"{summary['protocol']}_{summary['objective']}.jsonl"
            events=[json.loads(line) for line in log.read_text().splitlines()]
            assert len(events)==summary['calls']
            for event in events:
                cert=Certificate(**event['certificate'])
                assert cert.issuer==event['organization']
                assert cert.version==event['version'] and cert.bundle_hash==event['bundle_hash']
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(event['public_key'])).verify(bytes.fromhex(cert.signature),cert.payload())
                verified+=1
    print(f'{len(rows)} equilibrium rows checked; {verified} saved signatures verified')


if __name__=='__main__': main()
