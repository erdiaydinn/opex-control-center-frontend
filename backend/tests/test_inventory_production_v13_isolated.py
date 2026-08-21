"""Run Inventory production acceptance with v13 history-preserving fixture isolation.

Inventory v13 correctly prevents one operator from owning more than one ACTIVE
wall-to-wall location. The legacy production adversarial class predates that
invariant and intentionally reuses one tenant/operator pair across test methods,
so an ACTIVE attempt left by one successful test would contaminate the next.

This adapter does not weaken or bypass the database guard. Before each inherited
test it closes any prior ACTIVE fixture authority in the dedicated CI tenant by
appending lease-closure evidence and transitioning the corresponding attempts to
ABANDONED. The original production test methods then run unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.modules.inventory import test_inventory_production as _legacy
from backend.app.modules.inventory.production import connect


class InventoryProductionContractTests(_legacy.InventoryProductionContractTests):
    """Preserve the original pure production contract tests unchanged."""


class InventoryPostgresAdversarialTests(_legacy.InventoryPostgresAdversarialTests):
    """Preserve adversarial semantics while isolating durable v13 fixture state."""

    @staticmethod
    def key_for(principal):
        # The legacy helper names its concrete class directly. The inherited
        # setUpClass binds fresh keys to this isolated subclass, so keep signing
        # authority on the subclass rather than mutating the legacy test class.
        if principal.employee_id == "EMP-1":
            return InventoryPostgresAdversarialTests.private_key_one
        if principal.employee_id == "EMP-2":
            return InventoryPostgresAdversarialTests.private_key_two
        raise AssertionError("unknown test principal")

    def setUp(self):
        self._close_prior_fixture_authority()
        super().setUp()

    def _close_prior_fixture_authority(self) -> None:
        now = datetime.now(UTC)
        tenant = self.tenant
        with connect() as db:
            db.execute(
                """
                INSERT INTO inventory_mission_lease_closures(
                  tenant_id, lease_id, state, reason, closed_at, closed_by_subject
                )
                SELECT l.tenant_id,
                       l.lease_id,
                       'SUPERSEDED',
                       'test fixture isolation',
                       GREATEST(%s, l.valid_from),
                       'inventory-production-v13-test'
                  FROM inventory_mission_leases l
                  JOIN inventory_mission_attempts a
                    ON a.tenant_id=l.tenant_id
                   AND a.attempt_id=l.attempt_id
                  LEFT JOIN inventory_mission_lease_closures c
                    ON c.tenant_id=l.tenant_id
                   AND c.lease_id=l.lease_id
                 WHERE a.tenant_id=%s
                   AND a.state='ACTIVE'
                   AND c.lease_id IS NULL
                ON CONFLICT (tenant_id, lease_id) DO NOTHING
                """,
                (now, tenant),
            )
            db.execute(
                """
                UPDATE inventory_mission_attempts
                   SET state='ABANDONED',
                       closed_at=GREATEST(%s, created_at),
                       close_reason='test fixture isolation'
                 WHERE tenant_id=%s
                   AND state='ACTIVE'
                """,
                (now, tenant),
            )
            db.commit()
