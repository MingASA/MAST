import numpy as np
import pytest
from trust_network.core.graph import Graph,Node,Edge
from trust_network.solve.attribution import (Latent,Posterior,Observation,Check,ResponsibilityContext,decode,infer_omission_opportunities)
from trust_network.sim.simulator import Discovery
from trust_network.solve.settlement import Proportional,ProportionalWithOmission,BearerOnly,CostEvent,settle,allocation_shares
from trust_network.solve.decentralized_game import DecentralizedGame,GameConfig
from trust_network.solve.verification_metrics import expected_checks,planner_metrics,over_check_ratio


def case():
    g=Graph((Node('s','process','seller',alpha=.3),Node('v','verify','bank',c=.4,delta=.8,c_fix=.1),
             Node('w','verify','bank2',c=.5,delta=.9),Node('t','process','buyer',L=10)),
            (Edge('s','v'),Edge('v','w'),Edge('w','t')),'s')
    context=ResponsibilityContext(Observation((Check('s'),Check('v'),Check('w'),Check('t')),'flag'),1.,Discovery(.9,.1))
    return g,context


@pytest.mark.parametrize('rule',[BearerOnly(),Proportional(),*[ProportionalWithOmission(w_omit=w) for w in (0,.5,1,2)]])
def test_round2_random_shares_and_transfer_neutrality(rule):
    g,context=case(); rng=np.random.default_rng(191)
    states=(Latent(),Latent('s'),Latent('s',frozenset({'v','w'})),Latent(None,frozenset({'v'})))
    for _ in range(1000):
        posterior=Posterior(tuple(zip(states,rng.dirichlet(np.ones(4)))))
        shares=allocation_shares(rule,g,'t',posterior,context)
        assert sum(p for _,p in shares.amounts)==pytest.approx(1,abs=1e-12)
        events=(CostEvent('v',.4,0,posterior,context),CostEvent('t',0,10,posterior,context))
        result=settle(g,events,rule)
        assert result.social==settle(g,events,Proportional()).social
        assert sum(p for _,p in result.net)==pytest.approx(result.social)


def test_zero_omission_is_bitwise_legacy_even_with_mixed_origins():
    g,context=case()
    p=Posterior(((Latent('s'),.2),(Latent('s',frozenset({'v'})),.3),(Latent('s',frozenset({'v','w'})),.1),(Latent(),.4)))
    assert ProportionalWithOmission(w_omit=0).shares(g,'t',p)==Proportional().shares(g,'t',p)
    a=DecentralizedGame(g,GameConfig(1,'black_box','resp'))
    b=DecentralizedGame(g,GameConfig(1,'black_box','resp',allocation=ProportionalWithOmission(w_omit=0)))
    for start in (0,1):
        ar=a.solve({k:start for k in a.keys}); br=b.solve({k:start for k in b.keys})
        assert ar.social==br.social and ar.strategy==br.strategy
        assert expected_checks(a,dict(ar.strategy))==expected_checks(b,dict(br.strategy))
        assert planner_metrics(a)==planner_metrics(b)


def test_omission_uses_future_evidence_and_actual_budget():
    g,context=case()
    opportunities=infer_omission_opportunities(g,context)
    expected=.3*.9/(.3*.9+.7*.1)
    assert opportunities[1].omission_weight==pytest.approx(expected*.8)
    assert opportunities[2].omission_weight==pytest.approx(expected*.9)
    assert not opportunities[0].available and not opportunities[-1].available
    low=ResponsibilityContext(context.observation,.39,context.discovery_model)
    assert not any(o.omitted for o in infer_omission_opportunities(g,low))
    context2=ResponsibilityContext(Observation((Check('s'),Check('v',True,'flag'),Check('w'),Check('t')),'clear'),.8)
    ops=infer_omission_opportunities(g,context2)
    assert not ops[1].omitted and not ops[2].available
    assert ops[2].budget_before==pytest.approx(.3)


def test_omission_allocates_to_skipping_org_and_preserves_null_fallback():
    g,c=case(); p=decode(g,c.observation,c.discovery_model)
    old=Proportional().shares(g,'t',p)
    new=ProportionalWithOmission(w_omit=2).shares(g,'t',p,c)
    assert old.for_org('bank')==0 and new.for_org('bank')>0
    assert new.for_org('buyer')==pytest.approx(old.for_org('buyer'))
    assert ProportionalWithOmission().shares(g,'t',Posterior(((Latent(),1.),)),c).for_org('buyer')==1


def test_check_metric_counts_calls_and_handles_zero():
    g,c=case(); game=DecentralizedGame(g,GameConfig(.4))
    assert expected_checks(game,{k:1 for k in game.keys})==0 # reserve c+c_fix required
    assert over_check_ratio(0,0)==1 and over_check_ratio(1,0)==float('inf')


def test_omission_changes_verification_incentive_but_not_fixed_policy_social_cost():
    g=Graph((Node('s','process','seller',alpha=1),Node('v','verify','bank',c=.4),Node('t','process','buyer',L=10)),(Edge('s','v'),Edge('v','t')),'s')
    legacy=DecentralizedGame(g,GameConfig(.5,'certificate','resp'))
    omission=DecentralizedGame(g,GameConfig(.5,'certificate','resp',allocation=ProportionalWithOmission()))
    for action in (0,1):
        old=legacy.evaluate({k:action for k in legacy.keys})
        new=omission.evaluate({k:action for k in omission.keys})
        assert sum(old)==pytest.approx(sum(new))
    a,b=legacy.solve(),omission.solve()
    assert a.social==pytest.approx(10)
    assert b.social==pytest.approx(.4)
    assert expected_checks(legacy,dict(a.strategy))==0
    assert expected_checks(omission,dict(b.strategy))==1
