"""Typed workflow graph; routing probabilities are independent of signals."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Hashable, Literal
import math
import networkx as nx

NodeId = Hashable


@dataclass(frozen=True)
class Node:
    id: NodeId
    type: Literal["process", "verify"]
    org: str
    alpha: float = 0.0
    c: float = 0.0
    L: float = 0.0
    delta: float = 1.0
    epsilon: float = 0.0
    mu: float = 1.0
    c_fix: float = 0.0
    F: float = 0.0
    decision_maker: str | None = None
    payer: str | None = None
    bearer: str | None = None
    forced_penalty: bool = False

    def __post_init__(self):
        if self.type not in ("process", "verify"):
            raise ValueError("unknown node type")
        for name in ("alpha", "delta", "epsilon", "mu"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be a probability")
        for name in ("c", "L", "c_fix", "F"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.type == "verify" and self.alpha:
            raise ValueError("verify nodes cannot generate endogenous errors")
        for name in ("decision_maker", "payer", "bearer"):
            if getattr(self, name) is None:
                object.__setattr__(self, name, self.org)


@dataclass(frozen=True)
class Edge:
    u: NodeId
    v: NodeId
    q_uv: float = 1.0
    p_uv: float = 1.0
    resubmit: bool = False

    def __post_init__(self):
        if not 0 <= self.q_uv <= 1 or not 0 <= self.p_uv <= 1:
            raise ValueError("edge probabilities must be in [0,1]")


@dataclass
class Graph:
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    source: NodeId
    nx: nx.DiGraph = field(init=False, repr=False)

    def __post_init__(self):
        self.nx = nx.DiGraph()
        for node in self.nodes:
            if node.id in self.nx:
                raise ValueError("duplicate node")
            self.nx.add_node(node.id, data=node)
        if self.source not in self.nx:
            raise ValueError("missing source")
        for edge in self.edges:
            if edge.u not in self.nx or edge.v not in self.nx:
                raise ValueError("missing edge endpoint")
            if self.nx.has_edge(edge.u, edge.v):
                raise ValueError("duplicate edge")
            self.nx.add_edge(edge.u, edge.v, data=edge)
        for v in self.nx:
            out = self.outgoing(v)
            if out and not math.isclose(sum(e.q_uv for e in out), 1.0, abs_tol=1e-10):
                raise ValueError("outgoing routing probabilities must sum to one")

    def node(self, v: NodeId) -> Node:
        return self.nx.nodes[v]["data"]

    def outgoing(self, v: NodeId) -> tuple[Edge, ...]:
        return tuple(self.nx.edges[v, w]["data"] for w in self.nx.successors(v))

    def org_of(self, v: NodeId) -> str:
        return self.node(v).org

    @property
    def organizations(self) -> tuple[str, ...]:
        return tuple(sorted({o for n in self.nodes for o in
                             (n.org, n.decision_maker, n.payer, n.bearer)}))

    def topological(self) -> tuple[NodeId, ...]:
        if not nx.is_directed_acyclic_graph(self.nx):
            raise ValueError("unroll cycles before solving or simulating")
        return tuple(nx.topological_sort(self.nx))
