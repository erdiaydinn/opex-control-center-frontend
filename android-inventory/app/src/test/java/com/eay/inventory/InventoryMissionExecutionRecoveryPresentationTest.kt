package com.eay.inventory

import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldRecoveryVisualSeverity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class InventoryMissionExecutionRecoveryPresentationTest {
    @Test
    fun `successful claim has no recovery surface`() {
        assertNull(
            InventoryMissionExecutionRecoveryPresentation.claimPolicy(
                InventoryMissionClaimCode.OK,
            ),
        )
    }

    @Test
    fun `expired authentication re-enters corporate sign in only`() {
        val policy = requireNotNull(
            InventoryMissionExecutionRecoveryPresentation.claimPolicy(
                InventoryMissionClaimCode.AUTH_REQUIRED,
            ),
        )
        assertEquals(FieldRecoveryVisualSeverity.BLOCKING, policy.severity)
        assertEquals(FieldRecoveryActionKind.SIGN_IN_AGAIN, policy.actionKind)
    }

    @Test
    fun `retry and claim conflict only reload server missions`() {
        listOf(
            InventoryMissionClaimCode.RETRYABLE,
            InventoryMissionClaimCode.BUSINESS_CONFLICT,
        ).forEach { code ->
            val policy = requireNotNull(
                InventoryMissionExecutionRecoveryPresentation.claimPolicy(code),
            )
            assertEquals(FieldRecoveryActionKind.RELOAD_MISSIONS, policy.actionKind)
        }
    }

    @Test
    fun `device and authority rejection expose no client recovery mutation`() {
        listOf(
            InventoryMissionClaimCode.DEVICE_REJECTED,
            InventoryMissionClaimCode.POLICY_REJECTED,
            InventoryMissionClaimCode.CONTRACT_REJECTED,
            InventoryMissionClaimCode.PERMANENT_REJECTED,
        ).forEach { code ->
            val policy = requireNotNull(
                InventoryMissionExecutionRecoveryPresentation.claimPolicy(code),
            )
            assertEquals(FieldRecoveryActionKind.NONE, policy.actionKind)
        }
    }

    @Test
    fun `expired lease requires fresh mission reload not client lease extension`() {
        val policy = InventoryMissionExecutionRecoveryPresentation.leaseExpiredPolicy()
        assertEquals(FieldRecoveryVisualSeverity.ATTENTION, policy.severity)
        assertEquals(FieldRecoveryActionKind.RELOAD_MISSIONS, policy.actionKind)
    }
}
