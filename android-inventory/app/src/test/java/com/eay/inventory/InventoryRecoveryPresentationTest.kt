package com.eay.inventory

import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldRecoveryVisualSeverity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryRecoveryPresentationTest {
    private fun summary(intent: InventoryRecoveryIntent) = InventoryRecoverySummary(
        severity = when (intent) {
            InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY -> InventoryRecoverySeverity.INFO
            InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW,
            InventoryRecoveryIntent.RECOVER_MANAGED_DEVICE,
            -> InventoryRecoverySeverity.BLOCKING
            else -> InventoryRecoverySeverity.SECURITY
        },
        primaryIntent = intent,
        affectedEventCount = 2,
        quarantinedEventCount = if (intent == InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY) 0 else 2,
        pendingEventCount = if (intent == InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY) 2 else 0,
    )

    @Test
    fun pendingSyncDoesNotBlockNewMissionStarts() {
        val policy = InventoryRecoveryPresentation.policy(
            summary(InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY),
        )
        assertEquals(FieldRecoveryVisualSeverity.INFO, policy.severity)
        assertFalse(policy.blocksNewMissionStarts)
        assertEquals(FieldRecoveryActionKind.NONE, policy.actionKind)
    }

    @Test
    fun supervisorReviewDoesNotGloballyStopUnrelatedMissions() {
        val policy = InventoryRecoveryPresentation.policy(
            summary(InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW),
        )
        assertEquals(FieldRecoveryVisualSeverity.BLOCKING, policy.severity)
        assertFalse(policy.blocksNewMissionStarts)
    }

    @Test
    fun deviceSecurityAndIntegrityFailuresBlockNewMissionStarts() {
        listOf(
            InventoryRecoveryIntent.RECOVER_MANAGED_DEVICE,
            InventoryRecoveryIntent.REQUEST_SECURITY_REVIEW,
            InventoryRecoveryIntent.REQUEST_INTEGRITY_REVIEW,
        ).forEach { intent ->
            assertTrue(
                InventoryRecoveryPresentation.policy(summary(intent)).blocksNewMissionStarts,
            )
        }
    }

    @Test(expected = IllegalStateException::class)
    fun durableEvidenceCannotInventSignInRecovery() {
        InventoryRecoveryPresentation.policy(summary(InventoryRecoveryIntent.SIGN_IN_AGAIN))
    }
}
