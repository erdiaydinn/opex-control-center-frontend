package com.eay.mobile.fieldui

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AuditPrivacyContractTest {
    private val sourceFingerprint = "a".repeat(64)
    private val verificationFingerprint = "b".repeat(64)

    private fun receipt(
        privacyRedactionPassed: Boolean = true,
        processedFrames: Long = 90,
        serverPrivacyVerified: Boolean = false,
        serverVerifierRef: String? = null,
        serverVerificationFingerprint: String? = null,
    ) = AuditPrivacyReceipt(
        privacyRedactionPassed = privacyRedactionPassed,
        redactedMediaRef = "media:redacted:test",
        sourceFingerprint = sourceFingerprint,
        capturedAt = "2026-08-19T19:48:00+03:00",
        locationRef = "location:test",
        privacyPolicyVersion = "audit-privacy-v1",
        detectorModelRef = "mediapipe:face-detector:reviewed",
        frameCount = 90,
        processedFrameCount = processedFrames,
        serverPrivacyVerified = serverPrivacyVerified,
        serverVerifierRef = serverVerifierRef,
        serverVerificationFingerprint = serverVerificationFingerprint,
    )

    @Test
    fun rawMediaCannotBeUploadedOrEnterInference() {
        val raw = receipt(privacyRedactionPassed = false)

        assertFalse(canUploadRedactedAuditEvidence(raw))
        assertFalse(canStartAuditInference(raw))
    }

    @Test
    fun localRedactionReceiptCanUploadButCannotStartGovernedInference() {
        val localOnly = receipt()

        assertTrue(canUploadRedactedAuditEvidence(localOnly))
        assertFalse(canStartAuditInference(localOnly))
    }

    @Test
    fun serverVerifiedRedactedEvidenceCanEnterInference() {
        val verified = receipt(
            serverPrivacyVerified = true,
            serverVerifierRef = "privacy-verifier:eay:v1",
            serverVerificationFingerprint = verificationFingerprint,
        )

        assertTrue(canUploadRedactedAuditEvidence(verified))
        assertTrue(canStartAuditInference(verified))
    }

    @Test
    fun incompleteCanonicalFrameCoverageFailsClosed() {
        val incomplete = receipt(processedFrames = 89)

        assertFalse(canUploadRedactedAuditEvidence(incomplete))
        assertFalse(canStartAuditInference(incomplete))
    }

    @Test
    fun serverVerificationNeedsCanonicalFingerprint() {
        val invalid = receipt(
            serverPrivacyVerified = true,
            serverVerifierRef = "privacy-verifier:eay:v1",
            serverVerificationFingerprint = "not-a-sha256",
        )

        assertFalse(canStartAuditInference(invalid))
    }
}
