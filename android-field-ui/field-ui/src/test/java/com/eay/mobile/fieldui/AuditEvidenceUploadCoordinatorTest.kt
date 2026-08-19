package com.eay.mobile.fieldui

import java.io.InputStream
import java.nio.file.Files
import java.security.MessageDigest
import java.util.UUID
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class AuditEvidenceUploadCoordinatorTest {
    private fun fixture(): Pair<AuditRedactedEvidenceObject, ByteArray> {
        val bytes = "redacted-evidence".toByteArray()
        val path = Files.createTempFile("eay-audit-redacted-", ".jpg")
        path.toFile().writeBytes(bytes)
        val receipt = AuditRedactedEvidenceReceipt(
            localEvidenceId = UUID.randomUUID(),
            stepId = "entrance",
            sequence = 0,
            timestampMs = 1000,
            sha256 = sha256(bytes),
            byteCount = bytes.size.toLong(),
            mimeType = "image/jpeg",
            detectedFaceCount = 1,
            detectorModelRef = "privacy:model:v1",
            detectorModelSha256 = "a".repeat(64),
            detectorProvenanceRef = "github:source",
            detectorLicenseRef = "Apache-2.0",
        )
        return AuditRedactedEvidenceObject(receipt, path.toFile()) to bytes
    }

    @Test
    fun validServerAckDeletesSanitizedEvidence() {
        val (evidence, expectedBytes) = fixture()
        val coordinator = AuditEvidenceUploadCoordinator(
            object : AuditEvidenceUploadTransport {
                override fun upload(
                    request: AuditEvidenceUploadRequest,
                    content: InputStream,
                ): AuditEvidenceServerReceipt {
                    assertTrue(content.readBytes().contentEquals(expectedBytes))
                    return validAck(request)
                }
            },
        )

        coordinator.uploadAndAcknowledge(
            auditRunId = UUID.randomUUID(),
            fieldKey = "entrance_overview",
            evidence = evidence,
        )

        assertFalse(evidence.existsForTest())
    }

    @Test
    fun invalidServerAckKeepsSanitizedEvidenceForRetry() {
        val (evidence, _) = fixture()
        val coordinator = AuditEvidenceUploadCoordinator(
            object : AuditEvidenceUploadTransport {
                override fun upload(
                    request: AuditEvidenceUploadRequest,
                    content: InputStream,
                ): AuditEvidenceServerReceipt = validAck(request).copy(
                    visionInferenceAuthorized = true,
                )
            },
        )

        assertThrows(AuditEvidenceUploadReceiptException::class.java) {
            coordinator.uploadAndAcknowledge(
                auditRunId = UUID.randomUUID(),
                fieldKey = "entrance_overview",
                evidence = evidence,
            )
        }
        assertTrue(evidence.existsForTest())
        evidence.acknowledgeAndDelete()
    }

    @Test
    fun transportFailureKeepsSanitizedEvidenceForRetry() {
        val (evidence, _) = fixture()
        val coordinator = AuditEvidenceUploadCoordinator(
            object : AuditEvidenceUploadTransport {
                override fun upload(
                    request: AuditEvidenceUploadRequest,
                    content: InputStream,
                ): AuditEvidenceServerReceipt {
                    throw IllegalStateException("offline")
                }
            },
        )

        assertThrows(IllegalStateException::class.java) {
            coordinator.uploadAndAcknowledge(
                auditRunId = UUID.randomUUID(),
                fieldKey = "entrance_overview",
                evidence = evidence,
            )
        }
        assertTrue(evidence.existsForTest())
        evidence.acknowledgeAndDelete()
    }

    private fun validAck(request: AuditEvidenceUploadRequest): AuditEvidenceServerReceipt =
        AuditEvidenceServerReceipt(
            receiptId = UUID.randomUUID(),
            sha256 = request.sha256,
            byteSize = request.byteCount,
            mediaType = request.mimeType,
            redactedEvidenceRef = "field-evidence-receipt:${UUID.randomUUID()}",
            authority = "server_issued_private_evidence_receipt",
            clientRedactionClaimOnly = true,
            serverPrivacyVerified = false,
            visionInferenceAuthorized = false,
            publicUrl = null,
        )

    private fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { byte ->
            (byte.toInt() and 0xff).toString(16).padStart(2, '0')
        }
}
