package com.eay.inventory

import android.content.Context
import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldRecoveryBannerModel
import com.eay.mobile.presentation.FieldRecoveryVisualSeverity
import com.eay.mobile.presentation.adapter.FieldPresentationAdapter
import com.eay.mobile.presentation.adapter.RecoveryPresentationIntent

data class InventoryRecoveryPresentationPolicy(
    val severity: FieldRecoveryVisualSeverity,
    val titleRes: Int,
    val messageRes: Int,
    val actionKind: FieldRecoveryActionKind = FieldRecoveryActionKind.NONE,
    val actionLabelRes: Int? = null,
    val blocksNewMissionStarts: Boolean,
) {
    init {
        require((actionKind == FieldRecoveryActionKind.NONE) == (actionLabelRes == null))
    }
}

/**
 * Converts durable recovery truth into presentation-only copy and bounded UI intent.
 *
 * This layer cannot retry, delete, rebind, reassign or mutate evidence. Security,
 * integrity and managed-device failures block new local mission starts early; a
 * single business/supervisor review remains local to the affected evidence/mission.
 */
object InventoryRecoveryPresentation {
    fun policy(summary: InventoryRecoverySummary): InventoryRecoveryPresentationPolicy =
        when (summary.primaryIntent) {
            InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY -> InventoryRecoveryPresentationPolicy(
                severity = FieldRecoveryVisualSeverity.INFO,
                titleRes = R.string.terminal_recovery_title_info,
                messageRes = R.string.terminal_recovery_wait_auto,
                blocksNewMissionStarts = false,
            )

            InventoryRecoveryIntent.RECOVER_MANAGED_DEVICE -> InventoryRecoveryPresentationPolicy(
                severity = FieldRecoveryVisualSeverity.BLOCKING,
                titleRes = R.string.terminal_recovery_title_blocking,
                messageRes = R.string.terminal_recovery_device,
                blocksNewMissionStarts = true,
            )

            InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW -> InventoryRecoveryPresentationPolicy(
                severity = FieldRecoveryVisualSeverity.BLOCKING,
                titleRes = R.string.terminal_recovery_title_blocking,
                messageRes = R.string.terminal_recovery_supervisor,
                blocksNewMissionStarts = false,
            )

            InventoryRecoveryIntent.REQUEST_SECURITY_REVIEW -> InventoryRecoveryPresentationPolicy(
                severity = FieldRecoveryVisualSeverity.SECURITY,
                titleRes = R.string.terminal_recovery_title_security,
                messageRes = R.string.terminal_recovery_security,
                blocksNewMissionStarts = true,
            )

            InventoryRecoveryIntent.REQUEST_INTEGRITY_REVIEW -> InventoryRecoveryPresentationPolicy(
                severity = FieldRecoveryVisualSeverity.SECURITY,
                titleRes = R.string.terminal_recovery_title_security,
                messageRes = R.string.terminal_recovery_integrity,
                blocksNewMissionStarts = true,
            )

            InventoryRecoveryIntent.SIGN_IN_AGAIN,
            InventoryRecoveryIntent.RELOAD_MISSIONS,
            InventoryRecoveryIntent.NONE,
            -> error("Unsupported durable recovery intent: ${summary.primaryIntent}")
        }

    fun banner(
        context: Context,
        summary: InventoryRecoverySummary,
    ): FieldRecoveryBannerModel {
        val policy = policy(summary)
        return FieldPresentationAdapter.recoveryBanner(
            RecoveryPresentationIntent(
                severity = policy.severity,
                title = context.getString(policy.titleRes),
                message = context.getString(policy.messageRes, summary.affectedEventCount),
                affectedEventCount = summary.affectedEventCount,
                actionKind = policy.actionKind,
                actionLabel = policy.actionLabelRes?.let(context::getString),
            ),
        )
    }
}
