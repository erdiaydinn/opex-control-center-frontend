package com.eay.mobile.fieldui

import java.io.InputStream
import java.util.UUID


data class AuditEvidenceUploadRequest(
    val auditRunId: UUID,
    val fieldKey: String,
    val clientSubmissionId: UUID,
    val sha256: String,
    val byteCount: Long,
    val mimeType: String,
) {
    init {
        require(fieldKey.isNotBlank()) { "fieldKey must not be blank" }
        require(sha256.matches(Regex("^[0-9a-f]{64}$"))) { "sha256 must be lowercase SHA-256" }
        require(byteCount > 0L) { "byteCount must be positive" }
        require(mimeType == "image/jpeg") {
            "Audit redacted evidence upload currently requires image/jpeg"
        }
    }
}

data class AuditEvidenceServerReceipt(
    val receiptId: UUID,
    val sha256: String,
    val byteSize: Long,
    val mediaType: String,
    val redactedEvidenceRef: String,
    val authority: String,
    val clientRedactionClaimOnly: Boolean,
    val serverPrivacyVerified: Boolean,
    val visionInferenceAuthorized: Boolean,
    val publicUrl: String?,
)

interface AuditEvidenceUploadTransport {
    fun upload(
        request: AuditEvidenceUploadRequest,
        content: InputStream,
    ): AuditEvidenceServerReceipt
}

/**
 * Host-owned durable storage boundary for the server-issued evidence receipt.
 *
 * The Field UI module deliberately does not implement its own database/auth stack. Production host
 * code must atomically persist enough receipt/request state to retry Audit binding after process or
 * network failure. If this commit fails, sanitized evidence stays device-private for retry.
 */
interface AuditEvidenceReceiptCommitter {
    fun commit(
        request: AuditEvidenceUploadRequest,
        receipt: AuditEvidenceServerReceipt,
    )
}

class AuditEvidenceUploadReceiptException(message: String) : IllegalStateException(message)

/**
 * Uploads only sanitized evidence objects and deletes them only after strict server + durable ACK.
 *
 * The coordinator cannot accept AuditRawVideoCapture, so raw video cannot accidentally be routed
 * through the evidence transport. Authentication, HTTP and durable queue implementations remain
 * owned by the host mobile platform; this module deliberately does not create parallel stacks.
 */
class AuditEvidenceUploadCoordinator(
    private val transport: AuditEvidenceUploadTransport,
    private val receiptCommitter: AuditEvidenceReceiptCommitter,
) {
    fun uploadAndAcknowledge(
        auditRunId: UUID,
        fieldKey: String,
        evidence: AuditRedactedEvidenceObject,
    ): AuditEvidenceServerReceipt {
        val local = evidence.receipt
        val request = AuditEvidenceUploadRequest(
            auditRunId = auditRunId,
            fieldKey = fieldKey,
            clientSubmissionId = local.localEvidenceId,
            sha256 = local.sha256,
            byteCount = local.byteCount,
            mimeType = local.mimeType,
        )

        val server = evidence.readForGovernedUpload { input ->
            transport.upload(request, input)
        }
        validateServerAck(local, server)
        receiptCommitter.commit(request, server)
        evidence.acknowledgeAndDelete()
        return server
    }

    private fun validateServerAck(
        local: AuditRedactedEvidenceReceipt,
        server: AuditEvidenceServerReceipt,
    ) {
        if (server.sha256 != local.sha256) {
            throw AuditEvidenceUploadReceiptException(
                "Server evidence SHA-256 does not match local evidence",
            )
        }
        if (server.byteSize != local.byteCount) {
            throw AuditEvidenceUploadReceiptException(
                "Server evidence byte size does not match local evidence",
            )
        }
        if (server.mediaType != local.mimeType) {
            throw AuditEvidenceUploadReceiptException(
                "Server evidence media type does not match local evidence",
            )
        }
        if (server.redactedEvidenceRef.isBlank()) {
            throw AuditEvidenceUploadReceiptException("Server evidence reference is missing")
        }
        if (server.authority != "server_issued_private_evidence_receipt") {
            throw AuditEvidenceUploadReceiptException("Server evidence authority is invalid")
        }
        if (!server.clientRedactionClaimOnly) {
            throw AuditEvidenceUploadReceiptException(
                "Server must preserve client-redaction-claim boundary",
            )
        }
        if (server.serverPrivacyVerified || server.visionInferenceAuthorized) {
            throw AuditEvidenceUploadReceiptException(
                "Storage ACK must not claim privacy verification or vision authority",
            )
        }
        if (server.publicUrl != null) {
            throw AuditEvidenceUploadReceiptException(
                "Private evidence receipt must not expose a public URL",
            )
        }
    }
}
