package com.eay.mobile.presentation

enum class FieldRuntimeSurface { EAY_ONE, EAY_TERMINAL }

enum class EayOneDestination { TODAY, MISSIONS, SCAN, JARVIS, ME }

data class EayOneNavigationModel(
    val selected: EayOneDestination,
    val pendingSyncCount: Int,
    val quarantined: Boolean,
) {
    init { require(pendingSyncCount >= 0) }
}

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
enum class FieldMissionDeadlineVisualState { NONE, ON_TRACK, DUE_SOON, OVERDUE }
enum class FieldSyncVisualState { SYNCED, OFFLINE, PENDING, QUARANTINED }
enum class FieldRecoveryVisualSeverity { INFO, ATTENTION, BLOCKING, SECURITY }

enum class FieldRecoveryActionKind {
    NONE,
    SIGN_IN_AGAIN,
    RELOAD_MISSIONS,
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
 * It intentionally cannot represent retry/delete/rebind/reassign/review mutations.
 * Durable evidence recovery is routed by the signed sync/recovery authority layer;
 * UI actions remain limited to fresh sign-in and read-only mission reload.
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
    /** Signed minutes until due; negative means overdue. Raw due timestamps never enter UI models. */
    val deadlineMinutes: Int? = null,
    val deadlineState: FieldMissionDeadlineVisualState = FieldMissionDeadlineVisualState.NONE,
    val estimatedMinutes: Int? = null,
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
        require(estimatedMinutes == null || estimatedMinutes > 0)
        require((deadlineMinutes == null) == (deadlineState == FieldMissionDeadlineVisualState.NONE)) {
            "Deadline minutes and visual state must be projected together"
        }
        when (deadlineState) {
            FieldMissionDeadlineVisualState.NONE -> Unit
            FieldMissionDeadlineVisualState.ON_TRACK -> require(requireNotNull(deadlineMinutes) > 15)
            FieldMissionDeadlineVisualState.DUE_SOON -> require(requireNotNull(deadlineMinutes) in 0..15)
            FieldMissionDeadlineVisualState.OVERDUE -> require(requireNotNull(deadlineMinutes) < 0)
        }
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

enum class FieldOperationalStepKind {
    SOURCE_LOCATION,
    DESTINATION_LOCATION,
    ITEM,
    QUANTITY,
    CONDITION,
    CONTAINER,
    COMPLETE,
}

/**
 * Render-only projection for the four physical workflows. Sensitive execution
 * context is intentionally absent; evidence admission remains outside presentation.
 */
data class OperationalExecutionUiState(
    val missionId: String,
    val kind: FieldMissionVisualKind,
    val title: String,
    val referenceLabel: String,
    val stepKind: FieldOperationalStepKind,
    val stepLabel: String,
    val instruction: String,
    val progressCurrent: Int,
    val progressTotal: Int,
    val quantityText: String = "",
    val confirmationLabel: String? = null,
    val syncState: FieldSyncVisualState,
    val primaryActionLabel: String,
    val primaryActionEnabled: Boolean,
) {
    init {
        require(missionId.isNotBlank())
        require(kind in setOf(
            FieldMissionVisualKind.PICK,
            FieldMissionVisualKind.PUTAWAY,
            FieldMissionVisualKind.RECEIVING,
            FieldMissionVisualKind.TRANSFER,
        ))
        require(title.isNotBlank())
        require(referenceLabel.isNotBlank())
        require(stepLabel.isNotBlank())
        require(instruction.isNotBlank())
        require(progressTotal > 0)
        require(progressCurrent in 0..progressTotal)
        require(primaryActionLabel.isNotBlank())
    }
}
