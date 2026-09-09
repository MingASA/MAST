import pytest
from trust_network.demo.documents import keypair
from trust_network.demo.negotiation import attest
from trust_network.demo.negotiation_scenario import PRIVATE
from trust_network.demo.reservations import ReservationStore
from trust_network.demo.resource_protocol import ResourceParticipant, ResourceCoordinator
from trust_network.tests.test_negotiation import split_plan
from trust_network.demo.negotiation_worker import sign
from trust_network.demo.resource_protocol import execute_resource_plan


def setup(tmp_path):
    keys = {o: keypair() for o in ('supplier', 'carrier', 'buyer', 'coordinator')}
    public = {o: k[1] for o, k in keys.items()}
    participants = {o: ResourceParticipant(ReservationStore(tmp_path/(o+'.sqlite'), o, PRIVATE[o]),
                    keys[o][0], public['coordinator']) for o in ('supplier', 'carrier')}
    coordinator = ResourceCoordinator(tmp_path/'coordinator.sqlite', keys['coordinator'][0], public)
    plan = split_plan()
    buyer = attest('buyer', PRIVATE['buyer'], plan, 'workflow', 1, keys['buyer'][0], 100)
    coordinator.test_intent = sign('buyer', keys['buyer'][0], {'organization': 'buyer',
        'workflow_id': 'workflow', 'content': {'action': 'propose', 'plan': plan}})
    return participants, coordinator, plan, buyer


def test_partial_commit_recovers_after_original_hold_expiry(tmp_path):
    participants, coordinator, plan, buyer = setup(tmp_path)
    votes = {o: p.prepare(plan, 100) for o, p in participants.items()}
    decision = coordinator.decide(plan, votes, buyer, 'workflow', 101, buyer_decision=coordinator.test_intent)
    ack = participants['supplier'].decide(plan, decision, 102)
    coordinator.acknowledge(plan['transaction'], 'supplier', ack)
    assert coordinator.status(plan['transaction']) == 'recovery_pending'
    # Simulated carrier outage + coordinator restart. Prepared is NOT a lease.
    restarted = ResourceCoordinator(coordinator.path, coordinator.key, coordinator.public_keys)
    persisted = restarted.recover(plan['transaction'])
    for owner, participant in participants.items():
        ack = participant.decide(plan, persisted, 1000)
        restarted.acknowledge(plan['transaction'], owner, ack)
    assert restarted.status(plan['transaction']) == 'completed'
    with pytest.raises(ValueError, match='cannot change'):
        restarted.decide(plan, votes, buyer, 'workflow', 1000, action='abort')


def test_prepared_cannot_expire_or_be_released_without_decision(tmp_path):
    participants, coordinator, plan, buyer = setup(tmp_path)
    votes = {o: p.prepare(plan, 100) for o, p in participants.items()}
    contender = dict(plan, transaction='OTHER')
    for owner, participant in participants.items():
        assert participant.prepare(contender, 1000)['status'] == 'denied'
        with pytest.raises(ValueError, match='durable decision'):
            participant.store.transition(plan['transaction'], votes[owner]['body']['scope_hash'], 'release', 1000)
    decision = coordinator.decide(plan, votes, buyer, 'workflow', 1000, action='abort')
    for owner, participant in participants.items():
        participant.decide(plan, decision, 1001)
        ack = participant.decide(plan, decision, 1002)
        coordinator.acknowledge(plan['transaction'], owner, ack)
        assert participant.prepare(contender, 1003)['body']['kind'] == 'prepared'
    assert coordinator.status(plan['transaction']) == 'aborted'


def test_wrong_scope_missing_vote_and_forged_decision_blocked(tmp_path):
    participants, coordinator, plan, buyer = setup(tmp_path)
    votes = {o: p.prepare(plan, 100) for o, p in participants.items()}
    with pytest.raises(ValueError, match='missing'):
        coordinator.decide(plan, {'supplier': votes['supplier']}, buyer, 'workflow', 101,
                           buyer_decision=coordinator.test_intent)
    with pytest.raises(ValueError, match='execution request required'):
        coordinator.decide(plan, votes, buyer, 'workflow', 101)
    decision = coordinator.decide(plan, votes, buyer, 'workflow', 101, buyer_decision=coordinator.test_intent)
    decision['body']['action'] = 'abort'
    with pytest.raises(ValueError, match='signature'):
        participants['supplier'].decide(plan, decision, 102)


@pytest.mark.parametrize('occupied', [False, True])
def test_runtime_commits_or_releases_partial_preparation(tmp_path, occupied):
    participants, coordinator, plan, buyer = setup(tmp_path)
    if occupied:
        participants['carrier'].prepare(dict(plan, transaction='COMPETING'), 100)
    def call(owner, operation, **kwargs):
        if operation == 'attest': return {'commitment': buyer}
        if operation == 'resource_prepare':
            return {'resource': participants[owner].prepare(kwargs['plan'], 101)}
        return {'resource': participants[owner].decide(kwargs['plan'], kwargs['decision'], 102)}
    result = execute_resource_plan(coordinator, call, plan, coordinator.test_intent, 'workflow', lambda: 101)
    assert result['status'] == ('aborted' if occupied else 'completed')
    if occupied:
        assert result['denial']['owner'] == 'carrier'
        assert participants['supplier'].prepare(dict(plan, transaction='AVAILABLE'), 103)['body']['kind'] == 'prepared'
