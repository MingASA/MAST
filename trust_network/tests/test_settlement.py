import numpy as np
import pytest
from trust_network.core.graph import Graph, Node
from trust_network.solve.attribution import Posterior, Latent
from trust_network.solve.settlement import Proportional, BearerOnly, CostEvent, settle


def fixture():
    return Graph((Node('s','process','seller'),Node('v','verify','bank',payer='seller'),Node('t','process','buyer',L=100)),(),'s')


def test_shares_normalize_random_posteriors():
    g=fixture(); rng=np.random.default_rng(7)
    states=(Latent(),Latent('s'),Latent('s',frozenset({'v'})),Latent(None,frozenset({'v'})))
    for _ in range(1000):
        p=Posterior(tuple(zip(states,rng.dirichlet(np.ones(4)))))
        share=Proportional(float(rng.random())).shares(g,'t',p)
        assert sum(x for _,x in share.amounts)==pytest.approx(1,abs=1e-12)
        assert all(x>=0 for _,x in share.amounts)


def test_transfer_neutrality_including_flag_costs():
    g=fixture(); p=Posterior(((Latent('s',frozenset({'v'})),1.),))
    events=(CostEvent('v',3.7,0,p),CostEvent('t',0,100,p))
    a=settle(g,events,Proportional()); b=settle(g,events,BearerOnly())
    assert a.social==b.social==103.7
    assert a.net != b.net
    assert sum(v for _,v in a.net)==pytest.approx(a.social)
    assert sum(v for _,v in b.net)==pytest.approx(b.social)


def test_scope_and_null_origin_fallback():
    g=fixture()
    p=Posterior(((Latent('s',frozenset({'v'})),1.),))
    assert Proportional(eligible_checks=frozenset()).shares(g,'t',p).for_org('seller')==1
    assert Proportional().shares(g,'t',Posterior(((Latent(),1.),))).for_org('buyer')==1
