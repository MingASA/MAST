"""Expected executed checks, not number of verify nodes or budget spent."""
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class PlannerMetrics:
    social_cost: float
    expected_checks: float


def expected_checks(game,strategy) -> float:
    values=np.zeros(len(game.tree))
    for i in range(len(game.tree)-1,-1,-1):
        node=game.tree[i]; values[i]=node.verification_count
        if node.actor is not None: values[i]+=values[node.children[strategy.get(node.information,0)][1]]
        else: values[i]+=sum(p*values[c] for p,c in node.children)
    return float(values[0])


def planner_metrics(game) -> PlannerMetrics:
    costs=np.zeros(len(game.tree)); counts=np.zeros(len(game.tree))
    for i in range(len(game.tree)-1,-1,-1):
        node=game.tree[i]; costs[i]=sum(node.immediate); counts[i]=node.verification_count
        if node.actor is not None:
            minimum=min(costs[c] for _,c in node.children)
            candidates=[c for _,c in node.children if costs[c]<=minimum+1e-10]
            chosen=min(candidates,key=lambda c:counts[c])
            costs[i]+=costs[chosen]; counts[i]+=counts[chosen]
        else:
            costs[i]+=sum(p*costs[c] for p,c in node.children)
            counts[i]+=sum(p*counts[c] for p,c in node.children)
    return PlannerMetrics(float(costs[0]),float(counts[0]))


def over_check_ratio(equilibrium_checks: float, optimal_checks: float) -> float:
    if equilibrium_checks<0 or optimal_checks<0: raise ValueError('negative count')
    if optimal_checks==0: return 1. if equilibrium_checks==0 else math.inf
    return equilibrium_checks/optimal_checks
