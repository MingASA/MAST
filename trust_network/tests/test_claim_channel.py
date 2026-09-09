from trust_network.demo.claim_channel import ClaimGateway, issue
from trust_network.demo.documents import keypair, digest
import pytest


def test_multihop_revocation_and_unrelated_branch():
    keys={o:keypair() for o in ('authority','broker','executor')}
    public={o:k[1] for o,k in keys.items()}
    gateway=ClaimGateway('executor',keys['executor'][0],public,'w',{'price':'authority'})
    def claim(owner,value,parents=()):
        return issue(owner,keys[owner][0],{'kind':'claim','workflow':'w',
            'fact':{'predicate':'price','value':value},'parents':list(parents)})
    source=claim('authority',100); relay=claim('broker',100,[digest(source)])
    other=claim('authority',200)
    for packet in (source,relay,other): assert gateway.receive(packet)['body']['action']=='received'
    changed=claim('broker',0,[digest(source)])
    assert gateway.receive(changed)['body']['reasons']==['unsupported_transformation']
    revoke=issue('authority',keys['authority'][0],{'kind':'revoke','workflow':'w',
        'target':digest(source),'original':source})
    gateway.receive(revoke)
    assert gateway.use(digest(relay),'pay')['body']['action']=='use_blocked'
    assert gateway.use(digest(other),'pay')['body']['action']=='use_allowed'
    effects=[]
    with pytest.raises(ValueError,match='blocked execution'):
        gateway.execute(digest(relay),'pay',lambda: effects.append('invalid'))
    gateway.execute(digest(other),'pay',lambda: effects.append('unrelated'))
    assert effects==['unrelated']
    # Another receiver missed the notification. A fresh authority challenge
    # still blocks an already revoked root without reading the private registry.
    uninformed=ClaimGateway('executor',keys['executor'][0],public,'w',{'price':'authority'})
    for packet in (source,relay): uninformed.receive(packet)
    def authority_reply(owner,query):
        return issue(owner,keys[owner][0],{'kind':'status_reply','query':query,'status':'revoked'})
    with pytest.raises(ValueError,match='did not confirm'):
        uninformed.execute_checked(digest(relay),'pay',authority_reply,lambda:effects.append('stale'))
    assert effects==['unrelated']
    late=ClaimGateway('executor',keys['executor'][0],public,'w',{'price':'authority'})
    late.receive(revoke)
    assert late.receive(source)['body']['action']=='blocked'
    assert late.receive(relay)['body']['action']=='blocked'
