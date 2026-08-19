package com.eay.mobile.presentation.adapter

import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldRecoveryVisualSeverity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class SessionRecoveryPresentationAdapterTest {
    @Test
    fun `session recovery exposes sign in without durable evidence fields`() {
        val banner = SessionRecoveryPresentationAdapter.banner(
            SessionRecoveryPresentationIntent(
                severity = FieldRecoveryVisualSeverity.BLOCKING,
                title = "Session required",
                message = "Authenticate again",
                actionKind = FieldRecoveryActionKind.SIGN_IN_AGAIN,
                actionLabel = "Sign in again",
            ),
        )

        assertEquals(FieldRecoveryActionKind.SIGN_IN_AGAIN, banner.actionKind)
        assertEquals("Sign in again", banner.actionLabel)
    }

    @Test
    fun `session recovery exposes read only mission reload`() {
        val banner = SessionRecoveryPresentationAdapter.banner(
            SessionRecoveryPresentationIntent(
                severity = FieldRecoveryVisualSeverity.ATTENTION,
                title = "Connection unavailable",
                message = "Mission discovery can be retried",
                actionKind = FieldRecoveryActionKind.RELOAD_MISSIONS,
                actionLabel = "Reload missions",
            ),
        )

        assertEquals(FieldRecoveryActionKind.RELOAD_MISSIONS, banner.actionKind)
    }

    @Test
    fun `action kind cannot exist without a visible action label`() {
        assertThrows(IllegalArgumentException::class.java) {
            SessionRecoveryPresentationAdapter.banner(
                SessionRecoveryPresentationIntent(
                    severity = FieldRecoveryVisualSeverity.BLOCKING,
                    title = "Blocked",
                    message = "No implicit action",
                    actionKind = FieldRecoveryActionKind.SIGN_IN_AGAIN,
                    actionLabel = null,
                ),
            )
        }
    }
}
