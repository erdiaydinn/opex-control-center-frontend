package com.eay.inventory

import android.content.Context
import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldRecoveryVisualSeverity
import com.eay.mobile.presentation.FieldSessionRecoveryBannerModel
import com.eay.mobile.presentation.adapter.SessionRecoveryPresentationAdapter
import com.eay.mobile.presentation.adapter.SessionRecoveryPresentationIntent

/**
 * Maps read-only task-discovery failures to presentation-safe recovery.
 *
 * This path never touches durable offline evidence. Only fresh authentication or
 * a fresh read-only mission fetch can be requested from the UI.
 */
object InventoryTaskFetchRecoveryPresentation {
    fun banner(
        context: Context,
        code: InventoryTaskFetchCode,
    ): FieldSessionRecoveryBannerModel? = when (code) {
        InventoryTaskFetchCode.OK -> null

        InventoryTaskFetchCode.AUTH_REQUIRED -> SessionRecoveryPresentationAdapter.banner(
            SessionRecoveryPresentationIntent(
                severity = FieldRecoveryVisualSeverity.BLOCKING,
                title = context.getString(R.string.terminal_recovery_title_blocking),
                message = context.getString(R.string.terminal_sso_failed),
                actionKind = FieldRecoveryActionKind.SIGN_IN_AGAIN,
                actionLabel = context.getString(R.string.terminal_recovery_sign_in),
            ),
        )

        InventoryTaskFetchCode.RETRYABLE -> SessionRecoveryPresentationAdapter.banner(
            SessionRecoveryPresentationIntent(
                severity = FieldRecoveryVisualSeverity.ATTENTION,
                title = context.getString(R.string.terminal_recovery_title_info),
                message = context.getString(R.string.terminal_task_fetch_failed, "NETWORK"),
                actionKind = FieldRecoveryActionKind.RELOAD_MISSIONS,
                actionLabel = context.getString(R.string.terminal_recovery_reload),
            ),
        )

        InventoryTaskFetchCode.DEVICE_REJECTED -> SessionRecoveryPresentationAdapter.banner(
            SessionRecoveryPresentationIntent(
                severity = FieldRecoveryVisualSeverity.BLOCKING,
                title = context.getString(R.string.terminal_recovery_title_blocking),
                message = context.getString(R.string.terminal_enrollment_failed),
            ),
        )

        InventoryTaskFetchCode.POLICY_REJECTED,
        InventoryTaskFetchCode.CONTRACT_REJECTED,
        InventoryTaskFetchCode.PERMANENT_REJECTED,
        -> SessionRecoveryPresentationAdapter.banner(
            SessionRecoveryPresentationIntent(
                severity = FieldRecoveryVisualSeverity.SECURITY,
                title = context.getString(R.string.terminal_recovery_title_security),
                message = context.getString(R.string.terminal_contract_blocked),
            ),
        )
    }
}
