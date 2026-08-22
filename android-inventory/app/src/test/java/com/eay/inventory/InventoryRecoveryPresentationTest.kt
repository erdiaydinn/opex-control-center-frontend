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
            InventoryRecoveryIntent.WAIT_FOR_SUPERVISOR_REVIEW -> InventoryRecoverySeverity.ATTENTION
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
    fun supervisorRoutingDoesNotExposeMutationActionOrGloballyStopUnrelatedMissions() {
        listOf(
            InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW,
            InventoryRecoveryIntent.WAIT_FOR_SUPERVISOR_REVIEW,
        ).forEach { intent ->
            val policy = InventoryRecoveryPresentation.policy(summary(intent))
            assertFalse(policy.blocksNewMissionStarts)
            assertEquals(FieldRecoveryActionKind.NONE, policy.actionKind)
            assertEquals(null, policy.actionLabelRes)
        }
    }

    @Test
    fun routedSupervisorCaseBecomesAttentionNotFalseSuccess() {
        val policy = InventoryRecoveryPresentation.policy(
            summary(InventoryRecoveryIntent.WAIT_FOR_SUPERVISOR_REVIEW),
        )
        assertEquals(FieldRecoveryVisualSeverity.ATTENTION, policy.severity)
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

    @Test
    fun unsupportedDurableUiIntentsBecomeIntegrityBlockWithoutAction() {
        listOf(
            InventoryRecoveryIntent.SIGN_IN_AGAIN,
            InventoryRecoveryIntent.RELOAD_MISSIONS,
            InventoryRecoveryIntent.NONE,
        ).forEach { intent ->
            val policy = InventoryRecoveryPresentation.policy(summary(intent))
            assertEquals(FieldRecoveryVisualSeverity.SECURITY, policy.severity)
            assertTrue(policy.blocksNewMissionStarts)
            assertEquals(FieldRecoveryActionKind.NONE, policy.actionKind)
        }
    }
}
