import pytest
from trust_network.core.graph import Node, Edge, Graph
from trust_network.core.unroll import unroll


def test_unroll_and_roles():
    g = Graph((Node("a", "process", "seller"),
               Node("b", "verify", "bank", bearer="buyer")),
              (Edge("a", "b"), Edge("b", "a", resubmit=True)), "a")
    u = unroll(g, 3)
    assert len(u.topological()) == 9
    terminal = next(n for n in u.nodes if n.forced_penalty)
    assert terminal.bearer == "buyer"
    assert u.node(("b", 2)).decision_maker == "bank"


def test_invalid_routing():
    with pytest.raises(ValueError):
        Graph((Node(0, "process", "a"), Node(1, "process", "b")),
              (Edge(0, 1, .5),), 0)
