package com.eay.mobile.presentation.adapter

import com.eay.mobile.core.BlindCountSession
import com.eay.mobile.core.BlindCountTarget
import com.eay.mobile.core.ConnectivityState
import com.eay.mobile.core.FieldMission
import com.eay.mobile.core.FieldMissionKind
import com.eay.mobile.core.FieldMissionPriority
import com.eay.mobile.core.MissionGate
import com.eay.mobile.core.MobileAuthorizationSnapshot
import com.eay.mobile.core.MobileExecutionContext
import com.eay.mobile.core.MobileRuntimeProfile
import com.eay.mobile.core.SyncRecord
import com.eay.mobile.core.SyncRecordState
import com.eay.mobile.presentation.BlindCountUiState
import com.eay.mobile.presentation.FieldMissionCardModel
import com.eay.mobile.presentation.FieldMissionVisualKind
import com.eay.mobile.presentation.FieldMissionVisualPriority
import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldRecoveryBannerModel
import com.eay.mobile.presentation.FieldRecoveryVisualSeverity
import com.eay.mobile.presentation.FieldRuntimeSurface
import com.eay.mobile.presentation.FieldShellHeader
import com.eay.mobile.presentation.FieldSyncVisualState

/** Localized/safe copy supplied by the presentation layer; never an authority input. */
data class MissionPresentationCopy(
    val subtitle: String = "",
    val primaryActionLabel: String,
)

data class MissionProgress(
    val current: Int? = null,
    val total: Int? = null,
)

data class BlindCountPresentationCopy(
    val locationLabel: String,
    val stepLabel: String,
    val scannedItemLabel: String? = null,
    val observedQuantityText: String? = null,
)

data class SyncPresentationSummary(
    val state: FieldSyncVisualState,
    val pendingCount: Int,
)

data class RecoveryPresentationIntent(
    val severity: FieldRecoveryVisualSeverity,
    val title: String,
    val message: String,
    val affectedEventCount: Int,
    val actionKind: FieldRecoveryActionKind = FieldRecoveryActionKind.NONE,
    val actionLabel: String? = null,
)

/**
 * Presentation-only intent emitted before a server-authoritative mission claim.
 *
 * `enabled` means only that the UI may emit a bounded user-intent callback. It is never
 * execution authority: callers must re-enter the existing server/runtime claim gate before
 * creating an execution controller. Authority-bearing tenant, actor, device, shift, lease,
 * token and policy fields are intentionally impossible to represent here.
 */
data class MissionIntentPresentation(
    val missionId: String,
    val title: String,
    val subtitle: String = "",
    val kind: FieldMissionVisualKind,
    val priority: FieldMissionVisualPriority,
    val primaryActionLabel: String,
    val enabled: Boolean,
) {
    init {
        require(missionId.isNotBlank())
        require(title.isNotBlank())
        require(primaryActionLabel.isNotBlank())
    }
}

/**
 * One-way anti-corruption boundary from authoritative Mobile Core state to render-only UI models.
 *
 * The adapter deliberately cannot grant access. Runtime mission enablement is derived exclusively
 * from MissionGate, which composes mission binding and MobileOperationAdmission. Pre-claim intent
 * cards are presentation-only and must return to the existing server-authoritative claim path.
 * Raw actor, tenant, device, installation, auth-binding, barcode/payload hashes and expected stock
 * never appear in the returned presentation contracts.
 */
object FieldPresentationAdapter {
    fun missionCard(
        mission: FieldMission,
        context: MobileExecutionContext,
        authorization: MobileAuthorizationSnapshot?,
        nowEpochMs: Long,
        copy: MissionPresentationCopy,
        progress: MissionProgress = MissionProgress(),
    ): FieldMissionCardModel {
        require(copy.primaryActionLabel.isNotBlank())
        val decision = MissionGate.evaluate(
            mission = mission,
            context = context,
            snapshot = authorization,
            nowEpochMs = nowEpochMs,
        )
        return FieldMissionCardModel(
            missionId = mission.missionId,
            title = mission.title,
            subtitle = copy.subtitle,
            kind = mission.kind.toVisualKind(),
            priority = mission.priority.toVisualPriority(),
            progressCurrent = progress.current,
            progressTotal = progress.total,
            primaryActionLabel = copy.primaryActionLabel,
            enabled = decision.allowed,
        )
    }

