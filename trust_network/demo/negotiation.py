"""Versioned delivery plans and organization-scoped commitments.

Business agents choose plans. Owner gateways check only their own constraints.
The execution sink uses public plans and signed commitments, never registries.
"""
from dataclasses import asdict
import json
import math
import sqlite3
from trust_network.demo.documents import Certificate, Decision, digest

OWNERS=('supplier','carrier','buyer')


def validate_plan(plan):
    if set(plan)!={'transaction','model','quantity','shipments'}:
        raise ValueError('invalid plan fields')
    if not isinstance(plan['transaction'],str) or not plan['transaction']:
        raise ValueError('transaction required')
    if not isinstance(plan['model'],str) or not plan['model']:
        raise ValueError('model required')
    if type(plan['quantity']) is not int or plan['quantity']<=0:
        raise ValueError('positive integer quantity required')
    shipments=plan['shipments']
    if not isinstance(shipments,list) or not 1<=len(shipments)<=10:
        raise ValueError('bounded shipment list required')
    for row in shipments:
        if set(row)!={'lot','quantity','dispatch_day','service','arrival_day','cost'}:
            raise ValueError('invalid shipment fields')
        if not all(isinstance(row[k],str) and row[k] for k in ('lot','service')):
            raise ValueError('lot and service required')
        if any(type(row[k]) is not int or row[k]<=0 for k in ('quantity','dispatch_day','arrival_day')):
            raise ValueError('invalid shipment quantity/day')
        if row['arrival_day']<row['dispatch_day']:
            raise ValueError('arrival before dispatch')
        if type(row['cost']) not in (int,float) or not math.isfinite(row['cost']) or row['cost']<0:
            raise ValueError('invalid price')
    if sum(row['quantity'] for row in shipments)!=plan['quantity']:
        raise ValueError('shipment quantities do not match order')


def projection(owner,plan,binding_mode='dependency'):
    """Explicit dependency scopes. Excluded fields do not affect this contract."""
    validate_plan(plan)
    if owner not in OWNERS: raise ValueError('unknown commitment owner')
    if binding_mode=='full': return json.loads(json.dumps(plan))
    if binding_mode!='dependency': raise ValueError('unknown binding mode')
    base={k:plan[k] for k in ('transaction','model','quantity')}
    if owner=='supplier':
        fields=('lot','quantity','dispatch_day')
    elif owner=='carrier':
        fields=('quantity','dispatch_day','service','arrival_day','cost')
    elif owner=='buyer':
        fields=('quantity','arrival_day')
        base['total_cost']=sum(s['cost'] for s in plan['shipments'])
    else: raise ValueError('unknown commitment owner')
    base['shipments']=sorted(({k:row[k] for k in fields} for row in plan['shipments']),key=digest)
    return base


def owner_check(owner,private,plan):
    """Only an organization service calls this with its own private record."""
    validate_plan(plan); reasons=[]
    if owner=='supplier':
        totals={}
        for row in plan['shipments']:
            lot=private['lots'].get(row['lot'])
            if lot is None or lot['model']!=plan['model'] or row['dispatch_day']<lot['ready_day']:
                reasons.append('lot_not_available_for_requested_dispatch')
            totals[row['lot']]=totals.get(row['lot'],0)+row['quantity']
        if any(lot not in private['lots'] or count>private['lots'][lot]['quantity'] for lot,count in totals.items()):
            reasons.append('supply_capacity_exceeded')
    elif owner=='carrier':
        totals={}; fees={}
        for row in plan['shipments']:
            service=private['services'].get(row['service'])
            if service is None or row['dispatch_day']!=service['dispatch_day'] or row['arrival_day']!=service['arrival_day']:
                reasons.append('transport_schedule_not_confirmed')
            totals[row['service']]=totals.get(row['service'],0)+row['quantity']
            fees[row['service']]=fees.get(row['service'],0)+row['cost']
        for name,count in totals.items():
            service=private['services'].get(name)
            if service is None or count>service['capacity']: reasons.append('transport_capacity_exceeded')
            if service is None or fees[name]!=service['price']: reasons.append('transport_quote_mismatch')
    elif owner=='buyer':
        if not private['model_approvals'].get(plan['model'],False): reasons.append('model_not_approved')
        if plan['quantity']!=private['quantity']: reasons.append('wrong_order_quantity')
        if max(s['arrival_day'] for s in plan['shipments'])>private['latest_day']:
            reasons.append('delivery_deadline_exceeded')
        if sum(s['cost'] for s in plan['shipments'])>private['freight_cap']:
            reasons.append('freight_budget_exceeded')
    else: raise ValueError('unknown owner')
    return tuple(sorted(set(reasons)))


def attest(owner,private,plan,workflow_id,sequence,key,now,*,ttl=300,binding_mode='dependency'):
    if type(sequence) is not int or sequence<1: raise ValueError('positive sequence required')
    if not 0<ttl<=300: raise ValueError('invalid lifetime')
    reasons=owner_check(owner,private,plan)
    body={'owner':owner,'workflow_id':workflow_id,'scope':'delivery_'+owner,
          'projection':projection(owner,plan,binding_mode),'binding_mode':binding_mode,
          'sequence':sequence,'issued_at':now,'expires_at':now+ttl,
          'status':'denied' if reasons else 'approved','reasons':list(reasons)}
    signature=Certificate.issue(owner,1,body,
        Decision('reject' if reasons else 'pass',('delivery_'+owner,),(),'scoped commitment'),key)
    return {'body':body,'signature':asdict(signature)}


