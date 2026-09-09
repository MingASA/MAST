"""Explicit resubmission edges increment k; all other edges must form a DAG."""
from dataclasses import replace
import networkx as nx
from .graph import Graph, Node, Edge


def unroll(graph: Graph, K_max: int = 3, termination_loss: float = 100.0) -> Graph:
    if K_max < 0:
        raise ValueError("K_max must be nonnegative")
    ordinary = nx.DiGraph()
    ordinary.add_nodes_from(n.id for n in graph.nodes)
    ordinary.add_edges_from((e.u, e.v) for e in graph.edges if not e.resubmit)
    if not nx.is_directed_acyclic_graph(ordinary):
        raise ValueError("mark enough cycle edges resubmit=True to break all cycles")
    nodes = [replace(n, id=(n.id, k)) for k in range(K_max + 1) for n in graph.nodes]
    edges = []
    for k in range(K_max + 1):
        for index, e in enumerate(graph.edges):
            target = (e.v, k + int(e.resubmit))
            if e.resubmit and k == K_max:
                owner = graph.node(e.u)
                target = ("__termination__", index, k)
                nodes.append(Node(target, "process", owner.org, L=termination_loss,
                                  bearer=owner.bearer, forced_penalty=True))
            edges.append(Edge((e.u, k), target, e.q_uv, e.p_uv))
    result = Graph(tuple(nodes), tuple(edges), (graph.source, 0))
    reachable = nx.descendants(result.nx, result.source) | {result.source}
    result = Graph(tuple(n for n in nodes if n.id in reachable),
                   tuple(e for e in edges if e.u in reachable), result.source)
    result.topological()
    return result

