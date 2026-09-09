"""Pluggable responsibility allocation; transfers conserve realized total cost."""
from dataclasses import dataclass
from typing import Protocol
import math
from trust_network.core.graph import Graph, NodeId
from trust_network.solve.attribution import Posterior, Latent, Observation, Check, decode, ResponsibilityContext
from trust_network.sim.simulator import Trace, Discovery


@dataclass(frozen=True)
class Shares:
    amounts: tuple[tuple[str,float], ...]

    def __post_init__(self):
        if len({o for o,_ in self.amounts}) != len(self.amounts) or any(not math.isfinite(v) or v<0 for _,v in self.amounts) or not math.isclose(sum(v for _,v in self.amounts),1,abs_tol=1e-9):
            raise ValueError('shares must be nonnegative and sum to one')

    def for_org(self, org): return dict(self.amounts).get(org,0.)


class Allocation(Protocol):
    def shares(self, graph: Graph, loss_node: NodeId, posterior: Posterior) -> Shares: ...


@dataclass(frozen=True)
class Proportional:
    missed_weight: float = .35
    eligible_checks: frozenset[NodeId] | None = None

    def __post_init__(self):
        if not 0 <= self.missed_weight <= 1: raise ValueError('invalid missed-check weight')

    def shares(self, graph, loss_node, posterior):
        weights={o:0. for o in graph.organizations}
        bearer=graph.node(loss_node).bearer
        for state,p in posterior.mass:
            if state.origin is None:
                weights[bearer]+=p
                continue
            missed=state.false_negatives
            if self.eligible_checks is not None: missed=missed & self.eligible_checks
            fraction=self.missed_weight if missed else 0.
            weights[graph.node(state.origin).org]+=p*(1-fraction)
            for v in missed: weights[graph.node(v).decision_maker]+=p*fraction/len(missed)
        return Shares(tuple(weights.items()))


@dataclass(frozen=True)
class BearerOnly:
    def shares(self, graph, loss_node, posterior):
        return Shares(tuple((o,float(o==graph.node(loss_node).bearer)) for o in graph.organizations))


@dataclass(frozen=True)
class CostEvent:
    node: NodeId
    verification_cost: float
    loss: float
    posterior: Posterior
    context: ResponsibilityContext | None = None


@dataclass(frozen=True)
class Settlement:
    net: tuple[tuple[str,float], ...]
    social: float


def settle(graph: Graph, events: tuple[CostEvent,...], allocation: Allocation = Proportional()) -> Settlement:
    net={o:0. for o in graph.organizations}
    for event in events:
        node=graph.node(event.node)
        if event.loss < 0 or event.verification_cost < 0: raise ValueError('negative cost')
        net[node.payer]+=event.verification_cost
        shares=allocation_shares(BearerOnly() if node.forced_penalty else allocation,graph,event.node,event.posterior,event.context)
        for org,share in shares.amounts: net[org]+=event.loss*share
    social=math.fsum(e.verification_cost+e.loss for e in events)
    return Settlement(tuple(net.items()),social)


def settle_trace(graph: Graph, trace: Trace, allocation: Allocation = Proportional(), discovery: Discovery = Discovery()):
    events=[]
    for index,step in enumerate(trace.steps):
        node=graph.node(step.node)
        cost=node.c+((node.F+node.c_fix) if step.signal=='flag' else 0) if step.verified else 0.
        loss=node.L*float(node.forced_penalty or step.corrupted_after)
        if index==len(trace.steps)-1:
            posterior=decode(graph,Observation.from_trace(trace),discovery)
        else:
            # No discovery observation at intermediate actions: constant likelihood.
            obs=Observation(tuple(Check(s.node,s.verified,s.signal) for s in trace.steps[:index+1]),'flag')
            posterior=decode(graph,obs,Discovery(.5,.5))
        obs=Observation.from_trace(trace) if index==len(trace.steps)-1 else obs
        model=discovery if index==len(trace.steps)-1 else Discovery(.5,.5)
        context=ResponsibilityContext(obs,trace.steps[0].budget_before,model)
        events.append(CostEvent(node.id,cost,loss,posterior,context))
    return settle(graph,tuple(events),allocation)


@dataclass(frozen=True)
class ProportionalWithOmission:
    """Continuous omission extension anchored to legacy Proportional.

    See MODEL_DECISIONS.md: the requested global raw-score formula and exact
    legacy reduction are incompatible. Preserve legacy joint-state weighting
    and null-origin fallback; add omission scores to its non-null component.
    """
    w_origin: float = .65
    w_miss: float = .35
    w_omit: float = 1.
    eligible_checks: frozenset[NodeId] | None = None

    def __post_init__(self):
        if any(not math.isfinite(w) or w<0 for w in (self.w_origin,self.w_miss,self.w_omit)):
            raise ValueError('weights must be finite and nonnegative')
        if self.w_origin+self.w_miss<=0: raise ValueError('origin and miss weights cannot both be zero')

    def shares(self,graph,loss_node,posterior,context=None):
        from trust_network.solve.attribution import infer_omission_opportunities
        scale=self.w_origin+self.w_miss
        legacy=Proportional(self.w_miss/scale,self.eligible_checks)
        if self.w_omit==0:
            return legacy.shares(graph,loss_node,posterior)
        if context is None: raise ValueError('omission allocation requires observed path and initial budget')
        null_mass=sum(p for s,p in posterior.mass if s.origin is None)
        if null_mass>=1.: return BearerOnly().shares(graph,loss_node,posterior)
        scores={o:0. for o in graph.organizations}
        for state,p in posterior.mass:
            if state.origin is None: continue
            missed=state.false_negatives
            if self.eligible_checks is not None: missed=missed & self.eligible_checks
            scores[graph.node(state.origin).org]+=p*(self.w_origin if missed else scale)
            for v in missed: scores[graph.node(v).decision_maker]+=p*self.w_miss/len(missed)
        for item in infer_omission_opportunities(graph,context):
            if self.eligible_checks is None or item.node in self.eligible_checks:
                scores[graph.node(item.node).decision_maker]+=self.w_omit*item.omission_weight
        total=sum(scores.values())
        if not total: return BearerOnly().shares(graph,loss_node,posterior)
        weights={o:(1-null_mass)*s/total for o,s in scores.items()}
        weights[graph.node(loss_node).bearer]+=null_mass
        return Shares(tuple(weights.items()))


def allocation_shares(allocation,graph,loss_node,posterior,context=None):
    if isinstance(allocation,ProportionalWithOmission):
        return allocation.shares(graph,loss_node,posterior,context)
    return allocation.shares(graph,loss_node,posterior)
