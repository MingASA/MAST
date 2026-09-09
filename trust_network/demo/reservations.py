"""Owner-local resource holds; never expose this database to the coordinator.

This is the storage primitive for the dynamic protocol, not a distributed
transaction. Committed allocations are deliberately not released by TTL.
"""
import json
import math
import sqlite3
from trust_network.demo.documents import digest
from trust_network.demo.negotiation import owner_check, projection


class ReservationStore:
    def __init__(self, path, owner, private):
        if owner not in ('supplier', 'carrier'):
            raise ValueError('resource owner required')
        self.path, self.owner = path, owner
        self.private = json.loads(json.dumps(private))
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY, value TEXT)')
            identity = digest({'owner': owner, 'private': private})
            old = db.execute('SELECT value FROM metadata WHERE id=1').fetchone()
            if old and old[0] != identity:
                raise ValueError('resource configuration changed; explicit migration required')
            db.execute('INSERT OR IGNORE INTO metadata VALUES (1, ?)', (identity,))
            db.execute('''CREATE TABLE IF NOT EXISTS holds (
                transaction_id TEXT PRIMARY KEY, scope_hash TEXT NOT NULL,
                resources TEXT NOT NULL, expires_at REAL NOT NULL, status TEXT NOT NULL)''')

    def prepare(self, plan, now, ttl=60):
        if not math.isfinite(now) or not math.isfinite(ttl) or not 0 < ttl <= 300:
            raise ValueError('invalid hold lifetime')
        reasons = owner_check(self.owner, self.private, plan)
        if reasons:
            return {'status': 'denied', 'reasons': list(reasons)}
        scope_hash = digest(projection(self.owner, plan))
        field = 'lot' if self.owner == 'supplier' else 'service'
        records = self.private['lots' if self.owner == 'supplier' else 'services']
        capacity = 'quantity' if self.owner == 'supplier' else 'capacity'
        requested = {}
        for row in plan['shipments']:
            requested[row[field]] = requested.get(row[field], 0) + row['quantity']
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE holds SET status='expired' WHERE status='held' AND expires_at<=?", (now,))
            old = db.execute('SELECT scope_hash, expires_at, status FROM holds WHERE transaction_id=?',
                             (plan['transaction'],)).fetchone()
            if old and old[2] in ('held', 'prepared', 'committed'):
                if old[0] != scope_hash:
                    return {'status': 'denied', 'reasons': ['active_scope_conflict']}
                return {'status': old[2], 'scope_hash': scope_hash, 'expires_at': old[1]}
            used = {}
            for (encoded,) in db.execute("SELECT resources FROM holds WHERE status IN ('held','prepared','committed')"):
                for resource, amount in json.loads(encoded).items():
                    used[resource] = used.get(resource, 0) + amount
            if any(used.get(k, 0) + amount > records[k][capacity] for k, amount in requested.items()):
                return {'status': 'denied', 'reasons': ['resource_already_allocated']}
            db.execute('INSERT OR REPLACE INTO holds VALUES (?, ?, ?, ?, ?)',
                       (plan['transaction'], scope_hash, json.dumps(requested), now + ttl, 'held'))
            return {'status': 'held', 'scope_hash': scope_hash, 'expires_at': now + ttl}

    def transition(self, transaction, scope_hash, action, now):
        """Called by the authenticated owner gateway, not an untrusted agent.

        Release applies only before commit; reversing an executed allocation
        requires a separate business compensation process.
        """
        if action not in ('prepare', 'commit', 'release', 'abort') or not math.isfinite(now):
            raise ValueError('invalid transition')
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT scope_hash, expires_at, status FROM holds WHERE transaction_id=?',
                             (transaction,)).fetchone()
            if old is None or old[0] != scope_hash:
                raise ValueError('unknown reservation scope')
            if old[2] == 'released' and action == 'abort': return 'released'
            if old[2] == 'committed':
                if action == 'commit':
                    return 'committed'
                raise ValueError('committed allocation requires compensation')
            if old[2] == 'prepared':
                if action == 'prepare': return 'prepared'
                if action not in ('commit', 'abort'):
                    raise ValueError('prepared reservation requires durable decision')
                status = 'committed' if action == 'commit' else 'released'
                db.execute('UPDATE holds SET status=? WHERE transaction_id=?', (status, transaction))
                return status
            if old[2] != 'held' or old[1] <= now:
                raise ValueError('reservation is no longer active')
            status = {'prepare': 'prepared', 'commit': 'committed', 'release': 'released', 'abort': 'released'}[action]
            db.execute('UPDATE holds SET status=? WHERE transaction_id=?', (status, transaction))
            return status
