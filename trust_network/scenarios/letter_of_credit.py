"""Synthetic documentary-credit workflow baseline, not legal/financial advice.

Routing here is deliberately exogenous. The document demo implements conditional
resubmission independently; a paper DP must not claim those are the same model.
"""
from dataclasses import dataclass
from trust_network.core.graph import Graph,Node,Edge
from trust_network.core.unroll import unroll


@dataclass(frozen=True)
class LetterOfCreditConfig:
    K_max: int = 3
    resubmit_probability: float = .12
    termination_loss: float = 15.
    insurance: bool = False


def letter_of_credit(config: LetterOfCreditConfig = LetterOfCreditConfig()) -> Graph:
    # All probabilities and costs below are synthetic research parameters.
    nodes=[Node('seller_documents','process','seller',alpha=.12),
           Node('freight_booking','process','freight_forwarder',alpha=.05),
           Node('export_declaration','process','customs_export',alpha=.025),
           Node('export_bank_review','verify','advising_bank',c=.4,delta=.85,epsilon=.03,mu=.9,c_fix=.1,F=.08,payer='seller',bearer='buyer'),
           Node('issuing_review','verify','issuing_bank',c=.5,delta=.9,epsilon=.025,mu=.9,c_fix=.1,F=.08,bearer='buyer'),
           Node('seller_revision','process','seller',alpha=.03),
           Node('import_clearance','process','customs_import',alpha=.02),
           Node('buyer_receipt','process','buyer',L=25)]
    r=config.resubmit_probability
    if not 0<=r<1: raise ValueError('resubmit probability must be in [0,1)')
    edges=[Edge('seller_documents','freight_booking'),Edge('freight_booking','export_declaration',1,.95),
           Edge('export_declaration','export_bank_review'),Edge('export_bank_review','issuing_review'),
           Edge('issuing_review','seller_revision',r),Edge('issuing_review','import_clearance',1-r),
           Edge('seller_revision','seller_documents',resubmit=True),Edge('import_clearance','buyer_receipt',1,.95)]
    if config.insurance:
        nodes.extend((Node('claim','process','buyer',alpha=.01),Node('insurer_review','verify','insurer',c=.3,delta=.8,mu=.8),Node('claim_outcome','process','buyer',L=5),Node('closed','process','buyer')))
        edges.extend((Edge('buyer_receipt','claim',.15),Edge('buyer_receipt','closed',.85),Edge('claim','insurer_review'),Edge('insurer_review','claim_outcome')))
    return unroll(Graph(tuple(nodes),tuple(edges),'seller_documents'),config.K_max,config.termination_loss)


@dataclass(frozen=True)
class RoleMismatch:
    node: tuple
    decision_maker: str
    payer: str
    bearer: str
    loss: float


def role_mismatches(graph: Graph) -> tuple[RoleMismatch,...]:
    """Enumerate every expanded node, not just the two underlying base roles."""
    return tuple(RoleMismatch(n.id,n.decision_maker,n.payer,n.bearer,n.L)
                 for n in graph.nodes if n.decision_maker != n.bearer)


@dataclass(frozen=True)
class RoleAblationConfig:
    node: tuple
    alignment: str = 'baseline'
    scenario: LetterOfCreditConfig = LetterOfCreditConfig()


def letter_of_credit_ablation(config: RoleAblationConfig) -> Graph:
    from dataclasses import replace
    graph=letter_of_credit(config.scenario)
    target=graph.node(config.node)
    if config.alignment not in ('baseline','bearer_aligned','fully_aligned'):
        raise ValueError('unknown role alignment')
    changed=target
    if config.alignment=='bearer_aligned': changed=replace(target,bearer=target.decision_maker)
    if config.alignment=='fully_aligned': changed=replace(target,payer=target.decision_maker,bearer=target.decision_maker)
    return Graph(tuple(changed if n.id==target.id else n for n in graph.nodes),graph.edges,graph.source)
