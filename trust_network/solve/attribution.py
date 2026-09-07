"""Exact augmented-state forward/backward inference, conditioned on a path.

Actions are treated as known interventions. For adaptive private policies the game
solver integrates its own complete observation tree instead of misusing this API.
"""
from dataclasses import dataclass
from collections import defaultdict
from math import log
from trust_network.core.graph import Graph, Node, NodeId
from trust_network.sim.simulator import Trace, Signal, Discovery


@dataclass(frozen=True)
class Latent:
    origin: NodeId | None = None
    false_negatives: frozenset[NodeId] = frozenset()


@dataclass(frozen=True)
class Check:
    node: NodeId
    verified: bool = False
    signal: Signal | None = None


@dataclass(frozen=True)
class Observation:
    checks: tuple[Check, ...]
    discovery: Signal

    @classmethod
    def from_trace(cls, trace: Trace):
        return cls(tuple(Check(s.node,s.verified,s.signal) for s in trace.steps),trace.discovery)


@dataclass(frozen=True)
class Posterior:
    mass: tuple[tuple[Latent,float], ...]
    evidence: float = 1.0
    smoothed_corruption: tuple[float, ...] = ()

    def __post_init__(self):
        import math
        if not self.mass or len({s for s,_ in self.mass}) != len(self.mass):
            raise ValueError('empty or duplicated posterior states')
        if any(not math.isfinite(p) or p < 0 for _,p in self.mass) or not math.isclose(sum(p for _,p in self.mass),1,abs_tol=1e-9):
            raise ValueError('posterior must normalize')

    @property
    def entropy(self):
        return -sum(p*log(p) for _,p in self.mass if p)

    @property
    def top1(self):
        return max(self.mass,key=lambda pair:pair[1])[0]


def physical_transition(state: Latent, node: Node, p: float):
    """Latest endogenous origin, otherwise survival of the inherited origin."""
    output=defaultdict(float)
    output[Latent(node.id,state.false_negatives)] += node.alpha
    survive=p if state.origin is not None else 0.
    output[state] += (1-node.alpha)*survive
    output[Latent(None,state.false_negatives)] += (1-node.alpha)*(1-survive)
    return tuple((s,w) for s,w in output.items() if w > 0)


def check_transition(state: Latent, node: Node, check: Check):
    if not check.verified:
        if check.signal is not None: raise ValueError('signal on an uncalled check')
        return ((state,1.),)
    if node.type != 'verify': raise ValueError('checking a process node')
    pf=node.delta if state.origin is not None else node.epsilon
    output=defaultdict(float)
    if check.signal in (None,'clear'):
        missed=state.false_negatives | ({node.id} if state.origin is not None else set())
        output[Latent(state.origin,frozenset(missed))] += 1-pf
    if check.signal in (None,'flag'):
        if state.origin is None: output[state] += pf
        else:
            output[state] += pf*(1-node.mu)
            output[Latent(None,state.false_negatives)] += pf*node.mu
    if check.signal not in (None,'clear','flag'): raise ValueError('unknown signal')
    return tuple((s,w) for s,w in output.items() if w > 0)


def decode(graph: Graph, observation: Observation, discovery: Discovery = Discovery()) -> Posterior:
    graph.topological()
    if not observation.checks or observation.checks[0].node != graph.source:
        raise ValueError('observation must start at source')
    if observation.discovery not in ('flag','clear'): raise ValueError('unknown discovery signal')
    forward=[{Latent():1.}]
    kernels=[]
    previous=None
    for check in observation.checks:
        node=graph.node(check.node)
        if previous is None: p=0.
        else: p=graph.nx.edges[previous,check.node]['data'].p_uv
        current=defaultdict(float); kernel={}
        for old,weight in forward[-1].items():
            row=defaultdict(float)
            for middle,pm in physical_transition(old,node,p):
                for new,pn in check_transition(middle,node,check): row[new] += pm*pn
            kernel[old]=row
            for new,prob in row.items(): current[new] += weight*prob
        kernels.append(kernel); forward.append(dict(current)); previous=check.node
    def likelihood(state):
        pf=discovery.delta if state.origin is not None else discovery.epsilon
        return pf if observation.discovery=='flag' else 1-pf
    backward=[{} for _ in forward]
    backward[-1]={s:likelihood(s) for s in forward[-1]}
    evidence=sum(w*backward[-1][s] for s,w in forward[-1].items())
    if evidence <= 0: raise ValueError('impossible observation')
    for t in range(len(kernels)-1,-1,-1):
        backward[t]={old:sum(p*backward[t+1].get(new,0) for new,p in row.items()) for old,row in kernels[t].items()}
    smooth=tuple(sum(w*backward[t].get(s,0) for s,w in forward[t].items() if s.origin is not None)/evidence for t in range(1,len(forward)))
    mass=tuple((s,w*likelihood(s)/evidence) for s,w in forward[-1].items() if w*likelihood(s)>0)
    return Posterior(mass,evidence,smooth)


