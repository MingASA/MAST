import pytest
from trust_network.demo.claim_channel import ClaimGateway,issue
from trust_network.demo.claim_action_contract import approve_invoice
from trust_network.demo.documents import keypair,digest


def test_correct_total_is_not_action_authorization():
    keys={o:keypair() for o in ('buyer','billing','receiver')}
    gateway=ClaimGateway('receiver',keys['receiver'][0],{o:k[1] for o,k in keys.items()},'w',
                         {'invoice_authorization':'buyer','total_charge':'billing'})
    def add(owner,predicate,value):
        packet=issue(owner,keys[owner][0],{'kind':'claim','workflow':'w','parents':[],
                                        'fact':{'predicate':predicate,'value':value}})
        gateway.receive(packet); return packet
    total=add('billing','total_charge',{'order':'A','currency':'CNY','cents':10700})
    authorization={'order':'A','operation':'approve_invoice','currency':'CNY','maximum_cents':11000,'approved':True}
    effects=[]
    with pytest.raises(ValueError): approve_invoice(gateway,[digest(total)],'A',lambda:effects.append('invalid'))
    wrong=add('buyer','invoice_authorization',dict(authorization,order='B'))
    with pytest.raises(ValueError,match='cross_order'): approve_invoice(gateway,[digest(total),digest(wrong)],'A',lambda:effects.append('invalid'))
    valid=add('buyer','invoice_authorization',authorization)
    assert approve_invoice(gateway,[digest(total),digest(valid)],'A',lambda:{'invoice_approved':'A'})=={'invoice_approved':'A'}
    revoke=issue('buyer',keys['buyer'][0],{'kind':'revoke','workflow':'w','target':digest(valid),'original':valid})
    gateway.receive(revoke)
    with pytest.raises(ValueError,match='revoked'): approve_invoice(gateway,[digest(total),digest(valid)],'A',lambda:effects.append('invalid'))
    assert effects==[]
