from trust_network.demo.claim_derivation import valid_derivation


def test_total_requires_complete_same_order_same_currency_sources():
    manifest={'predicate':'charge_manifest','value':{'order':'A','currency':'CNY','components':['goods','freight']}}
    goods={'predicate':'charge/goods','value':{'order':'A','currency':'CNY','component':'goods','cents':10000}}
    freight={'predicate':'charge/freight','value':{'order':'A','currency':'CNY','component':'freight','cents':700}}
    total={'predicate':'total_charge','value':{'order':'A','currency':'CNY','cents':10700}}
    assert valid_derivation('sum_charges',total,[manifest,goods,freight])
    assert not valid_derivation('sum_charges',total,[manifest,goods])
    assert not valid_derivation('sum_charges',total,[manifest,goods,goods])
    freight['value']['currency']='USD'
    assert not valid_derivation('sum_charges',total,[manifest,goods,freight])
    freight['value']['currency']='CNY'; freight['value']['order']='B'
    assert not valid_derivation('sum_charges',total,[manifest,goods,freight])
