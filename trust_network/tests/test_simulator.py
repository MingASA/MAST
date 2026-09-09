import numpy as np
from trust_network.core.graph import Node, Edge, Graph
from trust_network.sim.simulator import (simulate, FixedPolicy, Discovery,
                                        Belief, propagate, bayes, update_rho)


def test_physical_process_and_signals():
    graph = Graph((Node("s", "process", "a", alpha=1),
                   Node("v", "verify", "b"), Node("t", "process", "c")),
                  (Edge("s", "v"), Edge("v", "t")), "s")
    trace = simulate(graph, FixedPolicy(frozenset({"v"})), 1,
                     np.random.default_rng(5), Discovery(1, 0))
    assert trace.steps[0].origin == "s"
    assert trace.steps[1].signal == "flag" and trace.steps[1].fixed
    assert not trace.steps[-1].corrupted_after
    assert trace.discovery == "clear"


def test_rho_marginal_and_bayes_boundaries():
    belief = Belief(("a", "b"), (.1, .3))
    node = Node("v", "verify", "a", delta=.8, epsilon=.1, mu=.7)
    for signal in ("flag", "clear"):
        updated = update_rho(belief, node, signal)
        expected = bayes(node, belief.r)
        assert np.isclose(updated.r, expected.r_flag_fixed if signal == "flag" else expected.r_clear)
    assert bayes(Node("v", "verify", "a"), 0).r_flag == 0
    assert bayes(Node("v", "verify", "a"), 1).r_clear == 0
    assert np.isclose(propagate(belief, Node("p", "process", "b", alpha=.2), .7).r, .424)
