"""Synthetic archive-format fixtures; these tests do not claim live execution."""
import copy
import pytest
from trust_network.benchmark.contribution.freeze import provision
from trust_network.benchmark.contribution.forensics import audit, project, signed_artifacts
from trust_network.benchmark.contribution.live_replay import import_trace, score_reference
from trust_network.demo.network_reliability import run_batch, ReliabilityConfig
from trust_network.demo.documents import digest


def archive():
    f, nodes, routes = provision()
    g = nodes['receiver_a']
    packet = run_batch(g, [{'id': 'actual-action', 'operation': 'forward',
                           'claims': [digest(f['trace']['A']['middle_a'])]}],
                       lambda *_: pytest.fail('no remote query'), lambda _: None,
                       ReliabilityConfig(policy='autonomous'))
    events = []
    def append(kind, **fields):
        events.append({'kind': kind, 'sequence': len(events),
                       'previous': digest(events[-1]) if events else None, **fields})
    for r in routes:
        append('handoff_registered', packet=r['handoff'], receipt=r['receipt'])
    for owner, node in nodes.items():
        append('worker_exchange', owner=owner, response={'events': node.events})
    return {'mode': 'live', 'arm': 'test-format-only', 'case': 'active',
            'public_keys': f['public'], 'packets': {cid: p for n in nodes.values() for cid, p in n.claims.items()},
            'batches': [packet], 'events': events, 'model_calls': 0, 'effects_are_simulated': True}


def test_original_batches_preserved_and_no_fabricated_duty_labels():
    raw = archive()
    before = copy.deepcopy(raw)
    e = import_trace(raw)
    assert e['observation']['batches'] == raw['batches']
    assert not e['observation']['uses']
    for view in ('full', 'no_receipts', 'ordinary_logs', 'opaque_relay'):
        o = project(e, view)
        a = audit(o)
        m = score_reference(e, o, a)
        assert m['verified_routes']['expected'] == 10
        assert m['verified_routes']['matched'] == (10 if view == 'full' else 0)
        assert m['duty_accuracy'] is None
        assert m['undetermined'] == 1
        if view in ('ordinary_logs', 'opaque_relay'):
            assert list(signed_artifacts(o)) == []
    assert raw == before


def test_archive_corruption_rejected():
    raw = archive()
    raw['events'][0]['previous'] = 'bad'
    with pytest.raises(ValueError, match='archive chain'):
        import_trace(raw)
    raw = archive()
    raw['batches'][0]['body']['outputs'][0]['action'] = 'BLOCKED'
    with pytest.raises(ValueError, match='signature'):
        import_trace(raw)


def test_batch_evidence_projection_does_not_leak_nested_receipt():
    raw = archive()
    # Original signed batches remain indivisible; construct a fixture envelope
    # with a nested receipt to test projection independently of signature audit.
    e = import_trace(raw)
    e['observation']['batches'][0]['body']['extra'] = e['observation']['receipts'][0]
    o = project(e, 'no_receipts')
    assert o['batches'] == []
    assert not any(p['body'].get('kind') == 'handoff_receipt' for p in signed_artifacts(o))


def test_reorder_invariant_and_live_bound_head_removed():
    e = import_trace(archive())
    full, reordered = project(e), project(e, fault='reorder')
    assert score_reference(e, full, audit(full)) == score_reference(e, reordered, audit(reordered))
    missing = project(e, fault='missing_link')
    assert len(missing['events']) < len(full['events'])
    assert all(v == 'undetermined' for v in audit(missing)['findings'].values())


def test_signed_batch_positive_requires_owner_order_and_action_binding():
    from trust_network.demo.claim_channel import issue
    f, nodes, _ = provision()
    g = nodes['receiver_a']
    original = f['trace']['A']['coordinator']
    g.receive(issue('coordinator', f['keys']['coordinator'],
                    {'kind': 'revoke', 'workflow': f['workflow'],
                     'target': digest(original), 'original': original}))
    proposal = {'id': 'deliberate-violation', 'operation': 'forward',
                'claims': [digest(f['trace']['A']['middle_a'])]}
    head = g.record('reliability_outcome', digest(proposal), ['COMPLETED'])
    plan = issue(g.owner, g.key, {'kind': 'reliability_plan', 'workflow': f['workflow'],
                                'proposals': [proposal]})
    batch = issue(g.owner, g.key, {'kind': 'reliability_batch', 'workflow': f['workflow'],
                                  'plan': plan, 'outputs': [{'proposal': proposal['id'],
                                      'action': 'COMPLETED', 'local_head': digest(head)}]})
    raw = archive()
    raw['batches'] = [batch]
    # This is an explicitly malicious fixture action, not an enforced run_batch.
    raw['events'].append({'kind': 'worker_exchange', 'owner': g.owner,
                          'response': {'events': g.events}, 'sequence': len(raw['events']),
                          'previous': digest(raw['events'][-1])})
    e = import_trace(raw)
    assert list(audit(project(e))['findings'].values()) == ['violation']
    assert list(audit(project(e, fault='missing_link'))['findings'].values()) == ['undetermined']
    assert list(audit(project(e, fault='missing_notice'))['findings'].values()) == ['undetermined']
