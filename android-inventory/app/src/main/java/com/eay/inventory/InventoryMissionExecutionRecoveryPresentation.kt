package com.eay.inventory

import android.content.Context
import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldRecoveryVisualSeverity
import com.eay.mobile.presentation.FieldSessionRecoveryBannerModel
import com.eay.mobile.presentation.adapter.SessionRecoveryPresentationAdapter
import com.eay.mobile.presentation.adapter.SessionRecoveryPresentationIntent

data class InventoryMissionExecutionRecoveryPolicy(
    val severity: FieldRecoveryVisualSeverity,
    val titleRes: Int,
    val messageRes: Int,
    val messageArgument: String? = null,
    val actionKind: FieldRecoveryActionKind = FieldRecoveryActionKind.NONE,
    val actionLabelRes: Int? = null,
) {
    init {
        require((actionKind == FieldRecoveryActionKind.NONE) == (actionLabelRes == null))
    }
}

/**
 * Presentation-only recovery for pre-execution mission claim and local lease expiry.
 *
 * Reloading missions is intentionally read-only. A user may never revive, extend,
 * reassign or rebind an attempt/lease from the client. Selecting a refreshed mission
 * must still re-enter InventoryTerminalMissionClaimClient and the server authority.
 */
object InventoryMissionExecutionRecoveryPresentation {
    fun claimPolicy(code: InventoryMissionClaimCode): InventoryMissionExecutionRecoveryPolicy? =
        when (code) {
            InventoryMissionClaimCode.OK -> null

            InventoryMissionClaimCode.AUTH_REQUIRED -> InventoryMissionExecutionRecoveryPolicy(
                severity = FieldRecoveryVisualSeverity.BLOCKING,
                titleRes = R.string.terminal_recovery_title_blocking,
                messageRes = R.string.terminal_sso_failed,
                actionKind = FieldRecoveryActionKind.SIGN_IN_AGAIN,
                actionLabelRes = R.string.terminal_recovery_sign_in,
            )

            InventoryMissionClaimCode.RETRYABLE -> InventoryMissionExecutionRecoveryPolicy(
                severity = FieldRecoveryVisualSeverity.ATTENTION,
                titleRes = R.string.terminal_recovery_title_info,
                messageRes = R.string.terminal_task_fetch_failed,
                messageArgument = "RETRYABLE",
                actionKind = FieldRecoveryActionKind.RELOAD_MISSIONS,
                actionLabelRes = R.string.terminal_recovery_reload,
            )

            InventoryMissionClaimCode.BUSINESS_CONFLICT -> InventoryMissionExecutionRecoveryPolicy(
                severity = FieldRecoveryVisualSeverity.ATTENTION,
                titleRes = R.string.terminal_recovery_title_blocking,
                messageRes = R.string.terminal_task_fetch_failed,
                messageArgument = "MISSION_CHANGED",
                actionKind = FieldRecoveryActionKind.RELOAD_MISSIONS,
                actionLabelRes = R.string.terminal_recovery_reload,
            )

            InventoryMissionClaimCode.DEVICE_REJECTED -> InventoryMissionExecutionRecoveryPolicy(
                severity = FieldRecoveryVisualSeverity.BLOCKING,
                titleRes = R.string.terminal_recovery_title_blocking,
                messageRes = R.string.terminal_enrollment_failed,
            )

            InventoryMissionClaimCode.POLICY_REJECTED,
            InventoryMissionClaimCode.CONTRACT_REJECTED,
            InventoryMissionClaimCode.PERMANENT_REJECTED,
            -> InventoryMissionExecutionRecoveryPolicy(
                severity = FieldRecoveryVisualSeverity.SECURITY,
                titleRes = R.string.terminal_recovery_title_security,
                messageRes = R.string.terminal_contract_blocked,
            )
        }

    fun leaseExpiredPolicy() = InventoryMissionExecutionRecoveryPolicy(
        severity = FieldRecoveryVisualSeverity.ATTENTION,
        titleRes = R.string.terminal_recovery_title_blocking,
        messageRes = R.string.terminal_task_fetch_failed,
        messageArgument = "LEASE_EXPIRED",
        actionKind = FieldRecoveryActionKind.RELOAD_MISSIONS,
        actionLabelRes = R.string.terminal_recovery_reload,
    )

    fun claimBanner(
        context: Context,
        code: InventoryMissionClaimCode,
    ): FieldSessionRecoveryBannerModel? = claimPolicy(code)?.let { banner(context, it) }

    fun leaseExpiredBanner(context: Context): FieldSessionRecoveryBannerModel =
        banner(context, leaseExpiredPolicy())

    private fun banner(
        context: Context,
        policy: InventoryMissionExecutionRecoveryPolicy,
    ): FieldSessionRecoveryBannerModel {
        val message = policy.messageArgument?.let {
            context.getString(policy.messageRes, it)
        } ?: context.getString(policy.messageRes)
        return SessionRecoveryPresentationAdapter.banner(
            SessionRecoveryPresentationIntent(
                severity = policy.severity,
                title = context.getString(policy.titleRes),
                message = message,
                actionKind = policy.actionKind,
                actionLabel = policy.actionLabelRes?.let(context::getString),
            ),
        )
    }
}