def inspect(owner,public_key,plan,workflow_id,receipt,now):
    body=receipt['body']; signature=Certificate(**receipt['signature'])
    if (signature.issuer!=owner or body['owner']!=owner or body['scope']!='delivery_'+owner or
            tuple(signature.checks)!=('delivery_'+owner,) or body['workflow_id']!=workflow_id or
            not signature.verify(public_key,body,1)):
        raise ValueError('invalid commitment signature or identity')
    if digest(body['projection'])!=digest(projection(owner,plan,body.get('binding_mode','dependency'))):
        raise ValueError('commitment does not cover current plan')
    if type(body['sequence']) is not int or body['sequence']<1:
        raise ValueError('invalid commitment sequence')
    if not body['issued_at']<=now<body['expires_at'] or not 0<body['expires_at']-body['issued_at']<=300:
        raise ValueError('stale commitment')
    if body['status'] not in ('approved','denied'):
        raise ValueError('invalid commitment status')
    if signature.action!=('pass' if body['status']=='approved' else 'reject'):
        raise ValueError('signature action disagrees with commitment')
    return body['status']


class CommitmentBook:
    """Public receipt ledger. Past denials survive expiry and cache eviction."""
    def __init__(self,public_keys,workflow_id,binding_mode='dependency'):
        if binding_mode not in ('dependency','full'): raise ValueError('unknown binding mode')
        self.public_keys=public_keys; self.workflow_id=workflow_id; self.latest={}; self.binding_mode=binding_mode

    def add(self,owner,plan,receipt,now):
        inspect(owner,self.public_keys[owner],plan,self.workflow_id,receipt,now)
        if receipt['body'].get('binding_mode','dependency')!=self.binding_mode:
            raise ValueError('commitment binding mode differs from receiving protocol')
        index=(owner,digest(projection(owner,plan,self.binding_mode)))
        previous=self.latest.get(index)
        if previous is not None:
            if receipt['body']['sequence']<previous['body']['sequence']:
                raise ValueError('replayed superseded commitment')
            if receipt['body']['sequence']==previous['body']['sequence'] and digest(receipt)!=digest(previous):
                raise ValueError('conflicting commitments at same sequence')
        self.latest[index]=json.loads(json.dumps(receipt))

    def required(self,plan,now):
        missing=[]; denied=[]; receipts=[]
        for owner in OWNERS:
            receipt=self.latest.get((owner,digest(projection(owner,plan,self.binding_mode))))
            if receipt is None: missing.append(owner); continue
            if receipt['body']['status']=='denied': denied.append(owner); continue
            try: inspect(owner,self.public_keys[owner],plan,self.workflow_id,receipt,now)
            except ValueError: missing.append(owner); continue
            receipts.append(receipt)
        return {'missing':missing,'denied':denied,'receipts':receipts}


class ExecutionSink:
    """Durable simulated shipment sink with transaction-level idempotency.

    It verifies public commitments itself. This does not claim an external
    logistics provider participates in the SQLite transaction.
    """
    def __init__(self,path,public_keys,binding_mode='dependency'):
        self.path=path; self.public_keys=public_keys; self.binding_mode=binding_mode
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS executions (transaction_id TEXT PRIMARY KEY, plan_hash TEXT NOT NULL, receipt TEXT NOT NULL)')

    def commit(self,plan,book,now):
        if book.public_keys!=self.public_keys: raise ValueError('untrusted commitment registry')
        if book.binding_mode!=self.binding_mode: raise ValueError('execution protocol binding mismatch')
        checked=book.required(plan,now)
        if checked['missing'] or checked['denied']:
            raise ValueError('current plan lacks all required commitments')
        return self._record(plan,book.workflow_id,checked['receipts'],now)

    def _record(self,plan,workflow_id,commitments,now):
        receipt={'transaction':plan['transaction'],'workflow_id':workflow_id,'plan_hash':digest(plan),
                 'plan':plan,'commitments':commitments,'committed_at':now,'assurance':self.binding_mode}
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT plan_hash,receipt FROM executions WHERE transaction_id=?',
                                (plan['transaction'],)).fetchone()
            if previous:
                if previous[0]!=digest(plan): raise ValueError('transaction already executed with another plan')
                return {'duplicate':True,'receipt':json.loads(previous[1])}
            db.execute('INSERT INTO executions VALUES (?,?,?)',
                       (plan['transaction'],digest(plan),json.dumps(receipt)))
        return {'duplicate':False,'receipt':receipt}


class AutonomousExecutionSink(ExecutionSink):
    """Benchmark control: signed buyer execution request, no forced owner checks.

    It is deliberately separate from the protected sink. It records simulated
    actions only; it is not an alternative production authorization endpoint.
    """
    def __init__(self,path,public_keys): super().__init__(path,public_keys,'autonomous')

    def commit(self,plan,buyer_decision,workflow_id,now):
        from trust_network.demo.negotiation_worker import verify
        validate_plan(plan)
        body=verify(buyer_decision,'buyer',self.public_keys['buyer'],workflow_id)
        if body['content']['action']!='propose' or digest(body['content']['plan'])!=digest(plan):
            raise ValueError('buyer did not request this execution')
        return self._record(plan,workflow_id,[],now)
