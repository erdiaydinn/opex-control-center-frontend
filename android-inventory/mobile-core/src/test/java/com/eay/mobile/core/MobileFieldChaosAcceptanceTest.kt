package com.eay.mobile.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Executable pre-pilot chaos acceptance over the real mobile sync state machine.
 *
 * This deliberately composes multiple failures instead of testing each enum in
 * isolation. Durable evidence must never be rewritten, silently rebound or
 * converted to success because connectivity/session/device state changed.
 */
class MobileFieldChaosAcceptanceTest {
    private val baseNow = 1_800_000_000_000L

    private fun event(
        eventId: String = "event-chaos-1",
        deviceId: String = "device-a",
        installationId: String = "install-a",
        authBindingId: String = "auth-a",
        deviceSequence: Long = 1,
        previousLedgerHash: String? = null,
    ) = MobileEventEnvelope(
        eventId = eventId,
        tenantId = "tenant-a",
        actorId = "employee-a",
        deviceId = deviceId,
        installationId = installationId,
        authBindingId = authBindingId,
        missionId = "count:document-a:A01",
        operation = "inventory.count.capture",
        deviceSequence = deviceSequence,
        occurredAt = "2026-08-20T07:00:00Z",
        payloadHash = "b".repeat(64),
        previousLedgerHash = previousLedgerHash,
        policyFingerprint = "a".repeat(64),
        appVersion = "1.0.0",
    )

    private fun context(
        connectivity: ConnectivityState = ConnectivityState.ONLINE,
        deviceId: String = "device-a",
        installationId: String = "install-a",
        authBindingId: String = "auth-a",
        deviceActive: Boolean = true,
        now: Long = baseNow,
    ) = SyncExecutionContext(
        tenantId = "tenant-a",
        deviceId = deviceId,
        installationId = installationId,
        authBindingId = authBindingId,
        deviceActive = deviceActive,
        connectivity = connectivity,
        nowEpochMs = now,
    )

    @Test
    fun `network loss then server outage then exact replay commits exactly once`() {
        val policy = SyncRetryPolicy(
            maxAttempts = 4,
            initialDelayMs = 1_000,
            maxDelayMs = 8_000,
        )
        val queued = SyncRecord(event())

        val offlinePlan = MobileSyncEngine.plan(
            queued,
            context(connectivity = ConnectivityState.OFFLINE),
            expectedPreviousLedgerHash = null,
            retryPolicy = policy,
        )
        assertEquals(SyncPlanCode.WAIT_OFFLINE, offlinePlan.code)
        assertEquals(0, queued.attempts)

        val onlinePlan = MobileSyncEngine.plan(
            queued,
            context(connectivity = ConnectivityState.ONLINE),
            expectedPreviousLedgerHash = null,
            retryPolicy = policy,
        )
        assertEquals(SyncPlanCode.SEND, onlinePlan.code)

        val after503 = MobileSyncEngine.applyServerVerdict(
            queued,
            SyncServerVerdict(SyncServerOutcome.RETRYABLE_FAILURE, "HTTP_503"),
            baseNow,
            policy,
        )
        assertEquals(SyncRecordState.RETRY_WAIT, after503.state)
        assertEquals(1, after503.attempts)
        assertEquals(baseNow + 1_000, after503.nextAttemptAtEpochMs)

        val backoffPlan = MobileSyncEngine.plan(
            after503,
            context(now = baseNow + 500),
            expectedPreviousLedgerHash = null,
            retryPolicy = policy,
        )
        assertEquals(SyncPlanCode.WAIT_BACKOFF, backoffPlan.code)

        val retryPlan = MobileSyncEngine.plan(
            after503,
            context(now = baseNow + 1_000),
            expectedPreviousLedgerHash = null,
            retryPolicy = policy,
        )
        assertEquals(SyncPlanCode.SEND, retryPlan.code)

        val exactReplay = MobileSyncEngine.applyServerVerdict(
            after503,
            SyncServerVerdict(SyncServerOutcome.EXACT_REPLAY, "EVENT_ALREADY_COMMITTED"),
            baseNow + 1_000,
            policy,
        )
        assertEquals(SyncRecordState.ACKED, exactReplay.state)
        assertEquals("EVENT_ALREADY_COMMITTED", exactReplay.lastServerCode)
        assertNull(exactReplay.quarantineReason)

        val settledPlan = MobileSyncEngine.plan(
            exactReplay,
            context(now = baseNow + 2_000),
            expectedPreviousLedgerHash = null,
            retryPolicy = policy,
        )
        assertEquals(SyncPlanCode.NOOP_ACKED, settledPlan.code)
    }

