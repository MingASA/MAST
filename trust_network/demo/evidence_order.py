"""Order proof from an organization's signed predecessor chain, not wall time."""
from trust_network.demo.claim_channel import read
from trust_network.demo.documents import digest


def local_index(packets,public):
    result={}
    for packet in packets:
        owner,body=read(packet,public)
        if body.get('kind')!='gateway_event':raise ValueError('invalid local event')
        result[digest(packet)]=(owner,body)
    return result


def precedes(index,notice,head,owner,workflow):
    seen=set();previous_sequence=None
    while head in index and head not in seen:
        seen.add(head);signer,body=index[head]
        if signer!=owner or body.get('workflow')!=workflow:
            raise ValueError('foreign local predecessor')
        seq=body['sequence']
        if previous_sequence is not None and seq!=previous_sequence-1:
            raise ValueError('invalid local sequence')
        if head==notice:return True
        previous_sequence=seq;head=body['previous']
    # Missing prefix or no signed action binding is insufficient evidence.
    return False
