"""Durable six-shard supervisor. Restart only untouched workflows; no automatic paid replay."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
from trust_network.benchmark.layered.storage import write_json
OUT=ROOT/'results/final_unified_live_v1_20260911'
ENV=Path('/home/cjy/cyberagent/.env')


def main():
    with (OUT/'supervisor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        jobs=[];streams=[]
        for shard in range(6):
            stream=(OUT/'shards'/f'{shard}.log').open('a');streams.append(stream)
            cmd=[sys.executable,'-m','trust_network.benchmark.layered.final_run','run',
                 '--output',str(OUT),'--env-file',str(ENV),'--allow-paid','--shards','6','--shard',str(shard)]
            jobs.append(subprocess.Popen(cmd,stdout=stream,stderr=subprocess.STDOUT))
        write_json(OUT/'supervisor.json',{'pid':os.getpid(),'shard_pids':[p.pid for p in jobs],'status':'running'})
        while any(p.poll() is None for p in jobs):
            states=[]
            for path in (OUT/'runs').glob('*/state.json'):
                states.append(json.loads(path.read_text())['status'])
            write_json(OUT/'progress.json',{'status':'running','planned':350,
                'completed':states.count('completed'),'unknown':states.count('unknown'),
                'started':states.count('started'),'not_started':350-len(states),
                'shard_exit_codes':[p.poll() for p in jobs]})
            time.sleep(15)
        for stream in streams:stream.close()
        write_json(OUT/'supervisor.json',{'pid':os.getpid(),'status':'finished','shard_exit_codes':[p.returncode for p in jobs]})
        code=subprocess.call([sys.executable,'-m','trust_network.benchmark.layered.final_run','summary','--output',str(OUT)])
        print(json.dumps({'summary_exit':code,'shard_exit_codes':[p.returncode for p in jobs]}),flush=True)

if __name__=='__main__':main()
