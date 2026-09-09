import copy
import sqlite3
import pytest
from trust_network.demo.documents import keypair
from trust_network.demo.negotiation import (
    OWNERS, attest, owner_check, projection, CommitmentBook, ExecutionSink)
from trust_network.demo.negotiation_scenario import PRIVATE


def split_plan():
    return {'transaction':'PROCUREMENT-017','model':'MX-40B','quantity':10,'shipments':[
        {'lot':'early','quantity':4,'dispatch_day':1,'service':'air','arrival_day':2,'cost':1500},
        {'lot':'later','quantity':6,'dispatch_day':3,'service':'road','arrival_day':5,'cost':600}]}


def bulk_plan():
    plan=split_plan()
    for row in plan['shipments']:
        row.update(dispatch_day=3,service='bulk',arrival_day=5,cost=0)
    plan['shipments'][0]['cost']=900
    return plan


def setup_book(plan):
    keys={org:keypair() for org in OWNERS}; public={o:p[1] for o,p in keys.items()}
    book=CommitmentBook(public,'w1')
    for owner in OWNERS:
        book.add(owner,plan,attest(owner,PRIVATE[owner],plan,'w1',1,keys[owner][0],1000.),1000.)
    return keys,public,book


def test_two_genuinely_distinct_business_plans_are_feasible():
    for plan in (split_plan(),bulk_plan()):
        assert all(owner_check(org,PRIVATE[org],plan)==() for org in OWNERS)
    assert sum(s['cost'] for s in split_plan()['shipments'])==2100
    assert sum(s['cost'] for s in bulk_plan()['shipments'])==900


def test_plan_edit_invalidates_only_affected_commitments():
    plan=split_plan(); keys,public,book=setup_book(plan)
    changed=copy.deepcopy(plan); changed['shipments'][1]['cost']=700
    assert book.required(changed,1000.)['missing']==['carrier','buyer']
    assert projection('supplier',changed)==projection('supplier',plan)
    # No private state is available to the receipt book to decide this.
    assert set(book.__dict__)=={'public_keys','workflow_id','latest','binding_mode'}


def test_capacity_and_price_are_aggregated_across_shared_service():
    plan=bulk_plan()
    assert owner_check('carrier',PRIVATE['carrier'],plan)==()
    plan['shipments'][1]['cost']=900
    assert 'transport_quote_mismatch' in owner_check('carrier',PRIVATE['carrier'],plan)
    plan=split_plan(); plan['shipments'][0]['quantity']=5; plan['shipments'][1]['quantity']=5
    assert 'supply_capacity_exceeded' in owner_check('supplier',PRIVATE['supplier'],plan)
    assert 'transport_capacity_exceeded' in owner_check('carrier',PRIVATE['carrier'],plan)


def test_denial_survives_expiry_and_old_approval_cannot_be_replayed():
    plan=split_plan(); keys,public,book=setup_book(plan)
    old=book.required(plan,1000.)['receipts'][-1]
    private=copy.deepcopy(PRIVATE['buyer']); private['model_approvals']['MX-40B']=False
    denial=attest('buyer',private,plan,'w1',2,keys['buyer'][0],1010.)
    book.add('buyer',plan,denial,1010.)
    assert book.required(plan,1400.)['denied']==['buyer']
    with pytest.raises(ValueError,match='superseded'):
        book.add('buyer',plan,old,1020.)


def test_execution_is_durable_idempotent_and_requires_current_plan(tmp_path):
    plan=split_plan(); keys,public,book=setup_book(plan)
    sink=ExecutionSink(tmp_path/'sink.sqlite',public)
    assert not sink.commit(plan,book,1000.)['duplicate']
    restarted=ExecutionSink(tmp_path/'sink.sqlite',public)
    assert restarted.commit(plan,book,1001.)['duplicate']
    changed=bulk_plan()
    with pytest.raises(ValueError,match='lacks'): restarted.commit(changed,book,1001.)
    for org in OWNERS:
        book.add(org,changed,attest(org,PRIVATE[org],changed,'w1',3,keys[org][0],1001.),1001.)
    with pytest.raises(ValueError,match='already executed'): restarted.commit(changed,book,1001.)
    with sqlite3.connect(tmp_path/'sink.sqlite') as db:
        assert db.execute('SELECT COUNT(*) FROM executions').fetchone()[0]==1


def test_full_binding_cache_is_reused_until_plan_actually_changes():
    plan=split_plan(); keys={o:keypair() for o in OWNERS}; public={o:p[1] for o,p in keys.items()}
    book=CommitmentBook(public,'w1','full')
    for owner in OWNERS:
        book.add(owner,plan,attest(owner,PRIVATE[owner],plan,'w1',1,keys[owner][0],1000.,binding_mode='full'),1000.)
    assert book.required(plan,1001.)['missing']==[]
    changed=copy.deepcopy(plan); changed['shipments'][1]['cost']=700
    assert book.required(changed,1001.)['missing']==list(OWNERS)
    narrower=attest('supplier',PRIVATE['supplier'],changed,'w1',2,keys['supplier'][0],1001.)
    with pytest.raises(ValueError,match='binding mode'): book.add('supplier',changed,narrower,1001.)
