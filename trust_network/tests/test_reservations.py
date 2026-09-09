from concurrent.futures import ThreadPoolExecutor
import copy
import pytest
from trust_network.demo.negotiation import owner_check
from trust_network.demo.negotiation_scenario import PRIVATE
from trust_network.demo.reservations import ReservationStore
from trust_network.tests.test_negotiation import split_plan


@pytest.mark.parametrize('owner', ['supplier', 'carrier'])
def test_concurrent_orders_cannot_consume_the_same_resource(tmp_path, owner):
    plans = [split_plan(), split_plan()]
    plans[1]['transaction'] = 'SECOND-ORDER'
    # The old snapshot checker approves both: the counterexample is explicit.
    assert all(owner_check(owner, PRIVATE[owner], plan) == () for plan in plans)
    store = ReservationStore(tmp_path/'resources.sqlite', owner, PRIVATE[owner])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda plan: store.prepare(plan, 100), plans))
    assert sorted(r['status'] for r in results) == ['denied', 'held']
    winner = next(i for i, r in enumerate(results) if r['status'] == 'held')
    scope = results[winner]['scope_hash']
    restarted = ReservationStore(store.path, owner, PRIVATE[owner])
    assert restarted.transition(plans[winner]['transaction'], scope, 'commit', 101) == 'committed'
    assert restarted.transition(plans[winner]['transaction'], scope, 'commit', 1000) == 'committed'
    assert restarted.prepare(plans[1-winner], 1000)['status'] == 'denied'
    with pytest.raises(ValueError, match='compensation'):
        restarted.transition(plans[winner]['transaction'], scope, 'release', 1000)


def test_expiry_release_and_dependency_reuse(tmp_path):
    store = ReservationStore(tmp_path/'resources.sqlite', 'supplier', PRIVATE['supplier'])
    plan = split_plan()
    held = store.prepare(plan, 100, ttl=10)
    changed = copy.deepcopy(plan)
    changed['shipments'][0]['cost'] += 100
    assert store.prepare(changed, 101) == held
    with pytest.raises(ValueError, match='no longer active'):
        store.transition(plan['transaction'], held['scope_hash'], 'commit', 110)
    second = copy.deepcopy(plan)
    second['transaction'] = 'SECOND'
    renewed = store.prepare(second, 110)
    assert renewed['status'] == 'held'
    assert store.transition(second['transaction'], renewed['scope_hash'], 'release', 111) == 'released'
    assert store.prepare(plan, 112)['status'] == 'held'
