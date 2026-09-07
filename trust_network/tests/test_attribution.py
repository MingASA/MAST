import pytest
from trust_network.core.graph import Node, Edge, Graph
from trust_network.solve.attribution import (decode, Observation, Check, Latent,
                                            monte_carlo_validation, survival_probabilities)
from trust_network.sim.simulator import Discovery


def test_monte_carlo_conditional_calibration():
    report=monte_carlo_validation()
    print(f'N={report.samples}, conditional KL={report.conditional_kl:.6f}, top-1={report.top1_accuracy:.6f}, Bayes expected top-1={report.expected_top1:.6f}')
    assert report.observation_groups==8
    assert report.conditional_kl < .015
    assert abs(report.top1_accuracy-report.expected_top1) < .025


def test_origin_survives_last_missed_verification():
    g=Graph((Node('s','process','a',alpha=1),Node('v','verify','b',delta=.5),Node('t','process','c',L=1)),(Edge('s','v'),Edge('v','t')),'s')
    obs=Observation((Check('s'),Check('v',True,'clear'),Check('t')),'flag')
    posterior=decode(g,obs,Discovery(1,0))
    assert posterior.mass==((Latent('s',frozenset({'v'})),1.),)
    assert posterior.smoothed_corruption==(1.,1.,1.)
    assert survival_probabilities(g,('s','v','t'))==(1.,1.,1.)


def test_false_alarm_and_impossible_evidence():
    g=Graph((Node('s','process','a'),),(),'s')
    obs=Observation((Check('s'),),'flag')
    assert decode(g,obs,Discovery(.9,.1)).mass==((Latent(),1.),)
    with pytest.raises(ValueError): decode(g,obs,Discovery(1,0))
