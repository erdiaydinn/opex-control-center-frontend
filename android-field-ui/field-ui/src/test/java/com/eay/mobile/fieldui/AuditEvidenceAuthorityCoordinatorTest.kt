package com.eay.mobile.fieldui

import java.util.UUID
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class AuditEvidenceAuthorityCoordinatorTest {
    private val runId = UUID.randomUUID()
    private val fieldReceiptId = UUID.randomUUID()
    private val redactionId = UUID.randomUUID()

    private fun request(): AuditEvidenceBindingRequest =
        AuditEvidenceBindingRequest(
            auditRunId = runId,
            fieldEvidenceReceiptId = fieldReceiptId,
            sourceFingerprint = "a".repeat(64),
            privacyPolicyVersion = "audit-privacy-v1",
            detectorModelRef = "privacy:model:v1",
            deviceId = "device-123",
        )

    private fun binding(): AuditEvidenceBindingReceipt =
        AuditEvidenceBindingReceipt(
            redactionReceiptId = redactionId,
            fieldEvidenceReceiptId = fieldReceiptId,
            redactedObjectHashVerified = true,
            sourceFingerprintVerified = false,
            clientRedactionClaimOnly = true,
            serverPrivacyVerified = false,
            visionInferenceAuthorized = false,
        )

    private fun privacy(status: String = "verified"): AuditServerPrivacyReceipt {
        val verified = status == "verified"
        return AuditServerPrivacyReceipt(
            verificationEventId = UUID.randomUUID(),
            redactionReceiptId = redactionId,
            fieldEvidenceReceiptId = fieldReceiptId,
            verificationStatus = status,
            verificationAuthorityVersion = "server_privacy_v2",
            verificationFingerprint = "b".repeat(64),
            privacyGatePassed = verified,
            serverPrivacyVerified = verified,
            visionInferenceAuthorized = false,
        )
    }

    @Test
    fun validServerBindingAndPrivacyReceiptsAreDurablyCommittedInOrder() {
        val commits = mutableListOf<String>()
        val coordinator = AuditEvidenceAuthorityCoordinator(
            transport = object : AuditEvidenceAuthorityTransport {
                override fun bindEvidence(
                    request: AuditEvidenceBindingRequest,
                ): AuditEvidenceBindingReceipt = binding()

                override fun verifyServerPrivacy(
                    auditRunId: UUID,
                    redactionReceiptId: UUID,
                ): AuditServerPrivacyReceipt {
                    assertEquals(runId, auditRunId)
                    assertEquals(redactionId, redactionReceiptId)
                    return privacy()
                }
            },
            committer = object : AuditEvidenceAuthorityCommitter {
                override fun commitBinding(
                    request: AuditEvidenceBindingRequest,
                    receipt: AuditEvidenceBindingReceipt,
                ) {
                    commits += "binding"
                }

                override fun commitPrivacyVerification(receipt: AuditServerPrivacyReceipt) {
                    commits += "privacy"
                }
            },
        )

        val result = coordinator.bindAndVerify(request())

        assertEquals(listOf("binding", "privacy"), commits)
        assertTrue(result.privacy.serverPrivacyVerified)
        assertTrue(result.privacy.privacyGatePassed)
        assertFalse(result.privacy.visionInferenceAuthorized)
    }

    @Test
    fun bindingCannotElevateClientSourceFingerprintOrVisionAuthority() {
        val invalid = binding().copy(sourceFingerprintVerified = true)
        val coordinator = coordinator(bindingReceipt = invalid)

        assertThrows(AuditEvidenceAuthorityException::class.java) {
            coordinator.bindAndVerify(request())
        }
    }

    @Test
    fun privacyReceiptMustNotGrantVisionAuthority() {
        val invalid = privacy().copy(visionInferenceAuthorized = true)
        val coordinator = coordinator(privacyReceipt = invalid)

        assertThrows(AuditEvidenceAuthorityException::class.java) {
            coordinator.bindAndVerify(request())
        }
    }

    @Test
    fun blockedPrivacyIsValidEvidenceStateButNeverServerVerified() {
        val coordinator = coordinator(privacyReceipt = privacy(status = "blocked"))

        val result = coordinator.bindAndVerify(request())

        assertEquals("blocked", result.privacy.verificationStatus)
        assertFalse(result.privacy.privacyGatePassed)
        assertFalse(result.privacy.serverPrivacyVerified)
    }

    private fun coordinator(
        bindingReceipt: AuditEvidenceBindingReceipt = binding(),
        privacyReceipt: AuditServerPrivacyReceipt = privacy(),
    ): AuditEvidenceAuthorityCoordinator =
        AuditEvidenceAuthorityCoordinator(
            transport = object : AuditEvidenceAuthorityTransport {
                override fun bindEvidence(
                    request: AuditEvidenceBindingRequest,
                ): AuditEvidenceBindingReceipt = bindingReceipt

                override fun verifyServerPrivacy(
                    auditRunId: UUID,
                    redactionReceiptId: UUID,
                ): AuditServerPrivacyReceipt = privacyReceipt
            },
            committer = object : AuditEvidenceAuthorityCommitter {
                override fun commitBinding(
                    request: AuditEvidenceBindingRequest,
                    receipt: AuditEvidenceBindingReceipt,
                ) = Unit

                override fun commitPrivacyVerification(receipt: AuditServerPrivacyReceipt) = Unit
            },
        )
}
