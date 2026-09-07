"""Small seeded branching graphs for exact extensive-form experiments."""
from dataclasses import dataclass
import numpy as np
from trust_network.core.graph import Graph,Node,Edge


@dataclass(frozen=True)
class SyntheticConfig:
    seed: int = 7
    stages: int = 2
    organizations: int = 3
    boundary_density: float = .7
    heterogeneity: float = .5


def synthetic_random(config: SyntheticConfig = SyntheticConfig()) -> Graph:
    if config.stages<1 or config.organizations<1 or not 0<=config.boundary_density<=1 or not 0<=config.heterogeneity<=1:
        raise ValueError('invalid synthetic configuration')
    rng=np.random.default_rng(config.seed)
    orgs=tuple(f'org_{i}' for i in range(config.organizations))
    nodes=[Node('source','process',orgs[0],alpha=.15)]
    edges=[]; prev='source'; owner=0
    for i in range(config.stages):
        if rng.random()<config.boundary_density: owner=(owner+1)%len(orgs)
        alpha=float(.04+config.heterogeneity*rng.uniform(0,.12))
        process=Node(f'p{i}','process',orgs[owner],alpha=alpha)
        check=Node(f'v{i}','verify',orgs[owner],c=.3,delta=.85,epsilon=.04,mu=.9,c_fix=.1,F=.05,bearer=orgs[-1])
        nodes.extend((process,check)); edges.extend((Edge(prev,process.id,1,float(.85+rng.uniform(0,.15))),Edge(process.id,check.id)))
        prev=check.id
    nodes.extend((Node('loss','process',orgs[-1],L=15),Node('alternate_loss','process',orgs[-1],alpha=.02,L=8)))
    edges.extend((Edge(prev,'loss',.8,.95),Edge(prev,'alternate_loss',.2,.8)))
    return Graph(tuple(nodes),tuple(edges),'source')
