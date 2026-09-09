"""Exact finite extensive-form best responses with imperfect information.

Each organization has perfect recall of its own checks. Cross-organization
records are hidden in protocol 0 and visible in 1/2. The shared remaining budget
and route are public. An audit sees all records for ex-post settlement. The tree
retains full origin/F distributions; no organization reads hidden truth.
"""
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Literal
import math
import numpy as np
from trust_network.core.graph import Graph
from trust_network.sim.simulator import Discovery
from trust_network.solve.attribution import Latent, Posterior, Check, physical_transition, check_transition, ResponsibilityContext, Observation
from trust_network.solve.settlement import Proportional, BearerOnly, Allocation, allocation_shares

ProtocolName = Literal['black_box','certificate','verified_certificate']
PROTOCOLS=('black_box','certificate','verified_certificate')


@dataclass(frozen=True)
class GameConfig:
    budget: float = 2.
    protocol: ProtocolName = 'black_box'
    objective: Literal['selfish','resp'] = 'resp'
    max_rounds: int = 50
    max_tree_nodes: int = 250000
    discovery: Discovery = Discovery()
    missed_weight: float = .35
    allocation: Allocation | None = None

    def __post_init__(self):
        if self.protocol not in PROTOCOLS or self.objective not in ('selfish','resp'):
            raise ValueError('invalid game mode')
        if self.budget < 0 or self.max_rounds < 1: raise ValueError('invalid budget or rounds')


@dataclass
class TreeNode:
    actor: str | None = None
    information: tuple | None = None
    children: list[tuple[float,int]] = field(default_factory=list)
    immediate: np.ndarray | None = None
    verification_count: float = 0.


@dataclass(frozen=True)
class GameResult:
    converged: bool
    rounds: int
    social: float
    net: tuple[tuple[str,float],...]
    strategy: tuple[tuple[tuple,int],...]
    oscillation: tuple[tuple[int,...],...]
    exploitability: float
    tree_nodes: int


