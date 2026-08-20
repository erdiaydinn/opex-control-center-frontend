package com.eay.mobile.presentation

enum class FieldRuntimeSurface { EAY_ONE, EAY_TERMINAL }

enum class FieldMissionVisualKind {
    SHIFT,
    PICK,
    COUNT,
    PUTAWAY,
    RECEIVING,
    TRANSFER,
    PLANOGRAM,
    AUDIT,
    ACADEMY,
    JARVIS,
}

enum class FieldMissionVisualPriority { LOW, NORMAL, HIGH, URGENT }
enum class FieldSyncVisualState { SYNCED, OFFLINE, PENDING, QUARANTINED }
enum class FieldRecoveryVisualSeverity { INFO, ATTENTION, BLOCKING, SECURITY }

enum class FieldRecoveryActionKind {
    NONE,
    SIGN_IN_AGAIN,
    RELOAD_MISSIONS,
    /** Opens a signed server-side review case; never retries or mutates evidence. */
    REQUEST_SUPERVISOR_REVIEW,
}

data class FieldShellHeader(
    val locationLabel: String,
    val deviceLabel: String,
    val runtimeSurface: FieldRuntimeSurface,
    val syncState: FieldSyncVisualState,
    val pendingCount: Int,
) {
    init {
        require(locationLabel.isNotBlank())
        require(deviceLabel.isNotBlank())
        require(pendingCount >= 0)
    }
}

/**
 * Presentation-only recovery explanation for durable evidence.
 *
 * It intentionally cannot represent retry/delete/rebind/reassign mutations. Only
 * bounded local UI intents that must re-enter existing authority paths are representable.
 */
data class FieldRecoveryBannerModel(
    val severity: FieldRecoveryVisualSeverity,
    val title: String,
    val message: String,
    val affectedEventCount: Int,
    val actionKind: FieldRecoveryActionKind = FieldRecoveryActionKind.NONE,
    val actionLabel: String? = null,
) {
    init {
        require(title.isNotBlank())
        require(message.isNotBlank())
        require(affectedEventCount > 0)
        require((actionKind == FieldRecoveryActionKind.NONE) == actionLabel.isNullOrBlank()) {
            "Recovery action kind and label must either both be absent or both be present"
        }
    }
}

/**
 * Presentation-only recovery for session/read-only mission discovery failures.
 *
 * This is deliberately a different type from durable-evidence recovery: it carries
 * no event count or evidence identity and can only request a fresh sign-in or a
 * read-only mission reload. It cannot retry, mutate, delete or rebind queued events.
 */
data class FieldSessionRecoveryBannerModel(
    val severity: FieldRecoveryVisualSeverity,
    val title: String,
    val message: String,
    val actionKind: FieldRecoveryActionKind = FieldRecoveryActionKind.NONE,
    val actionLabel: String? = null,
) {
    init {
        require(title.isNotBlank())
        require(message.isNotBlank())
        require(actionKind in setOf(
            FieldRecoveryActionKind.NONE,
            FieldRecoveryActionKind.SIGN_IN_AGAIN,
            FieldRecoveryActionKind.RELOAD_MISSIONS,
        ))
        require((actionKind == FieldRecoveryActionKind.NONE) == actionLabel.isNullOrBlank()) {
            "Session recovery action kind and label must either both be absent or both be present"
        }
    }
}

data class FieldMissionCardModel(
    val missionId: String,
    val title: String,
    val subtitle: String,
    val kind: FieldMissionVisualKind,
    val priority: FieldMissionVisualPriority,
    val progressCurrent: Int? = null,
    val progressTotal: Int? = null,
    val primaryActionLabel: String,
    val enabled: Boolean,
) {
    init {
        require(missionId.isNotBlank())
        require(title.isNotBlank())
        require(primaryActionLabel.isNotBlank())
        require(progressCurrent == null || progressCurrent >= 0)
        require(progressTotal == null || progressTotal > 0)
        require(progressCurrent == null || progressTotal == null || progressCurrent <= progressTotal)
    }
}

/** Presentation-safe blind-count state. Expected/system stock is intentionally impossible to represent. */
data class BlindCountUiState(
    val missionId: String,
    val locationLabel: String,
    val stepLabel: String,
    val scannedItemLabel: String?,
    val observedQuantityText: String,
    val confirmedLines: Int,
    val totalLines: Int?,
    val syncState: FieldSyncVisualState,
) {
    init {
        require(missionId.isNotBlank())
        require(locationLabel.isNotBlank())
        require(stepLabel.isNotBlank())
        require(confirmedLines >= 0)
        require(totalLines == null || totalLines > 0)
        require(totalLines == null || confirmedLines <= totalLines)
    }
}
