package com.eay.mobile.presentation

/** Presentation-only summary used by EAY One Today. */
data class EayOneHomeSummaryUiState(
    val title: String,
    val supportingText: String,
    val shiftLabel: String,
    val shiftValue: String,
    val missionLabel: String,
    val missionValue: String,
    val attentionLabel: String,
    val attentionValue: String,
    val progressCurrent: Int,
    val progressTotal: Int,
) {
    init {
        require(title.isNotBlank())
        require(supportingText.isNotBlank())
        require(shiftLabel.isNotBlank() && shiftValue.isNotBlank())
        require(missionLabel.isNotBlank() && missionValue.isNotBlank())
        require(attentionLabel.isNotBlank() && attentionValue.isNotBlank())
        require(progressTotal > 0)
        require(progressCurrent in 0..progressTotal)
    }
}

enum class EayModuleHealthVisual { READY, IN_PROGRESS, ATTENTION, LOCKED }

data class EayModuleMetricUiModel(
    val label: String,
    val value: String,
    val supportingText: String = "",
) {
    init {
        require(label.isNotBlank())
        require(value.isNotBlank())
    }
}

data class EayModuleDetailSectionUiModel(
    val title: String,
    val body: String,
    val statusLabel: String? = null,
) {
    init {
        require(title.isNotBlank())
        require(body.isNotBlank())
        require(statusLabel == null || statusLabel.isNotBlank())
    }
}

/**
 * Presentation-only module workspace for Workforce, Planogram, Audit, Academy and Jarvis.
 * It intentionally contains no credential, identity-binding, device-binding or stock-truth fields.
 */
data class EayModuleDetailUiState(
    val moduleId: String,
    val kind: FieldMissionVisualKind,
    val eyebrow: String,
    val title: String,
    val summary: String,
    val health: EayModuleHealthVisual,
    val statusLabel: String,
    val metrics: List<EayModuleMetricUiModel>,
    val sections: List<EayModuleDetailSectionUiModel>,
    val syncState: FieldSyncVisualState,
    val backActionLabel: String,
    val primaryActionLabel: String,
    val secondaryActionLabel: String? = null,
    val primaryActionEnabled: Boolean = true,
) {
    init {
        require(moduleId.isNotBlank())
        require(kind in setOf(
            FieldMissionVisualKind.SHIFT,
            FieldMissionVisualKind.PLANOGRAM,
            FieldMissionVisualKind.AUDIT,
            FieldMissionVisualKind.ACADEMY,
            FieldMissionVisualKind.JARVIS,
        ))
        require(eyebrow.isNotBlank())
        require(title.isNotBlank())
        require(summary.isNotBlank())
        require(statusLabel.isNotBlank())
        require(backActionLabel.isNotBlank())
        require(primaryActionLabel.isNotBlank())
        require(secondaryActionLabel == null || secondaryActionLabel.isNotBlank())
        require(metrics.size <= 6)
        require(sections.size <= 8)
    }
}
