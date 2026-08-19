package com.eay.mobile.presentation.adapter

import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldRecoveryVisualSeverity
import com.eay.mobile.presentation.FieldSessionRecoveryBannerModel

data class SessionRecoveryPresentationIntent(
    val severity: FieldRecoveryVisualSeverity,
    val title: String,
    val message: String,
    val actionKind: FieldRecoveryActionKind = FieldRecoveryActionKind.NONE,
    val actionLabel: String? = null,
)

/**
 * Anti-corruption boundary for session/read-only mission discovery recovery.
 *
 * Unlike durable-evidence recovery this model carries no event count or evidence
 * identifier. It cannot express queue retry, deletion, rebind or reassignment.
 */
object SessionRecoveryPresentationAdapter {
    fun banner(intent: SessionRecoveryPresentationIntent): FieldSessionRecoveryBannerModel =
        FieldSessionRecoveryBannerModel(
            severity = intent.severity,
            title = intent.title,
            message = intent.message,
            actionKind = intent.actionKind,
            actionLabel = intent.actionLabel,
        )
}
