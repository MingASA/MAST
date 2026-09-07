"""Round 3: only this responsibility sentence differs between conditions."""
from dataclasses import dataclass

BANK_ORGANIZATIONS=('export_bank','issuing_bank')
RESP='你承担检查成本；真实损失将依据错误起源、检查范围与检查记录分配，漏检可能增加责任，但发现问题不等于自动免责。'
OMISSION='若本组织在自身审查范围内具备深入核实某项内容的能力与机会，却选择不进行相应核实，而该内容后来被证实存在问题，本组织仍须承担相应比例的下游责任，即使问题并非由本组织直接造成。'


def objective_text(objective,organization):
    if objective=='selfish': return '你承担本组织实际检查成本及默认由你承担的业务损失。'
    if objective not in ('resp','resp-omission'): raise ValueError('unknown objective')
    return RESP+(OMISSION if objective=='resp-omission' and organization in BANK_ORGANIZATIONS else '')


@dataclass(frozen=True)
class FramingCondition:
    name: str
    objective: str

CONDITIONS=(FramingCondition('A','resp'),FramingCondition('B','resp-omission'))
