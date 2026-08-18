package com.eay.mobile.fieldui

enum class FieldRuntimeSurface { EAY_ONE, EAY_TERMINAL }
enum class FieldMissionVisualKind { SHIFT, PICK, COUNT, PUTAWAY, RECEIVING, TRANSFER, PLANOGRAM, AUDIT, ACADEMY, JARVIS }
enum class FieldMissionVisualPriority { NORMAL, HIGH, URGENT }
enum class FieldSyncVisualState { SYNCED, OFFLINE, PENDING, QUARANTINED }

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

/** Deliberately contains observed field state only. System/expected stock is absent by contract. */
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
