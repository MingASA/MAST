"""Local, signed stage readiness. A snapshot is never a business capability."""
from trust_network.demo.claim_channel import issue
from trust_network.demo.documents import digest
from trust_network.demo.recovery_frontier import frontier

STAGE_SEMANTICS={
    'proceed':'仅提议生成派生证据；本地父证据可用且符合规则即可，不要求先获业务执行许可。',
    'verify':'只请求权威核验并返回证据；无论核验是否成功，都不执行批准或转发。',
    'approve':'显式请求账单批准；运行时仍须检查业务合约及策略要求的新鲜度。',
    'forward':'显式请求转发；运行时仍须检查其依赖。',
    'hold':'不提议动作，也不隐式发起核验。'}


def stage_status(gateway,phase,claims,rebuild_scope=None,receiver=None):
    if phase not in ('derive','decide_action'): raise ValueError('unknown stage')
    if not isinstance(claims,list) or not all(isinstance(c,str) for c in claims): raise ValueError('invalid stage claims')
    claims=list(dict.fromkeys(claims))
    missing=[c for c in claims if c not in gateway.claims]
    blocked={c:gateway.blockers(c) for c in claims if gateway.blockers(c)}
    ready=bool(claims) and not missing and not blocked
    binding=False; reasons=[]
    if rebuild_scope is not None:
        if phase!='derive' or receiver is None: raise ValueError('missing local recovery trust configuration')
        try:
            state=frontier(gateway,rebuild_scope['envelope'],rebuild_scope['task_id'],rebuild_scope['completed'],receiver)
            match=[n for n in state['ready'] if n['old']==rebuild_scope['old'] and n['issuer']==gateway.owner and n['parents']==claims]
            binding=len(match)==1;ready=ready and binding
            if not binding:reasons.append('not_in_this_issuer_frontier')
        except (ValueError,KeyError):
            ready=False;reasons.append('recovery_binding_invalid')
    body={'kind':'stage_readiness','version':1,'workflow':gateway.workflow,'phase':phase,
          'claims':claims,'missing':missing,'blocked':blocked,'reasons':reasons,
          'local_parent_checks_passed':ready,'task_binding_verified':binding,
          'may_propose_derivation':phase=='derive' and ready,
          'may_request_verification':phase=='decide_action',
          'may_submit_explicit_action':phase=='decide_action' and ready,
          'business_execution_authorized':False,
          'freshness_scope':'后续业务动作；不阻止依据本地合法父证据提议重建',
          'future_write_checks_required':True,'semantics':STAGE_SEMANTICS}
    packet=issue(gateway.owner,gateway.key,body)
    gateway.record('stage_readiness_reported',digest(packet))
    return packet
