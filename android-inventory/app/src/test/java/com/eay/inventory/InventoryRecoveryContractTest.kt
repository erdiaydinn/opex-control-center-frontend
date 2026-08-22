package com.eay.inventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotEquals
import org.junit.Test

class InventoryRecoveryContractTest {
    private fun event(
        state: String,
        reason: String? = null,
        code: String? = null,
        id: String = "11111111-1111-4111-8111-111111111111",
        recoveryCaseId: String? = null,
        recoveryState: String? = null,
    ) = OfflineEvent(
        eventId = id,
        deviceSequence = 1,
        canonicalPayload = "{}",
        payloadHash = "a".repeat(64),
        authBindingId = "binding",
        state = state,
        quarantineReason = reason,
        lastServerCode = code,
        recoveryCaseId = recoveryCaseId,
        recoveryState = recoveryState,
    )

    @Test
    fun ackedEvidenceNeedsNoRecovery() {
        assertNull(InventoryRecoveryContract.classify(event("ACKED")))
    }

    @Test
    fun pendingAndBackoffRemainAutomaticOnly() {
        listOf("PENDING", "RETRY_WAIT").forEach { state ->
            val result = requireNotNull(InventoryRecoveryContract.classify(event(state)))
            assertEquals(InventoryRecoverySeverity.INFO, result.severity)
            assertEquals(InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY, result.intent)
            assertNull(result.reason)
        }
    }

    @Test
    fun quarantinedEvidenceNeverBecomesClientRetry() {
        val reasons = listOf(
            "CORRUPT_EVENT",
            "LEDGER_CHAIN_MISMATCH",
            "TENANT_BINDING_CHANGED",
            "DEVICE_BINDING_CHANGED",
            "INSTALLATION_BINDING_CHANGED",
            "AUTH_BINDING_CHANGED",
            "DEVICE_REVOKED",
            "POLICY_REJECTED",
            "BUSINESS_CONFLICT",
            "SERVER_CONTRACT_MISMATCH",
            "DEPENDENCY_BLOCKED",
            "PERMANENT_REJECTED",
            "RETRY_EXHAUSTED",
        )
        reasons.forEachIndexed { index, reason ->
            val result = requireNotNull(
                InventoryRecoveryContract.classify(
                    event(
                        state = "QUARANTINED",
                        reason = reason,
                        id = "11111111-1111-4111-8111-${(index + 1).toString().padStart(12, '0')}",
                    ),
                ),
            )
            check(result.intent != InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY)
        }
    }

    @Test
    fun authBindingMismatchCannotBeFixedBySigningInAgain() {
        val result = requireNotNull(
            InventoryRecoveryContract.classify(
                event("QUARANTINED", "AUTH_BINDING_CHANGED"),
            ),
        )
        assertEquals(InventoryRecoverySeverity.SECURITY, result.severity)
        assertEquals(InventoryRecoveryIntent.REQUEST_SECURITY_REVIEW, result.intent)
        assertNotEquals(InventoryRecoveryIntent.SIGN_IN_AGAIN, result.intent)
    }

    @Test
    fun policyRejectionRoutesToSecurityNotSupervisor() {
        val result = requireNotNull(
            InventoryRecoveryContract.classify(
                event("QUARANTINED", "POLICY_REJECTED", "HTTP_403"),
            ),
        )
        assertEquals(InventoryRecoverySeverity.SECURITY, result.severity)
        assertEquals(InventoryRecoveryIntent.REQUEST_SECURITY_REVIEW, result.intent)
        assertNotEquals(InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW, result.intent)
    }

    @Test
    fun serverContractAndPermanentRejectionRouteToIntegrityNotSupervisor() {
        listOf("SERVER_CONTRACT_MISMATCH", "PERMANENT_REJECTED").forEach { reason ->
            val result = requireNotNull(
                InventoryRecoveryContract.classify(event("QUARANTINED", reason)),
            )
            assertEquals(InventoryRecoverySeverity.SECURITY, result.severity)
            assertEquals(InventoryRecoveryIntent.REQUEST_INTEGRITY_REVIEW, result.intent)
        }
    }

    @Test
    fun deviceLossRoutesToManagedDeviceRecovery() {
        val result = requireNotNull(
            InventoryRecoveryContract.classify(
                event("QUARANTINED", "DEVICE_REVOKED", "HTTP_410"),
            ),
        )
        assertEquals(InventoryRecoverySeverity.BLOCKING, result.severity)
        assertEquals(InventoryRecoveryIntent.RECOVER_MANAGED_DEVICE, result.intent)
        assertEquals("HTTP_410", result.serverCode)
    }

    @Test
    fun operationalConflictRoutesToSupervisorThenBecomesWaitOnlyAfterCaseBinding() {
        val fresh = requireNotNull(
            InventoryRecoveryContract.classify(
                event("QUARANTINED", "BUSINESS_CONFLICT", "HTTP_409"),
            ),
        )
        assertEquals(InventoryRecoverySeverity.BLOCKING, fresh.severity)
        assertEquals(InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW, fresh.intent)

        val routed = requireNotNull(
            InventoryRecoveryContract.classify(
                event(
                    "QUARANTINED",
                    "BUSINESS_CONFLICT",
                    "HTTP_409",
                    recoveryCaseId = "33333333-3333-4333-8333-333333333333",
                    recoveryState = "REQUESTED",
                ),
            ),
        )
        assertEquals(InventoryRecoverySeverity.ATTENTION, routed.severity)
        assertEquals(InventoryRecoveryIntent.WAIT_FOR_SUPERVISOR_REVIEW, routed.intent)
    }

    @Test
    fun tenantAndLedgerMismatchesEscalateAboveBusinessConflicts() {
        val summary = requireNotNull(
            InventoryRecoveryContract.summarize(
                listOf(
                    event(
                        "QUARANTINED",
                        "BUSINESS_CONFLICT",
                        id = "11111111-1111-4111-8111-000000000001",
                    ),
                    event(
                        "QUARANTINED",
                        "TENANT_BINDING_CHANGED",
                        id = "11111111-1111-4111-8111-000000000002",
                    ),
                    event(
                        "RETRY_WAIT",
                        id = "11111111-1111-4111-8111-000000000003",
                    ),
                ),
            ),
        )
        assertEquals(InventoryRecoverySeverity.SECURITY, summary.severity)
        assertEquals(InventoryRecoveryIntent.REQUEST_SECURITY_REVIEW, summary.primaryIntent)
        assertEquals(3, summary.affectedEventCount)
        assertEquals(2, summary.quarantinedEventCount)
        assertEquals(1, summary.pendingEventCount)
    }

    @Test
    fun unknownLocalStateFailsClosedIntoIntegrityReview() {
        val result = requireNotNull(
            InventoryRecoveryContract.classify(event("MYSTERY_STATE")),
        )
        assertEquals(InventoryRecoverySeverity.SECURITY, result.severity)
        assertEquals(InventoryRecoveryIntent.REQUEST_INTEGRITY_REVIEW, result.intent)
        assertEquals("UNKNOWN_LOCAL_STATE", result.serverCode)
    }
}