@dataclass
class DecentralizedGame:
    graph: Graph
    config: GameConfig = GameConfig()
    tree: list[TreeNode] = field(default_factory=list,init=False,repr=False)
    information_sets: dict = field(default_factory=dict,init=False,repr=False)

    def __post_init__(self):
        self.graph.topological()
        self.orgs=self.graph.organizations
        self.allocation=(self.config.allocation if self.config.allocation is not None else Proportional(self.config.missed_weight)) if self.config.objective=='resp' else BearerOnly()
        self._enter(self.graph.source,self.config.budget,((Latent(),1.),),(),0.)
        self.keys=tuple(self.information_sets)

    def _append(self, actor=None, information=None, immediate=None):
        if len(self.tree)>=self.config.max_tree_nodes:
            raise RuntimeError('exact game tree exceeds configured limit; reduce graph/budget')
        index=len(self.tree)
        self.tree.append(TreeNode(actor,information,[],np.zeros(len(self.orgs)) if immediate is None else immediate))
        if actor is not None: self.information_sets.setdefault(information,[]).append(index)
        return index

    def _information(self,node,budget,history):
        actor=node.decision_maker
        visible=tuple((h.node,h.verified,h.signal) if self.config.protocol!='black_box' or self.graph.node(h.node).decision_maker==actor else (h.node,None,None) for h in history)
        return actor,node.id,round(budget,10),visible

    @staticmethod
    def _transform(mass, transform):
        output=defaultdict(float)
        for state,weight in mass:
            for new,prob in transform(state): output[new]+=weight*prob
        total=sum(output.values())
        return total,tuple((s,w/total) for s,w in output.items() if w>0) if total else ()

    def _enter(self,v,budget,mass,history,p):
        node=self.graph.node(v)
        _,before=self._transform(mass,lambda s:physical_transition(s,node,p))
        if node.type=='verify' and self.graph.outgoing(v) and budget+1e-10>=node.c+node.c_fix:
            index=self._append(node.decision_maker,self._information(node,budget,history))
            skip=self._after(v,budget,before,history+(Check(v),),0.)
            call=self._append()
            self.tree[call].verification_count=1.
            self.tree[index].children=[(1.,skip),(1.,call)]
            for signal in ('flag','clear'):
                check=Check(v,True,signal)
                prob,after=self._transform(before,lambda s:check_transition(s,node,check))
                if prob:
                    spent=node.c+(node.c_fix if signal=='flag' else 0.)
                    cost=spent+(node.F if signal=='flag' else 0.)
                    child=self._after(v,max(0,budget-spent),after,history+(check,),cost)
                    self.tree[call].children.append((prob,child))
            return index
        return self._after(v,budget,before,history+(Check(v),),0.)

    def _loss_cost(self,node,mass,terminal,history):
        out=np.zeros(len(self.orgs))
        if not node.L: return out
        if node.forced_penalty:
            out[self.orgs.index(node.bearer)]=node.L
            return out
        signals=('flag','clear') if terminal else (None,)
        for signal in signals:
            weighted=[]
            for state,p in mass:
                pf=self.config.discovery.delta if state.origin is not None else self.config.discovery.epsilon
                likelihood=1. if signal is None else pf if signal=='flag' else 1-pf
                if p*likelihood: weighted.append((state,p*likelihood))
            prob=sum(p for _,p in weighted)
            if not prob: continue
            posterior=Posterior(tuple((s,p/prob) for s,p in weighted))
            corrupted=sum(p for s,p in weighted if s.origin is not None)
            context=ResponsibilityContext(Observation(history,signal or 'flag'),self.config.budget,self.config.discovery if terminal else Discovery(.5,.5))
            shares=allocation_shares(self.allocation,self.graph,node.id,posterior,context)
            for org,share in shares.amounts: out[self.orgs.index(org)]+=node.L*corrupted*share
        return out

    def _after(self,v,budget,mass,history,cost):
        node=self.graph.node(v); edges=self.graph.outgoing(v)
        immediate=self._loss_cost(node,mass,not edges,history)
        immediate[self.orgs.index(node.payer)]+=cost
        index=self._append(immediate=immediate)
        for edge in edges:
            if edge.q_uv:
                child=self._enter(edge.v,budget,mass,history,edge.p_uv)
                self.tree[index].children.append((edge.q_uv,child))
        return index

    def evaluate(self,strategy):
        values=np.zeros((len(self.tree),len(self.orgs)))
        for index in range(len(self.tree)-1,-1,-1):
            node=self.tree[index]
            values[index]=node.immediate
            if node.actor is not None:
                values[index]+=values[node.children[strategy.get(node.information,0)][1]]
            else:
                for prob,child in node.children: values[index]+=prob*values[child]
        return values[0]

    def best_response(self,org,strategy):
        """Backward local DP on perfect-recall information sets.

        Counterfactual reach excludes the responding player's own actions, so
        hidden chance/opponent histories sharing an information set are averaged
        with their correct conditional weights. No truth is exposed to policies.
        """
        reach=np.zeros(len(self.tree)); reach[0]=1.
        for index,node in enumerate(self.tree):
            if node.actor is None:
                for prob,child in node.children: reach[child]+=reach[index]*prob
            elif node.actor==org:
                for _,child in node.children: reach[child]+=reach[index]
            else:
                reach[node.children[strategy.get(node.information,0)][1]]+=reach[index]
        result=dict(strategy); values=np.zeros(len(self.tree)); component=self.orgs.index(org)
        # DFS preorder ensures every child index exceeds its parent. Members of
        # an information set can be interleaved: recursively solve dependencies.
        done=set(); solved=set()
        def visit(index):
            if index in done: return values[index]
            node=self.tree[index]
            if node.actor==org:
                key=node.information
                if key not in solved:
                    members=self.information_sets[key]
                    scores=np.zeros(2)
                    for member in members:
                        for action,(_,child) in enumerate(self.tree[member].children):
                            scores[action]+=reach[member]*visit(child)
                    old=result.get(key,0)
                    action=old if scores[old] <= min(scores)+1e-10 else int(np.argmin(scores))
                    result[key]=action; solved.add(key)
                    for member in members:
                        values[member]=self.tree[member].immediate[component]+visit(self.tree[member].children[action][1])
                        done.add(member)
            else:
                value=node.immediate[component]
                if node.actor is None:
                    value+=sum(prob*visit(child) for prob,child in node.children)
                else: value+=visit(node.children[result.get(node.information,0)][1])
                values[index]=value; done.add(index)
            return values[index]
        visit(0)
        return result,float(values[0])

    def solve(self,initial=None):
        strategy={} if initial is None else dict(initial)
        signatures=[tuple(strategy.get(k,0) for k in self.keys)]; seen={signatures[0]:0}
        converged=False; oscillation=()
        for round_index in range(1,self.config.max_rounds+1):
            before=signatures[-1]
            for org in self.orgs: strategy,_=self.best_response(org,strategy)
            signature=tuple(strategy.get(k,0) for k in self.keys)
            signatures.append(signature)
            if signature==before:
                converged=True; break
            if signature in seen:
                oscillation=tuple(signatures[seen[signature]:]); break
            seen[signature]=len(signatures)-1
        net=self.evaluate(strategy)
        exploitability=max((float(net[i])-self.best_response(org,strategy)[1] for i,org in enumerate(self.orgs)),default=0.)
        return GameResult(converged,round_index,float(sum(net)),tuple(zip(self.orgs,map(float,net))),
                          tuple(strategy.items()),oscillation,max(0.,exploitability),len(self.tree))


def price_of_anarchy(equilibrium: float, optimum: float) -> float:
    if optimum < 0 or equilibrium < 0: raise ValueError('negative cost')
    return equilibrium/optimum if optimum else (1. if equilibrium==0 else math.inf)
