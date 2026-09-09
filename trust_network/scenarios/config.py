"""JSON configuration loader; public solver boundaries use dataclasses."""
import json
from pathlib import Path
from .synthetic import SyntheticConfig,synthetic_random
from .letter_of_credit import LetterOfCreditConfig,letter_of_credit,RoleAblationConfig,letter_of_credit_ablation


def load_scenario(path: str | Path):
    raw=json.loads(Path(path).read_text())
    kind=raw.pop('scenario')
    if kind=='synthetic_random': return synthetic_random(SyntheticConfig(**raw))
    if kind=='letter_of_credit': return letter_of_credit(LetterOfCreditConfig(**raw))
    if kind=='letter_of_credit_role_ablation':
        return letter_of_credit_ablation(RoleAblationConfig(tuple(raw['node']),raw['alignment'],LetterOfCreditConfig(**raw.get('parameters',{}))))
    raise ValueError('unknown scenario')
