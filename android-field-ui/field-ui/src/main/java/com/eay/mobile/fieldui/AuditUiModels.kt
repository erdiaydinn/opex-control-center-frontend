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

/**
 * Fail-closed mobile boundary: audit inference cannot start with raw or unproven media.
 * This contract intentionally does not perform identity recognition.
 */
fun canStartAuditInference(receipt: AuditPrivacyReceipt?): Boolean {
    if (receipt == null) return false
    if (!receipt.privacyRedactionPassed) return false
    if (receipt.redactedMediaRef.isNullOrBlank()) return false
    if (receipt.sourceFingerprint.isNullOrBlank()) return false
    if (receipt.capturedAt.isNullOrBlank()) return false
    if (receipt.locationRef.isNullOrBlank()) return false
    return true
}
