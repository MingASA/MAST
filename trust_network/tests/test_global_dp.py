import numpy as np
import pytest
from trust_network.core.graph import Graph, Node, Edge
from trust_network.solve.global_dp import GlobalDP, PerfectBaseline, DPConfig


def example():
    return Graph((Node('s','process','a',alpha=.12), Node('v','verify','a',c=.3),
                  Node('p','process','b',alpha=.07),Node('w','verify','b',c=.4),
                  Node('t','process','b',L=4)),
                 (Edge('s','v'),Edge('v','p',.6,.8),Edge('v','t',.4,.9),
                  Edge('p','w'),Edge('w','t',1,.9)), 's')


def test_perfect_numeric_matches_independent_piecewise():
    g=example()
    exact=PerfectBaseline(g)
    numeric=GlobalDP(g,DPConfig(1.,10001))
    points=np.r_[np.linspace(0,1,101),np.random.default_rng(12).uniform(size=200)]
    errors=[]
    for v in g.topological():
        for b in (0.,.3,.4,.7,1.):
            errors.extend(abs(numeric.value(v,b,float(r))-exact.value(v,b,float(r))) for r in points)
            # Include the exact breakpoints: random samples alone can miss the
            # narrow interpolation cells where a policy switch creates error.
            for r in exact.function(v,b).knots:
                errors.append(abs(numeric.value(v,b,r)-exact.value(v,b,r)))
            tau=exact.threshold(v,b)
            if np.isfinite(tau):
                assert abs(numeric.threshold(v,b)-tau) <= 2e-4
    print(f'Perfect baseline maximum error: {max(errors):.8f}')
    assert max(errors) < 1e-3


def test_default_grid_and_budget_and_imperfect_cost():
    g=Graph((Node('v','verify','a',c=1,c_fix=.5,F=.2,delta=.8,epsilon=.1,mu=.5),
             Node('t','process','a',L=10)),(Edge('v','t'),),'v')
    dp=GlobalDP(g,DPConfig(2))
    assert len(dp.grid)==101
    assert dp.value('v',1,.8)==pytest.approx(8)
    pf=.8*.8+.1*.2
    remaining=.8*(1-.8*.5)
    assert dp.value('v',2,.8)==pytest.approx(min(8,1+pf*.7+remaining*10))
    with pytest.raises(ValueError): PerfectBaseline(g)


def test_refinement_converges():
    g=example(); exact=PerfectBaseline(g)
    errors=[]
    for size in (101,1001,10001):
        dp=GlobalDP(g,DPConfig(1,size))
        errors.append(max(abs(dp.value('s',1,r)-exact.value('s',1,r)) for r in np.linspace(0,1,317)))
    assert errors[-1] < 1e-3
    assert errors[-1] <= errors[0]+1e-12
