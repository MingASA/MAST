"""Archive a code-bound regression result, including process parity cases."""
import argparse
import hashlib
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from .preflight import source_hashes
from .storage import write_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    before=source_hashes();xml=args.output/'tests.xml'
    command=[sys.executable,'-m','pytest','-q','--basetemp='+str(args.output/'pytest_work'),
             '--junitxml='+str(xml)]
    with (args.output/'tests.log').open('w') as log:
        completed=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    tests=list(ET.parse(xml).getroot().iter('testcase')) if xml.exists() else []
    parity=[t for t in tests if t.attrib.get('name','').startswith('test_process_matches_memory')]
    success=completed.returncode==0 and before==source_hashes() and len(parity)>=5
    write_json(args.output/'validation.json',{'status':'passed' if success else 'failed',
        'source_hashes':before,'return_code':completed.returncode,'tests':len(tests),
        'process_parity_cases':len(parity),'test_report':'tests.xml',
        'test_report_sha256':hashlib.sha256(xml.read_bytes()).hexdigest() if xml.exists() else None})
    print({'status':'passed' if success else 'failed','tests':len(tests),'process_parity_cases':len(parity)},flush=True)
    if not success:raise SystemExit(1)

if __name__=='__main__':main()
