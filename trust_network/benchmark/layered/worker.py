"""One persistent organization process, with owner-local config and state."""
import json
import sys
from pathlib import Path
from .storage import write_json
from .backend import Node

def main():
    node = Node(json.load(open(sys.argv[1])))
    local=[]
    def query(owner, request):
        if owner==node.owner:
            result=node.call(request,query)
            local.append({'owner':owner,'sender':owner,'op':request['op'],'request':request,'response':result})
            return result
        print(json.dumps({'owner':owner,'_query':request}),flush=True)
        return json.loads(sys.stdin.readline())
    for line in sys.stdin:
        local.clear()
        try:
            result = node.call(json.loads(line),query)
        except (ValueError,KeyError,StopIteration) as exc:
            result = {'error':type(exc).__name__,'message':str(exc)}
        state={'gateway':node.g.snapshot() if node.g else None,'messages':node.messages,
               'revoked':sorted(node.revoked),'effects':node.effects,'batches':node.batches}
        write_json(Path(sys.argv[1]).with_suffix('.state.json'),state)
        result['_local_exchanges']=list(local)
        print(json.dumps(result),flush=True)

if __name__ == '__main__': main()
