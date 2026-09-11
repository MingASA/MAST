"""Durable workspace-local checkpoints; no OS temporary directory dependency."""
import json
import os
from pathlib import Path


def write_json(path, value):
    path=Path(path)
    staged=path.with_name(path.name+'.pending')
    with staged.open('w') as f:
        os.chmod(staged,0o600)
        json.dump(value,f,ensure_ascii=False,indent=2)
        f.write('\n');f.flush();os.fsync(f.fileno())
    staged.replace(path)


def append_json(path, value):
    with Path(path).open('a') as f:
        os.chmod(path,0o600)
        f.write(json.dumps(value,ensure_ascii=False)+'\n')
        f.flush();os.fsync(f.fileno())
