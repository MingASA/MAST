"""Online decisions over public views only; no file, network or truth access."""
from dataclasses import dataclass, asdict
import math
from trust_network.core.graph import Node
from trust_network.sim.simulator import bayes

POLICIES=('autonomous','verify_all','risk_aware')


@dataclass(frozen=True)
class RiskConfig:
    change_prior: float = .20
    routine_prior: float = .02
    change_loss: float = 100.
    routine_loss: float = 10.
    verification_cost: float = 3.
    escalation_cost: float = 5.
    budget: float = 9.
    omission_weight: float = 0.
    maximum_unverified_risk: float = .05

    def __post_init__(self):
        for name,value in asdict(self).items():
            if not math.isfinite(value) or value<0: raise ValueError('invalid risk configuration')
        if max(self.change_prior,self.routine_prior,self.maximum_unverified_risk)>1:
            raise ValueError('invalid probability')


@dataclass(frozen=True)
class VisibleContext:
    # Intake class is assigned by the receiving bank's contract configuration,
    # never accepted from a seller assertion, a case filename or the evaluator.
    intake_class: str
    evidence_status: str = 'missing'
    budget_remaining: float = 9.


@dataclass(frozen=True)
class Gate:
    action: str
    reason: str
    prior: float
    posterior: float
    potential_loss: float
    pass_cost: float
    verify_cost: float
    escalation_cost: float
    omission_cost: float
    affordable: bool


def decide(policy: str,view: VisibleContext,config: RiskConfig) -> Gate:
    """Choose allow / request_evidence / escalate before committing an action.

    Reuses the mathematical model's Bayes update. Authority answers are assumed
    correct in this fixture (delta=1, epsilon=0); signatures alone do not imply it.
    Omission is an optional ex-ante cost approximation, not posterior settlement.
    """
    if policy not in POLICIES: raise ValueError('unknown policy')
    if view.intake_class not in ('change_order','routine_order'): raise ValueError('unknown intake class')
    if view.evidence_status not in ('missing','approved','denied','unknown',
                                    'stale_approved','stale_denied','stale_unknown'):
        raise ValueError('invalid evidence status')
    if not math.isfinite(view.budget_remaining) or view.budget_remaining<0: raise ValueError('invalid budget')
    change=view.intake_class=='change_order'
    prior=config.change_prior if change else config.routine_prior
    loss=config.change_loss if change else config.routine_loss
    test=Node('authority_check','verify','buyer_authority',delta=1.,epsilon=0.,mu=0.)
    update=bayes(test,prior)
    posterior=0. if view.evidence_status=='approved' else 1. if view.evidence_status in ('denied','stale_denied') else prior
    affordable=view.budget_remaining+1e-10>=config.verification_cost
    omission=(config.omission_weight*prior*test.delta*loss
              if view.evidence_status=='missing' and affordable else 0.)
    pass_cost=posterior*loss+omission
    verify_cost=(config.verification_cost+update.probability_flag*config.escalation_cost
                 +(1-update.probability_flag)*update.r_clear*loss)
    action='allow'; reason='llm_retains_decision_authority'
    if policy!='autonomous':
        if view.evidence_status in ('denied','unknown'):
            action='escalate'; reason='authority_did_not_confirm_approval'
        elif view.evidence_status=='approved':
            reason='fresh_bound_authority_evidence_reused'
        elif view.evidence_status.startswith('stale_'):
            action='request_evidence' if affordable else 'escalate'
            reason='refresh_previously_observed_evidence' if affordable else 'stale_evidence_requires_escalation'
        elif policy=='verify_all':
            action='request_evidence' if affordable else 'escalate'
            reason='mandatory_authority_check' if affordable else 'mandatory_check_unaffordable'
        else:
            choices=[(config.escalation_cost,2,'escalate')]
            if prior<=config.maximum_unverified_risk: choices.append((pass_cost,0,'allow'))
            if affordable: choices.append((verify_cost,1,'request_evidence'))
            action=min(choices)[2]
            reason={'allow':'accepted_residual_risk_below_check_cost',
                    'request_evidence':'verification_minimizes_estimated_cost',
                    'escalate':'risk_limit_or_cost_requires_escalation'}[action]
    return Gate(action,reason,prior,posterior,loss,pass_cost,verify_cost,
                config.escalation_cost,omission,affordable)
