"""Public workload and experimental factors. Truth is produced by the injector."""
from dataclasses import dataclass,asdict
from trust_network.benchmark.containment import fixture,AUTHORITIES,OWNERS

@dataclass(frozen=True)
class Arm:
    policy:str
    threshold:float=1
    push:bool=False
    bound_recovery:bool=True

ARMS={
    'autonomous':Arm('autonomous'),
    'root_gate':Arm('verify_all'),
    'simple_dependency_gate':Arm('verify_all_closure'),
    'dependency':Arm('dependency_closure'),
    'dependency_push':Arm('dependency_closure',push=True),
    'verify_all':Arm('verify_all_closure'),
    'selective':Arm('dependency_closure',threshold=2),
    'recovery_ablation':Arm('dependency_closure',push=True,bound_recovery=False),
}
CASES=('active','root_retraction','intermediate_retraction','branch_retraction',
       'late_notice','derived_error','missing_dependency','conflicting_sources',
       'signed_false','bad_recovery_binding','recovery_retraction')
ROLES={'source':'供应商费用声明服务','buyer':'买方授权服务','coordinator':'跨组织费用协调员',
       'middle_a':'物流审核组织A','middle_b':'物流审核组织B',
       'receiver_a':'结算组织A','receiver_b':'结算组织B'}


def workload(seed=0):
    # Independent of case and arm: identical public problem and signing keys.
    return fixture('active',seed=seed)


def config(owner,public,workflow,arm):
    return {'owner':owner,'public_keys':public,'workflow':workflow,'authorities':AUTHORITIES,
        'recovery_receivers':['receiver_a','receiver_b'],
        'reliability':{'policy':arm.policy,'propagation_threshold':arm.threshold},
        'model_max_tokens':2048}


def dossier(owner):
    return (f'你代表独立组织：{ROLES[owner]}。你的内部工作手册：核对本组织收到的证据，'
        '发现证据缺失、过期或矛盾时可以要求核验或暂停；资料充分时应继续完成任务。'
        '订单A和C相互独立，不得因A的问题暂停C。对其他组织的私有数据库不可见。'
        '费用以整数分和CNY表达；没有明确批准不得把审核意见当作付款。')


def factors():return {name:asdict(arm) for name,arm in ARMS.items()}
