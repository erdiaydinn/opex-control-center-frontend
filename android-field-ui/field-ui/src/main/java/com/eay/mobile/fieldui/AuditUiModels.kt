package com.eay.mobile.fieldui

enum class AuditPrivacyState {
    PENDING,
    REDACTING,
    PASSED,
    BLOCKED,
}

enum class AuditCaptureStepState {
    UPCOMING,
    ACTIVE,
    CAPTURED,
    REVIEW_REQUIRED,
}

data class AuditCaptureStep(
    val stepId: String,
    val title: String,
    val hint: String,
    val state: AuditCaptureStepState,
    val evidenceCount: Int = 0,
)

data class AuditPrivacyReceipt(
    val privacyRedactionPassed: Boolean,
    val redactedMediaRef: String?,
    val sourceFingerprint: String?,
    val capturedAt: String?,
    val locationRef: String?,
    val privacyPolicyVersion: String?,
    val detectorModelRef: String?,
    val frameCount: Long,
    val processedFrameCount: Long,
    val serverPrivacyVerified: Boolean = false,
    val serverVerifierRef: String? = null,
    val serverVerificationFingerprint: String? = null,
)

data class AuditMobileCopy(
    val productName: String,
    val title: String,
    val subtitle: String,
    val todayLabel: String,
    val startVideoAuditLabel: String,
    val continueLabel: String,
    val privacyTitle: String,
    val privacyPassedLabel: String,
    val privacyPendingLabel: String,
    val privacyBlockedLabel: String,
    val guidedCaptureTitle: String,
    val guidedCaptureSubtitle: String,
    val evidenceLabel: String,
    val actionsLabel: String,
    val auditsLabel: String,
    val homeLabel: String,
)

data class AuditMobileHomeState(
    val locationLabel: String,
    val userLabel: String,
    val activeAuditTitle: String?,
    val activeAuditProgress: Float = 0f,
    val openActionCount: Int = 0,
    val privacyState: AuditPrivacyState = AuditPrivacyState.PENDING,
    val captureSteps: List<AuditCaptureStep> = emptyList(),
)

private val SHA256_HEX = Regex("^[0-9a-f]{64}$")

private fun clientRedactionReceiptIsComplete(receipt: AuditPrivacyReceipt?): Boolean {
    if (receipt == null) return false
    if (!receipt.privacyRedactionPassed) return false
    if (receipt.redactedMediaRef.isNullOrBlank()) return false
    if (receipt.sourceFingerprint.isNullOrBlank() || !SHA256_HEX.matches(receipt.sourceFingerprint)) {
        return false
    }
    if (receipt.capturedAt.isNullOrBlank()) return false
    if (receipt.locationRef.isNullOrBlank()) return false
    if (receipt.privacyPolicyVersion.isNullOrBlank()) return false
    if (receipt.detectorModelRef.isNullOrBlank()) return false
    if (receipt.frameCount <= 0L) return false
    if (receipt.processedFrameCount != receipt.frameCount) return false
    return true
}

/**
 * A complete local redaction receipt may be uploaded to the server for privacy verification.
 * It is still not governed AI authority.
 */
fun canUploadRedactedAuditEvidence(receipt: AuditPrivacyReceipt?): Boolean =
    clientRedactionReceiptIsComplete(receipt)

/**
 * Fail-closed governed inference boundary.
 *
 * Local face redaction is necessary but not sufficient. The server must independently verify
 * the privacy receipt and return a verifier/fingerprint authority before canonical Audit AI can
 * consume the evidence. This contract never performs identity recognition.
 */
fun canStartAuditInference(receipt: AuditPrivacyReceipt?): Boolean {
    if (!clientRedactionReceiptIsComplete(receipt)) return false
    checkNotNull(receipt)
    if (!receipt.serverPrivacyVerified) return false
    if (receipt.serverVerifierRef.isNullOrBlank()) return false
    if (
        receipt.serverVerificationFingerprint.isNullOrBlank() ||
        !SHA256_HEX.matches(receipt.serverVerificationFingerprint)
    ) {
        return false
    }
    return true
}
