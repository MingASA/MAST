"""Online short-circuit verification over observable owner responses.

Order checks by estimated denial probability / cost. This minimizes expected
cost until the first denial under independent Bernoulli outcomes. The estimate
is a Beta(1,1) mean updated only from signed responses, not hidden truth.
"""
class VerificationSchedule:
    def __init__(self, owners, costs=None):
        self.owners = tuple(owners)
        self.costs = costs or {o: 1.0 for o in owners}
        self.counts = {o: [1, 1] for o in owners}

    def order(self, required, previously_denied=()):
        # Re-check a known blocking dependency first after the Agent repairs it.
        return sorted(required, key=lambda o: (o not in previously_denied,
            -self.counts[o][0] / sum(self.counts[o]) / self.costs[o], self.owners.index(o)))

    def observe(self, owner, denied):
        self.counts[owner][0 if denied else 1] += 1
