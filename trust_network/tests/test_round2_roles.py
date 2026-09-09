from dataclasses import replace
import json
from trust_network.scenarios.letter_of_credit import letter_of_credit,role_mismatches,letter_of_credit_ablation,RoleAblationConfig
from trust_network.scenarios.config import load_scenario
from trust_network.solve.decentralized_game import DecentralizedGame,GameConfig


def test_all_eight_mismatches_and_only_one_node_changes(tmp_path):
    g=letter_of_credit(); mismatches=role_mismatches(g)
    assert len(mismatches)==8
    assert {m.node for m in mismatches}=={(base,k) for base in ('export_bank_review','issuing_review') for k in range(4)}
    for item in mismatches:
        for alignment in ('bearer_aligned','fully_aligned'):
            path=tmp_path/f'{item.node[0]}_{item.node[1]}_{alignment}.json'
            path.write_text(json.dumps({'scenario':'letter_of_credit_role_ablation','node':item.node,'alignment':alignment}))
            variant=load_scenario(path)
            assert variant.edges==g.edges and variant.source==g.source
            for old,new in zip(g.nodes,variant.nodes):
                if old.id!=item.node: assert old==new
                else:
                    assert new.bearer==old.decision_maker
                    assert replace(new,bearer=old.bearer,payer=old.payer)==old
                    if alignment=='bearer_aligned': assert new.payer==old.payer
                    else: assert new.payer==new.decision_maker


def test_zero_loss_bearer_mapping_is_payoff_irrelevant():
    original=DecentralizedGame(letter_of_credit(),GameConfig(1.2))
    modified=DecentralizedGame(letter_of_credit_ablation(RoleAblationConfig(('export_bank_review',0),'bearer_aligned')),GameConfig(1.2))
    assert len(original.tree)==len(modified.tree)
    assert all((a.immediate==b.immediate).all() for a,b in zip(original.tree,modified.tree))