    @Test
    fun `token rotation quarantines old durable evidence instead of replaying under new auth`() {
        val queued = SyncRecord(event(authBindingId = "auth-old"))
        val plan = MobileSyncEngine.plan(
            queued,
            context(authBindingId = "auth-new"),
            expectedPreviousLedgerHash = null,
        )
        assertEquals(SyncPlanCode.QUARANTINE, plan.code)
        assertEquals(SyncQuarantineReason.AUTH_BINDING_CHANGED, plan.quarantineReason)
    }

    @Test
    fun `physical device replacement cannot inherit old queue even for same employee`() {
        val oldEvidence = SyncRecord(event(deviceId = "device-old"))
        val plan = MobileSyncEngine.plan(
            oldEvidence,
            context(deviceId = "device-new"),
            expectedPreviousLedgerHash = null,
        )
        assertEquals(SyncPlanCode.QUARANTINE, plan.code)
        assertEquals(SyncQuarantineReason.DEVICE_BINDING_CHANGED, plan.quarantineReason)
    }

    @Test
    fun `revocation wins over restored connectivity`() {
        val queued = SyncRecord(event())
        val plan = MobileSyncEngine.plan(
            queued,
            context(connectivity = ConnectivityState.ONLINE, deviceActive = false),
            expectedPreviousLedgerHash = null,
        )
        assertEquals(SyncPlanCode.QUARANTINE, plan.code)
        assertEquals(SyncQuarantineReason.DEVICE_REVOKED, plan.quarantineReason)
    }

    @Test
    fun `business conflict and retry exhaustion require governed recovery not last write wins`() {
        val conflict = MobileSyncEngine.applyServerVerdict(
            SyncRecord(event(eventId = "event-conflict")),
            SyncServerVerdict(SyncServerOutcome.BUSINESS_CONFLICT, "COUNT_REVISION_CONFLICT"),
            baseNow,
        )
        assertEquals(SyncRecordState.QUARANTINED, conflict.state)
        assertEquals(SyncQuarantineReason.BUSINESS_CONFLICT, conflict.quarantineReason)

        val policy = SyncRetryPolicy(
            maxAttempts = 2,
            initialDelayMs = 1_000,
            maxDelayMs = 2_000,
        )
        val firstFailure = MobileSyncEngine.applyServerVerdict(
            SyncRecord(event(eventId = "event-retry")),
            SyncServerVerdict(SyncServerOutcome.RETRYABLE_FAILURE, "HTTP_500"),
            baseNow,
            policy,
        )
        val exhausted = MobileSyncEngine.applyServerVerdict(
            firstFailure,
            SyncServerVerdict(SyncServerOutcome.RETRYABLE_FAILURE, "HTTP_500"),
            baseNow + 1_000,
            policy,
        )
        assertEquals(SyncRecordState.QUARANTINED, exhausted.state)
        assertEquals(SyncQuarantineReason.RETRY_EXHAUSTED, exhausted.quarantineReason)
    }

    @Test
    fun `ledger corruption remains security quarantine after network recovers`() {
        val corrupted = SyncRecord(
            event(previousLedgerHash = "c".repeat(64)),
        )
        val plan = MobileSyncEngine.plan(
            corrupted,
            context(connectivity = ConnectivityState.ONLINE),
            expectedPreviousLedgerHash = "d".repeat(64),
        )
        assertEquals(SyncPlanCode.QUARANTINE, plan.code)
        assertEquals(SyncQuarantineReason.LEDGER_CHAIN_MISMATCH, plan.quarantineReason)
    }
}
