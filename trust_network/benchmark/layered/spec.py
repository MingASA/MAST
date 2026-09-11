from dataclasses import dataclass, asdict, replace
from trust_network.benchmark.contribution.generalization import TOPOLOGIES, build_topology

@dataclass(frozen=True)
class Layer:
    signed: bool
    policy: str = 'autonomous'
    push: bool = False
    facts: bool = False
    recovery: bool = False
    coarse: bool = False

LAYERS = {'L0': Layer(False), 'L1': Layer(True), 'L2': Layer(True, 'verify_all'),
          'L3': Layer(True, 'dependency_closure'),
          'L4': Layer(True, 'dependency_closure', True, True, True)}
LAYERS.update({'L4_no_push': replace(LAYERS['L4'], push=False),
               'L4_no_fact': replace(LAYERS['L4'], facts=False),
               'L4_no_recovery': replace(LAYERS['L4'], recovery=False),
               'L3_coarse': replace(LAYERS['L3'], coarse=True),
               'verify_all': Layer(True, 'verify_all_closure')})
MAIN = ('L0','L1','L2','L3','L4')
CASES = ('active','tampered_handoff','root_retraction','intermediate_retraction',
         'branch_retraction','late_notice','signed_false','conflicting_sources',
         'confirmed_repair','authority_unknown')
LIVE_CASES = ('active','late_notice','confirmed_repair')
AUTHORITIES = {'total_charge': 'source', 'invoice_authorization': 'buyer'}

def matrix():
    for t in TOPOLOGIES:
        for c in CASES:
            for l in MAIN:
                yield t,c,l
        for l,cases in {
            'L4_no_push': ('active','late_notice','intermediate_retraction'),
            'L4_no_fact': ('signed_false','conflicting_sources','confirmed_repair','authority_unknown'),
            'L4_no_recovery': ('confirmed_repair',),
            'L3_coarse': ('intermediate_retraction','branch_retraction'),
            'verify_all': CASES,
        }.items():
            for c in cases:
                yield t,c,l
