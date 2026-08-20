package com.eay.mobile.fieldui

import java.util.UUID

private val SHA256_HEX = Regex("^[0-9a-f]{64}$")

data class AuditEvidenceBindingRequest(
    val auditRunId: UUID,
    val fieldEvidenceReceiptId: UUID,
    val sourceFingerprint: String,
    val privacyPolicyVersion: String,
    val detectorModelRef: String,
    val deviceId: String?,
) {
    init {
        require(sourceFingerprint.matches(SHA256_HEX)) {
            "sourceFingerprint must be lowercase SHA-256"
        }
        require(privacyPolicyVersion.isNotBlank() && privacyPolicyVersion.length <= 80) {
            "privacyPolicyVersion is invalid"
        }
        require(detectorModelRef.isNotBlank() && detectorModelRef.length <= 300) {
            "detectorModelRef is invalid"
        }
        require(deviceId == null || deviceId.length <= 180) { "deviceId is invalid" }
    }
}

data class AuditEvidenceBindingReceipt(
    val redactionReceiptId: UUID,
    val fieldEvidenceReceiptId: UUID,
    val redactedObjectHashVerified: Boolean,
    val sourceFingerprintVerified: Boolean,
    val clientRedactionClaimOnly: Boolean,
    val serverPrivacyVerified: Boolean,
    val visionInferenceAuthorized: Boolean,
)

data class AuditServerPrivacyReceipt(
    val verificationEventId: UUID,
    val redactionReceiptId: UUID,
    val fieldEvidenceReceiptId: UUID,
    val verificationStatus: String,
    val verificationAuthorityVersion: String,
    val verificationFingerprint: String,
    val privacyGatePassed: Boolean,
    val serverPrivacyVerified: Boolean,
    val visionInferenceAuthorized: Boolean,
) {
    init {
        require(verificationStatus in setOf("verified", "rejected", "blocked", "tampered")) {
            "verificationStatus is invalid"
        }
        require(verificationFingerprint.matches(SHA256_HEX)) {
            "verificationFingerprint must be lowercase SHA-256"
        }
    }
}

interface AuditEvidenceAuthorityTransport {
    /** POST /v1/audit/runs/{run}/redaction-receipts using the host auth/session stack. */
    fun bindEvidence(request: AuditEvidenceBindingRequest): AuditEvidenceBindingReceipt

    /**
     * POST /v1/audit/runs/{run}/redaction-receipts/{receipt}/server-privacy-verifications.
     * The request carries no client-selected verification/model authority fields.
     */
    fun verifyServerPrivacy(
        auditRunId: UUID,
        redactionReceiptId: UUID,
    ): AuditServerPrivacyReceipt
}

interface AuditEvidenceAuthorityCommitter {
    /** Persist binding receipt before crossing the next network boundary. */
    fun commitBinding(
        request: AuditEvidenceBindingRequest,
        receipt: AuditEvidenceBindingReceipt,
    )

    /** Persist the append-only server privacy event for offline/retry continuity. */
    fun commitPrivacyVerification(receipt: AuditServerPrivacyReceipt)
}

class AuditEvidenceAuthorityException(message: String) : IllegalStateException(message)

data class AuditEvidenceAuthorityResult(
    val binding: AuditEvidenceBindingReceipt,
    val privacy: AuditServerPrivacyReceipt,
)

/**
 * Continues a durable private-storage ACK into server-owned Audit evidence authority.
 *
 * This coordinator cannot mark evidence verified itself. It validates that the storage binding
 * remains client-claim-only and that the privacy result is internally self-consistent. Vision,
 * finding and action authority stay outside this mobile module.
 */
class AuditEvidenceAuthorityCoordinator(
    private val transport: AuditEvidenceAuthorityTransport,
    private val committer: AuditEvidenceAuthorityCommitter,
) {
    fun bindAndVerify(request: AuditEvidenceBindingRequest): AuditEvidenceAuthorityResult {
        val binding = transport.bindEvidence(request)
        validateBinding(request, binding)
        committer.commitBinding(request, binding)

        val privacy = transport.verifyServerPrivacy(
            auditRunId = request.auditRunId,
            redactionReceiptId = binding.redactionReceiptId,
        )
        validatePrivacy(binding, privacy)
        committer.commitPrivacyVerification(privacy)
        return AuditEvidenceAuthorityResult(binding = binding, privacy = privacy)
    }

    private fun validateBinding(
        request: AuditEvidenceBindingRequest,
        binding: AuditEvidenceBindingReceipt,
    ) {
        if (binding.fieldEvidenceReceiptId != request.fieldEvidenceReceiptId) {
            throw AuditEvidenceAuthorityException("Audit binding changed the Field receipt identity")
        }
        if (!binding.redactedObjectHashVerified) {
            throw AuditEvidenceAuthorityException("Audit binding did not verify stored object integrity")
        }
        if (binding.sourceFingerprintVerified) {
            throw AuditEvidenceAuthorityException(
                "Client source provenance must not be elevated to server verification",
            )
        }
        if (!binding.clientRedactionClaimOnly) {
            throw AuditEvidenceAuthorityException("Audit binding lost client-redaction-claim boundary")
        }
        if (binding.serverPrivacyVerified || binding.visionInferenceAuthorized) {
            throw AuditEvidenceAuthorityException(
                "Binding receipt must not claim server privacy or vision authority",
            )
        }
    }

    private fun validatePrivacy(
        binding: AuditEvidenceBindingReceipt,
        privacy: AuditServerPrivacyReceipt,
    ) {
        if (privacy.redactionReceiptId != binding.redactionReceiptId) {
            throw AuditEvidenceAuthorityException("Privacy receipt changed redaction identity")
        }
        if (privacy.fieldEvidenceReceiptId != binding.fieldEvidenceReceiptId) {
            throw AuditEvidenceAuthorityException("Privacy receipt changed Field evidence identity")
        }
        if (privacy.verificationAuthorityVersion != "server_privacy_v2") {
            throw AuditEvidenceAuthorityException("Unsupported server privacy authority version")
        }
        val verified = privacy.verificationStatus == "verified"
        if (privacy.privacyGatePassed != verified || privacy.serverPrivacyVerified != verified) {
            throw AuditEvidenceAuthorityException("Server privacy receipt is internally inconsistent")
        }
        if (privacy.visionInferenceAuthorized) {
            throw AuditEvidenceAuthorityException(
                "Privacy receipt must not grant downstream vision authority",
            )
        }
    }
}
