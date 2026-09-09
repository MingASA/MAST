"""V2 grid Bellman solver and independent V1 exact piecewise-linear baseline."""
from dataclasses import dataclass, field
import numpy as np
from trust_network.core.graph import Graph, NodeId
from trust_network.sim.simulator import DecisionContext, bayes, phi


@dataclass(frozen=True)
class DPConfig:
    budget: float = 3.0
    grid_size: int = 101

    def __post_init__(self):
        if self.budget < 0 or not np.isfinite(self.budget) or self.grid_size < 2:
            raise ValueError("invalid DP configuration")


@dataclass
class GlobalDP:
    graph: Graph
    config: DPConfig = DPConfig()
    grid: np.ndarray = field(init=False, repr=False)
    tables: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        self.graph.topological()
        self.grid = np.linspace(0, 1, self.config.grid_size)
        # Dependencies are evaluated backwards over the acyclic workflow;
        # reachable real-valued budgets are memoized, never rounded to integers.
        for v in reversed(self.graph.topological()):
            self.table(v, self.config.budget)

    def continuation(self, v, b, r):
        out = np.zeros_like(r, dtype=float)
        for edge in self.graph.outgoing(v):
            node = self.graph.node(edge.v)
            out += edge.q_uv * np.interp(phi(node, edge.p_uv, r), self.grid, self.table(edge.v, b))
        return out

    def q_values(self, v, b, r):
        node = self.graph.node(v)
        loss = node.L * (np.ones_like(r) if node.forced_penalty else r)
        passed = loss + self.continuation(v, b, r)
        checked = np.full_like(r, np.inf, dtype=float)
        if node.type == 'verify' and self.graph.outgoing(v) and b + 1e-10 >= node.c + node.c_fix:
            pf = node.delta * r + node.epsilon * (1-r)
            rf = np.divide(node.delta*r, pf, out=np.zeros_like(r), where=pf > 0) * (1-node.mu)
            rc = np.divide((1-node.delta)*r, 1-pf, out=np.zeros_like(r), where=pf < 1)
            checked = node.c + pf * (node.F + node.c_fix + node.L*rf + self.continuation(v, max(0,b-node.c-node.c_fix), rf))
            checked += (1-pf) * (node.L*rc + self.continuation(v, max(0,b-node.c), rc))
        return passed, checked

    def table(self, v, b):
        if b < -1e-9:
            raise ValueError('negative budget')
        key = (v, round(b, 10))
        if key not in self.tables:
            self.tables[key] = np.minimum(*self.q_values(v, b, self.grid))
        return self.tables[key]

    def value(self, v=None, b=None, r=None):
        v = self.graph.source if v is None else v
        b = self.config.budget if b is None else b
        r = self.graph.node(v).alpha if r is None else r
        if not 0 <= r <= 1:
            raise ValueError('belief outside [0,1]')
        return float(np.interp(r, self.grid, self.table(v,b)))

    def verify(self, context: DecisionContext) -> bool:
        passed, checked = self.q_values(context.node, context.budget, np.asarray([context.belief.r]))
        return bool(checked[0] < passed[0] - 1e-10)

    def threshold(self, v, b):
        passed, checked = self.q_values(v,b,self.grid)
        selected = self.grid[checked < passed-1e-10]
        return float(selected[0]) if len(selected) else float('inf')


@dataclass(frozen=True)
class Piecewise:
    knots: tuple[float, ...]
    values: tuple[float, ...]

    def __call__(self, r):
        return np.interp(r, self.knots, self.values)


@dataclass
class PerfectBaseline:
    """Exact continuous-r Bellman functions; no numerical grid is used."""
    graph: Graph
    tables: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        self.graph.topological()
        for n in self.graph.nodes:
            if n.type == 'verify' and (n.delta != 1 or n.mu != 1 or n.epsilon or n.F or n.c_fix):
                raise ValueError('V1 requires perfect detection/repair and zero flag costs')

    def function(self, v: NodeId, b: float) -> Piecewise:
        key = (v, round(b,10))
        if key in self.tables:
            return self.tables[key]
        node = self.graph.node(v)
        edges = self.graph.outgoing(v)
        knots = {0.,1.}
        for e in edges:
            child = self.graph.node(e.v)
            scale = (1-child.alpha)*e.p_uv
            if scale:
                knots.update((x-child.alpha)/scale for x in self.function(e.v,b).knots if 0 < (x-child.alpha)/scale < 1)
        x = sorted(knots)
        y = [node.L*(1 if node.forced_penalty else r) + sum(e.q_uv*float(self.function(e.v,b)(phi(self.graph.node(e.v), e.p_uv,r))) for e in edges) for r in x]
        if node.type == 'verify' and edges and b + 1e-10 >= node.c:
            check = node.c + sum(e.q_uv*float(self.function(e.v,max(0,b-node.c))(self.graph.node(e.v).alpha)) for e in edges)
            for a,z,ya,yz in zip(x[:-1],x[1:],y[:-1],y[1:]):
                if (ya-check)*(yz-check) < 0:
                    knots.add(a+(z-a)*(check-ya)/(yz-ya))
            xx = sorted(knots)
            yy = np.minimum(np.interp(xx,x,y),check)
            x,y = xx,yy
        result = Piecewise(tuple(x),tuple(float(t) for t in y))
        self.tables[key] = result
        return result

    def value(self, v, b, r):
        return float(self.function(v,b)(r))

    def threshold(self,v,b):
        node = self.graph.node(v)
        if node.type != 'verify' or not self.graph.outgoing(v) or b < node.c:
            return float('inf')
        check = node.c + sum(e.q_uv*self.value(e.v,b-node.c,self.graph.node(e.v).alpha) for e in self.graph.outgoing(v))
        def passed(r):
            return node.L*r + sum(e.q_uv*self.value(e.v,b,phi(self.graph.node(e.v),e.p_uv,r)) for e in self.graph.outgoing(v))
        if passed(1) <= check:
            return float('inf')
        lo,hi = 0.,1.
        for _ in range(60):
            mid=(lo+hi)/2
            if passed(mid) > check: hi=mid
            else: lo=mid
        return hi
