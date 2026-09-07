import itertools
import pytest
from trust_network.core.graph import Graph, Node, Edge
from trust_network.solve.decentralized_game import DecentralizedGame,GameConfig,price_of_anarchy
from trust_network.solve.global_dp import GlobalDP,DPConfig


def small():
    return Graph((Node('s','process','seller',alpha=.3),
                  Node('v','verify','bank',c=.2,delta=.8,epsilon=.1,mu=.8),
                  Node('w','verify','buyer',c=.3,delta=.8,epsilon=.1,mu=.9),
                  Node('t','process','buyer',L=10)),
                 (Edge('s','v'),Edge('v','w'),Edge('w','t')),'s')


def test_best_response_matches_exhaustive_and_scope():
    game=DecentralizedGame(small(),GameConfig(1,'black_box','resp'))
    profile={k:0 for k in game.keys}
    for org in game.orgs:
        keys=[k for k in game.keys if k[0]==org]
        result,value=game.best_response(org,profile)
        index=game.orgs.index(org)
        exhaustive=[]
        for choices in itertools.product((0,1),repeat=len(keys)):
            candidate=dict(profile); candidate.update(zip(keys,choices))
            exhaustive.append(game.evaluate(candidate)[index])
        assert value==pytest.approx(min(exhaustive))
        assert all(result.get(k,0)==profile[k] for k in game.keys if k[0]!=org)


def test_protocol_equivalence_and_equilibrium():
    results=[]
    for protocol in ('black_box','certificate','verified_certificate'):
        game=DecentralizedGame(small(),GameConfig(1,protocol,'resp'))
        result=game.solve(); results.append(result)
        assert result.converged and result.exploitability<1e-8
        assert sum(v for _,v in result.net)==pytest.approx(result.social)
    assert results[1].social==results[2].social
    optimum=GlobalDP(small(),DPConfig(1,1001)).value()
    assert all(r.social >= optimum-1e-3 for r in results)


def test_zero_denominator_and_decision_role():
    assert price_of_anarchy(0,0)==1
    assert price_of_anarchy(1,0)==float('inf')
    g=Graph((Node('s','process','seller',alpha=.5),Node('v','verify','bank',c=.1,decision_maker='buyer',payer='seller'),Node('t','process','buyer',L=10)),(Edge('s','v'),Edge('v','t')),'s')
    game=DecentralizedGame(g)
    assert all(k[0]=='buyer' for k in game.keys)


def test_cycle_detection_returns_witness(monkeypatch):
    game=DecentralizedGame(small())
    key=game.keys[0]
    def oscillating(org,strategy):
        result=dict(strategy)
        if org==key[0]: result[key]=1-result.get(key,0)
        return result,0.
    monkeypatch.setattr(game,'best_response',oscillating)
    result=game.solve()
    assert not result.converged and len(result.oscillation)==3


def test_hidden_signal_changes_best_response_value():
    # Fixed upstream verification produces two posterior risks. Public budget
    # is identical on flag/clear (c_fix=0), so it cannot leak the hidden signal.
    g=Graph((Node('s','process','s',alpha=.4),
             Node('v','verify','bank',c=.1,delta=.8,epsilon=.2,mu=.7),
             Node('w','verify','buyer',c=1.8),Node('t','process','buyer',L=10)),
            (Edge('s','v'),Edge('v','w'),Edge('w','t')),'s')
    values=[]
    for protocol in ('black_box','certificate','verified_certificate'):
        game=DecentralizedGame(g,GameConfig(2,protocol,'selfish'))
        profile={k:int(k[0]=='bank') for k in game.keys}
        _,value=game.best_response('buyer',profile)
        values.append(value)
    assert values[0]==pytest.approx(1.76)
    assert values[1]==pytest.approx(1.592)
    assert values[2]==pytest.approx(values[1])