    /**
     * Maps a presentation-safe claim intent into the shared Compose model.
     *
     * This method never evaluates or grants execution permission. Even an enabled card may only
     * emit a user-intent callback; the existing server mission claim remains mandatory.
     */
    fun missionIntentCard(intent: MissionIntentPresentation): FieldMissionCardModel =
        FieldMissionCardModel(
            missionId = intent.missionId,
            title = intent.title,
            subtitle = intent.subtitle,
            kind = intent.kind,
            priority = intent.priority,
            primaryActionLabel = intent.primaryActionLabel,
            enabled = intent.enabled,
        )

    /**
     * Recovery output is explanation plus a bounded local intent only. There is no
     * representation for retry/delete/rebind/reassign mutations in this adapter.
     */
    fun recoveryBanner(intent: RecoveryPresentationIntent): FieldRecoveryBannerModel =
        FieldRecoveryBannerModel(
            severity = intent.severity,
            title = intent.title,
            message = intent.message,
            affectedEventCount = intent.affectedEventCount,
            actionKind = intent.actionKind,
            actionLabel = intent.actionLabel,
        )

    fun blindCount(
        session: BlindCountSession,
        target: BlindCountTarget,
        copy: BlindCountPresentationCopy,
        syncState: FieldSyncVisualState,
    ): BlindCountUiState {
        require(session.missionId == target.missionId)
        require(copy.locationLabel.isNotBlank())
        require(copy.stepLabel.isNotBlank())
        return BlindCountUiState(
            missionId = session.missionId,
            locationLabel = copy.locationLabel,
            stepLabel = copy.stepLabel,
            scannedItemLabel = copy.scannedItemLabel,
            observedQuantityText = copy.observedQuantityText
                ?: session.currentQuantity?.toString().orEmpty(),
            confirmedLines = session.confirmedLineCount,
            totalLines = target.targetLineCount,
            syncState = syncState,
        )
    }

    fun syncSummary(
        connectivity: ConnectivityState,
        records: Collection<SyncRecord>,
    ): SyncPresentationSummary {
        val pendingCount = records.count { it.state != SyncRecordState.ACKED }
        val state = when {
            records.any { it.state == SyncRecordState.QUARANTINED } -> FieldSyncVisualState.QUARANTINED
            connectivity == ConnectivityState.OFFLINE -> FieldSyncVisualState.OFFLINE
            pendingCount > 0 -> FieldSyncVisualState.PENDING
            else -> FieldSyncVisualState.SYNCED
        }
        return SyncPresentationSummary(state = state, pendingCount = pendingCount)
    }

    fun shellHeader(
        locationLabel: String,
        deviceLabel: String,
        runtimeProfile: MobileRuntimeProfile,
        sync: SyncPresentationSummary,
    ): FieldShellHeader = FieldShellHeader(
        locationLabel = locationLabel,
        deviceLabel = deviceLabel,
        runtimeSurface = runtimeProfile.toRuntimeSurface(),
        syncState = sync.state,
        pendingCount = sync.pendingCount,
    )

    private fun FieldMissionKind.toVisualKind(): FieldMissionVisualKind = when (this) {
        FieldMissionKind.SHIFT -> FieldMissionVisualKind.SHIFT
        FieldMissionKind.PICK -> FieldMissionVisualKind.PICK
        FieldMissionKind.COUNT -> FieldMissionVisualKind.COUNT
        FieldMissionKind.PUTAWAY -> FieldMissionVisualKind.PUTAWAY
        FieldMissionKind.RECEIVING -> FieldMissionVisualKind.RECEIVING
        FieldMissionKind.TRANSFER -> FieldMissionVisualKind.TRANSFER
        FieldMissionKind.PLANOGRAM -> FieldMissionVisualKind.PLANOGRAM
        FieldMissionKind.AUDIT -> FieldMissionVisualKind.AUDIT
        FieldMissionKind.ACADEMY -> FieldMissionVisualKind.ACADEMY
        FieldMissionKind.JARVIS -> FieldMissionVisualKind.JARVIS
    }

    private fun FieldMissionPriority.toVisualPriority(): FieldMissionVisualPriority = when (this) {
        FieldMissionPriority.LOW -> FieldMissionVisualPriority.LOW
        FieldMissionPriority.NORMAL -> FieldMissionVisualPriority.NORMAL
        FieldMissionPriority.HIGH -> FieldMissionVisualPriority.HIGH
        FieldMissionPriority.URGENT -> FieldMissionVisualPriority.URGENT
    }

    private fun MobileRuntimeProfile.toRuntimeSurface(): FieldRuntimeSurface = when (this) {
        MobileRuntimeProfile.EAY_ONE -> FieldRuntimeSurface.EAY_ONE
        MobileRuntimeProfile.EAY_TERMINAL -> FieldRuntimeSurface.EAY_TERMINAL
    }
}
