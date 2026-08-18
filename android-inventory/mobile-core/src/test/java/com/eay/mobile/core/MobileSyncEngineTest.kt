package com.eay.mobile.core

import org.junit.Assert.assertEquals
import org.junit.Test

class MobileSyncEngineTest {
    private val now = 1_800_000_000_000L

    private fun event(
        tenantId: String = "tenant-a",
        deviceId: String = "device-1",
        installationId: String = "install-1",
        authBindingId: String = "auth-1",
        previousLedgerHash: String? = null,
    ) = MobileEventEnvelope(
        eventId = "event-1",
        tenantId = tenantId,
        actorId = "actor-a",
        deviceId = deviceId,
        installationId = installationId,
        authBindingId = authBindingId,
        missionId = "mission-1",
        operation = "inventory.count.capture",
        deviceSequence = 1,
        occurredAt = "2026-08-18T12:00:00Z",
        payloadHash = "b".repeat(64),
        previousLedgerHash = previousLedgerHash,
        policyFingerprint = "a".repeat(64),
        appVersion = "1.0.0",
    )

    private fun context(
        tenantId: String = "tenant-a",
        deviceId: String = "device-1",
        installationId: String = "install-1",
        authBindingId: String = "auth-1",
        deviceActive: Boolean = true,
        connectivity: ConnectivityState = ConnectivityState.ONLINE,
    ) = SyncExecutionContext(
        tenantId = tenantId,
        deviceId = deviceId,
        installationId = installationId,
        authBindingId = authBindingId,
        deviceActive = deviceActive,
        connectivity = connectivity,
        nowEpochMs = now,
    )

    @Test
    fun `offline waits without incrementing attempts`() {
        val record = SyncRecord(event())
        val plan = MobileSyncEngine.plan(
            record,
            context(connectivity = ConnectivityState.OFFLINE),
            expectedPreviousLedgerHash = null,
        )
        assertEquals(SyncPlanCode.WAIT_OFFLINE, plan.code)
        assertEquals(0, record.attempts)
    }

    @Test
    fun `auth binding rotation quarantines old offline event`() {
        val plan = MobileSyncEngine.plan(
            SyncRecord(event()),
            context(authBindingId = "auth-2"),
            expectedPreviousLedgerHash = null,
        )
        assertEquals(SyncPlanCode.QUARANTINE, plan.code)
        assertEquals(
            SyncQuarantineReason.AUTH_BINDING_CHANGED,
            plan.quarantineReason,
        )
    }

    @Test
    fun `device replacement or reinstall cannot inherit old queue`() {
        val replaced = MobileSyncEngine.plan(
            SyncRecord(event()),
            context(deviceId = "device-2"),
            expectedPreviousLedgerHash = null,
        )
        assertEquals(
            SyncQuarantineReason.DEVICE_BINDING_CHANGED,
            replaced.quarantineReason,
        )

        val reinstalled = MobileSyncEngine.plan(
            SyncRecord(event()),
            context(installationId = "install-2"),
            expectedPreviousLedgerHash = null,
        )
        assertEquals(
            SyncQuarantineReason.INSTALLATION_BINDING_CHANGED,
            reinstalled.quarantineReason,
        )
    }

    @Test
    fun `ledger chain corruption quarantines instead of skipping`() {
        val plan = MobileSyncEngine.plan(
            SyncRecord(event(previousLedgerHash = "c".repeat(64))),
            context(),
            expectedPreviousLedgerHash = "d".repeat(64),
        )
        assertEquals(
            SyncQuarantineReason.LEDGER_CHAIN_MISMATCH,
            plan.quarantineReason,
        )
    }

    @Test
    fun `exact replay is acknowledged as idempotent success`() {
        val result = MobileSyncEngine.applyServerVerdict(
            SyncRecord(event(), attempts = 2),
            SyncServerVerdict(
                SyncServerOutcome.EXACT_REPLAY,
                "EVENT_ALREADY_COMMITTED",
            ),
            now,
        )
        assertEquals(SyncRecordState.ACKED, result.state)
        assertEquals("EVENT_ALREADY_COMMITTED", result.lastServerCode)
    }

    @Test
    fun `business conflict is quarantined and never last write wins`() {
        val result = MobileSyncEngine.applyServerVerdict(
            SyncRecord(event()),
            SyncServerVerdict(
                SyncServerOutcome.BUSINESS_CONFLICT,
                "COUNT_REVISION_CONFLICT",
            ),
            now,
        )
        assertEquals(SyncRecordState.QUARANTINED, result.state)
        assertEquals(
            SyncQuarantineReason.BUSINESS_CONFLICT,
            result.quarantineReason,
        )
    }

    @Test
    fun `retry uses bounded exponential delay and eventually quarantines`() {
        val policy = SyncRetryPolicy(
            maxAttempts = 3,
            initialDelayMs = 1_000,
            maxDelayMs = 10_000,
        )
        val first = MobileSyncEngine.applyServerVerdict(
            SyncRecord(event()),
            SyncServerVerdict(
                SyncServerOutcome.RETRYABLE_FAILURE,
                "SERVER_UNAVAILABLE",
            ),
            now,
            policy,
        )
        assertEquals(SyncRecordState.RETRY_WAIT, first.state)
        assertEquals(now + 1_000, first.nextAttemptAtEpochMs)

        val second = MobileSyncEngine.applyServerVerdict(
            first,
            SyncServerVerdict(
                SyncServerOutcome.RETRYABLE_FAILURE,
                "SERVER_UNAVAILABLE",
            ),
            now + 1_000,
            policy,
        )
        assertEquals(now + 3_000, second.nextAttemptAtEpochMs)

        val third = MobileSyncEngine.applyServerVerdict(
            second,
            SyncServerVerdict(
                SyncServerOutcome.RETRYABLE_FAILURE,
                "SERVER_UNAVAILABLE",
            ),
            now + 3_000,
            policy,
        )
        assertEquals(SyncRecordState.QUARANTINED, third.state)
        assertEquals(
            SyncQuarantineReason.RETRY_EXHAUSTED,
            third.quarantineReason,
        )
    }

    @Test
    fun `revoked device is quarantined before network send`() {
        val plan = MobileSyncEngine.plan(
            SyncRecord(event()),
            context(deviceActive = false),
            expectedPreviousLedgerHash = null,
        )
        assertEquals(SyncPlanCode.QUARANTINE, plan.code)
        assertEquals(SyncQuarantineReason.DEVICE_REVOKED, plan.quarantineReason)
    }
}
