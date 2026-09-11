"""Content-bound release gate; a partially written metrics file cannot authorize live."""
import hashlib
import json
from pathlib import Path
from .spec import matrix


def source_hashes():
    root=Path(__file__).resolve().parents[3]
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root/'trust_network').rglob('*.py'))}


def verify_offline(directory):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    required={'metrics.json','progress.json','provenance.json'}
    if not required<=set(manifest):raise ValueError('manifest lacks required records')
    for name,expected in manifest.items():
        path=(directory/name).resolve()
        if not path.is_relative_to(directory.resolve()):raise ValueError('invalid archive path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('archive hash mismatch')
    progress=json.loads((directory/'progress.json').read_text())
    if progress.get('status')!='completed' or progress.get('mode')!='offline':
        raise ValueError('offline run is incomplete')
    provenance=json.loads((directory/'provenance.json').read_text())
    if provenance['source_hashes']!=source_hashes():raise ValueError('source changed after offline run')
    rows=json.loads((directory/'metrics.json').read_text())
    expected=set(matrix())
    actual=[(r['topology'],r['case'],r['layer']) for r in rows]
    if len(actual)!=len(expected) or set(actual)!=expected:raise ValueError('incomplete or duplicate matrix')
    if not {r['file'] for r in rows}<=set(manifest):raise ValueError('unhashed raw run')
    for r in rows:
        if not r['metrics']['fault_realized'] or r['metrics']['worker_errors']:
            raise ValueError('invalid execution in offline matrix')
    # Consistency of common inputs, without requiring equal outputs.
    for topology,case,_ in expected:
        selected=[r for r in rows if r['topology']==topology and r['case']==case]
        for field in ('workload_hash','event_tape_hash','proposal_tape_hash'):
            if len({r[field] for r in selected})!=1:raise ValueError('unpaired input '+field)
    return {'offline_manifest_sha256':hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),
            'source_hashes':provenance['source_hashes'],'matrix_rows':len(rows)}


def verify_validation(path):
    path=Path(path)
    value=json.loads(path.read_text())
    if value.get('status')!='passed' or value.get('return_code')!=0 or value.get('process_parity_cases',0)<5:
        raise ValueError('regression/process validation incomplete')
    if value.get('source_hashes')!=source_hashes():raise ValueError('validation is for different code')
    report=(path.parent/value['test_report']).resolve()
    if not report.is_relative_to(path.parent.resolve()):raise ValueError('invalid test report path')
    if hashlib.sha256(report.read_bytes()).hexdigest()!=value['test_report_sha256']:
        raise ValueError('test report hash mismatch')
    return value