def survival_probabilities(graph: Graph, path: tuple[NodeId,...]) -> tuple[float,...]:
    if not path: return ()
    values=[1.]*len(path)
    for k in range(len(path)-2,-1,-1):
        values[k]=values[k+1]*graph.nx.edges[path[k],path[k+1]]['data'].p_uv
    return tuple(values)


@dataclass(frozen=True)
class Calibration:
    samples: int
    observation_groups: int
    conditional_kl: float
    top1_accuracy: float
    expected_top1: float


def monte_carlo_validation(samples: int = 12000, seed: int = 902) -> Calibration:
    import numpy as np
    from collections import Counter
    from trust_network.core.graph import Edge
    from trust_network.sim.simulator import simulate, FixedPolicy
    if samples < 10000: raise ValueError('acceptance validation requires N>=10000')
    graph=Graph((Node('s','process','seller',alpha=.28),
                 Node('v','verify','bank',delta=.72,epsilon=.09,mu=.65),
                 Node('a','process','buyer',alpha=.13,L=10),
                 Node('b','process','buyer',alpha=.21,L=10)),
                (Edge('s','v',1,.85),Edge('v','a',.6,.8),Edge('v','b',.4,.7)),'s')
    policy=FixedPolicy(frozenset({'v'})); rng=np.random.default_rng(seed)
    counts=defaultdict(Counter); cache={}; correct=0; expected=0.
    for _ in range(samples):
        trace=simulate(graph,policy,1,rng)
        obs=Observation.from_trace(trace)
        truth=Latent(trace.steps[-1].origin,trace.false_negatives)
        counts[obs][truth]+=1
        if obs not in cache: cache[obs]=decode(graph,obs)
        posterior=cache[obs]
        correct += truth==posterior.top1
        expected += max(p for _,p in posterior.mass)
    kl=0.
    for obs,counter in counts.items():
        total=sum(counter.values()); target=dict(cache[obs].mass)
        for state,count in counter.items():
            empirical=count/total
            kl += count/samples*log(empirical/target[state])
    return Calibration(samples,len(counts),kl,correct/samples,expected/samples)


if __name__=='__main__':
    import json
    from dataclasses import asdict
    print(json.dumps(asdict(monte_carlo_validation()),indent=2))


@dataclass(frozen=True)
class ResponsibilityContext:
    observation: Observation
    initial_budget: float
    discovery_model: Discovery = Discovery()


@dataclass(frozen=True)
class OmissionOpportunity:
    node: NodeId
    budget_before: float
    available: bool
    omitted: bool
    posterior_corruption: float
    omission_weight: float


def infer_omission_opportunities(graph: Graph, context: ResponsibilityContext) -> tuple[OmissionOpportunity, ...]:
    """Reuse the same forward/backward smoother, including future evidence.

    At a skipped check pre/post-check X coincide. The public audit includes the
    full actually observed check history, even when protocol 0 hides it online.
    """
    posterior=decode(graph,context.observation,context.discovery_model)
    budget=context.initial_budget
    if budget < 0: raise ValueError('negative initial budget')
    opportunities=[]
    for check,r in zip(context.observation.checks,posterior.smoothed_corruption):
        node=graph.node(check.node)
        available=(node.type=='verify' and bool(graph.outgoing(node.id)) and budget+1e-10>=node.c+node.c_fix)
        if check.verified and not available: raise ValueError('unavailable check in audit')
        omitted=available and not check.verified
        opportunities.append(OmissionOpportunity(node.id,budget,available,omitted,r,r*node.delta if omitted else 0.))
        if check.verified:
            if check.signal is None: raise ValueError('budget replay requires observed check signals')
            budget-=node.c+(node.c_fix if check.signal=='flag' else 0.)
    return tuple(opportunities)
