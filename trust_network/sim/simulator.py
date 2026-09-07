"""Sample physical errors separately from the defender's observations."""
from dataclasses import dataclass
from typing import Protocol, Literal
import numpy as np
from trust_network.core.graph import Graph, Node, NodeId

Signal = Literal["flag", "clear"]


@dataclass(frozen=True)
class Belief:
    organizations: tuple[str, ...]
    rho: tuple[float, ...]

    @property
    def r(self) -> float:
        return sum(self.rho)

    def __post_init__(self):
        if len(self.organizations) != len(self.rho) or len(set(self.organizations)) != len(self.organizations):
            raise ValueError("invalid belief dimensions")
        if any(not np.isfinite(x) or x < 0 for x in self.rho) or self.r > 1 + 1e-10:
            raise ValueError("invalid belief mass")


def phi(node: Node, p: float, r: float) -> float:
    return node.alpha + (1 - node.alpha) * p * r


def propagate(belief: Belief, node: Node, p: float) -> Belief:
    mass = [(1 - node.alpha) * p * x for x in belief.rho]
    mass[belief.organizations.index(node.org)] += node.alpha
    return Belief(belief.organizations, tuple(mass))


@dataclass(frozen=True)
class SignalUpdate:
    probability_flag: float
    r_flag: float
    r_clear: float
    r_flag_fixed: float


def bayes(node: Node, r: float) -> SignalUpdate:
    prob = node.delta * r + node.epsilon * (1 - r)
    flagged = node.delta * r / prob if prob else 0.0
    clear = (1 - node.delta) * r / (1 - prob) if prob < 1 else 0.0
    return SignalUpdate(prob, flagged, clear, (1 - node.mu) * flagged)


def update_rho(belief: Belief, node: Node, signal: Signal, repair: bool = True) -> Belief:
    """Exact source-independent likelihood update, preserving source ratios."""
    update = bayes(node, belief.r)
    target = (update.r_flag_fixed if repair else update.r_flag) if signal == "flag" else update.r_clear
    return Belief(belief.organizations, tuple(target * x / belief.r if belief.r else 0.0 for x in belief.rho))


@dataclass(frozen=True)
class DecisionContext:
    node: NodeId
    budget: float
    belief: Belief
    history: tuple[tuple[NodeId, bool, Signal | None], ...] = ()


class Policy(Protocol):
    def verify(self, context: DecisionContext) -> bool: ...


@dataclass(frozen=True)
class FixedPolicy:
    selected: frozenset[NodeId] = frozenset()

    def verify(self, context: DecisionContext) -> bool:
        return context.node in self.selected


@dataclass(frozen=True)
class Discovery:
    delta: float = .95
    epsilon: float = .02

    def __post_init__(self):
        if not 0 <= self.delta <= 1 or not 0 <= self.epsilon <= 1:
            raise ValueError("invalid discovery probabilities")


@dataclass(frozen=True)
class Step:
    node: NodeId
    corrupted_before: bool
    corrupted_after: bool
    origin: NodeId | None
    verified: bool
    signal: Signal | None
    fixed: bool
    budget_before: float
    belief_before: Belief


@dataclass(frozen=True)
class Trace:
    steps: tuple[Step, ...]
    discovery: Signal

    @property
    def false_negatives(self) -> frozenset[NodeId]:
        return frozenset(s.node for s in self.steps if s.signal == "clear" and s.corrupted_before)


def simulate(graph: Graph, policy: Policy, budget: float, rng: np.random.Generator,
             discovery: Discovery = Discovery()) -> Trace:
    graph.topological()
    current = graph.source
    origin = None
    belief = Belief(graph.organizations, (0.0,) * len(graph.organizations))
    p = 0.0
    steps = []
    while True:
        node = graph.node(current)
        # Independent new error dominates any surviving old error: a declared
        # latest-endogenous-origin convention for otherwise ambiguous collisions.
        inherited = origin is not None and rng.random() < p
        if rng.random() < node.alpha:
            origin = current
        elif not inherited:
            origin = None
        belief = propagate(belief, node, p)
        before = origin is not None
        history = tuple((s.node, s.verified, s.signal) for s in steps)
        selected = (node.type == "verify" and bool(graph.outgoing(current)) and
                    policy.verify(DecisionContext(current, budget, belief, history)))
        if selected and budget + 1e-12 < node.c + node.c_fix:
            raise ValueError("policy selected unaffordable verification")
        signal = None
        fixed = False
        initial_budget = budget
        initial_belief = belief
        if selected:
            signal = "flag" if rng.random() < (node.delta if before else node.epsilon) else "clear"
            budget -= node.c
            if signal == "flag":
                budget -= node.c_fix
                fixed = before and rng.random() < node.mu
                if fixed:
                    origin = None
            belief = update_rho(belief, node, signal)
        steps.append(Step(current, before, origin is not None, origin, selected,
                          signal, fixed, initial_budget, initial_belief))
        edges = graph.outgoing(current)
        if not edges:
            terminal_signal = "flag" if rng.random() < (discovery.delta if origin is not None else discovery.epsilon) else "clear"
            return Trace(tuple(steps), terminal_signal)
        edge = edges[int(rng.choice(len(edges), p=[e.q_uv for e in edges]))]
        current, p = edge.v, edge.p_uv
