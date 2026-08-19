package com.eay.mobile.fieldui

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AuditPrivacyContractTest {
    @Test
    fun rawMediaCannotEnterInference() {
        val raw = AuditPrivacyReceipt(
            privacyRedactionPassed = false,
            redactedMediaRef = null,
            sourceFingerprint = "sha256:source",
            capturedAt = "2026-08-19T19:48:00+03:00",
            locationRef = "location:test",
        )

        assertFalse(canStartAuditInference(raw))
    }

    @Test
    fun redactedEvidenceCanEnterInferenceWhenReceiptIsComplete() {
        val redacted = AuditPrivacyReceipt(
            privacyRedactionPassed = true,
            redactedMediaRef = "media:redacted:test",
            sourceFingerprint = "sha256:source",
            capturedAt = "2026-08-19T19:48:00+03:00",
            locationRef = "location:test",
        )

        assertTrue(canStartAuditInference(redacted))
    }

    @Test
    fun incompleteReceiptFailsClosed() {
        val incomplete = AuditPrivacyReceipt(
            privacyRedactionPassed = true,
            redactedMediaRef = "media:redacted:test",
            sourceFingerprint = null,
            capturedAt = "2026-08-19T19:48:00+03:00",
            locationRef = "location:test",
        )

        assertFalse(canStartAuditInference(incomplete))
    }
}
