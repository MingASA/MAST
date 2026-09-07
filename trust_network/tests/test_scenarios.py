from trust_network.scenarios.synthetic import synthetic_random
from trust_network.scenarios.letter_of_credit import letter_of_credit
from trust_network.scenarios.config import load_scenario


def test_scenarios_and_config(tmp_path):
    for g in (synthetic_random(),letter_of_credit()):
        assert g.topological()
    g=letter_of_credit()
    assert ('seller_documents',3) in g.nx
    assert any(n.forced_penalty for n in g.nodes)
    assert g.node(('export_bank_review',0)).decision_maker != g.node(('export_bank_review',0)).bearer
    path=tmp_path/'config.json'; path.write_text('{"scenario":"synthetic_random","seed":2}')
    assert load_scenario(path).source=='source'
