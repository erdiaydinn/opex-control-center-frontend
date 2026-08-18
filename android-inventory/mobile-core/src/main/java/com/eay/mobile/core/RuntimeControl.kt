package com.eay.mobile.core

enum class RuntimeFeature {
    INVENTORY_COUNT_V2_UI,
    PICKER_ROUTE_ASSIST,
    PLANOGRAM_VISION,
    JARVIS_VOICE,
    ACADEMY_MEDIA_AUTOPLAY,
}

data class RuntimeFeatureControl(
    val feature: RuntimeFeature,
    val enabledRings: Set<RolloutRing>,
)

data class RuntimeControlSnapshot(
    val version: Long,
    val policyFingerprint: String,
    val issuedAtEpochMs: Long,
    val expiresAtEpochMs: Long,
    val controls: Map<RuntimeFeature, RuntimeFeatureControl>,
) {
    fun isStructurallyValid(): Boolean =
        version > 0 &&
            policyFingerprint.matches(Regex("^[a-fA-F0-9]{64}$")) &&
            issuedAtEpochMs > 0 &&
            expiresAtEpochMs > issuedAtEpochMs &&
            controls.all { (feature, control) ->
                feature == control.feature
            }
}

enum class RuntimeControlCode {
    ENABLED,
    DISABLED_NO_SNAPSHOT,
    DISABLED_INVALID_SNAPSHOT,
    DISABLED_POLICY_MISMATCH,
    DISABLED_EXPIRED,
    DISABLED_NOT_CONFIGURED,
    DISABLED_ROLLOUT_RING,
}

data class RuntimeControlDecision(
    val enabled: Boolean,
    val code: RuntimeControlCode,
)

object RuntimeControlGuard {
    fun evaluate(
        feature: RuntimeFeature,
        snapshot: RuntimeControlSnapshot?,
        currentPolicyFingerprint: String,
        rolloutRing: RolloutRing,
        nowEpochMs: Long,
    ): RuntimeControlDecision {
        if (snapshot == null) return disabled(RuntimeControlCode.DISABLED_NO_SNAPSHOT)
        if (!snapshot.isStructurallyValid()) {
            return disabled(RuntimeControlCode.DISABLED_INVALID_SNAPSHOT)
        }
        if (
            currentPolicyFingerprint.isBlank() ||
            !snapshot.policyFingerprint.equals(currentPolicyFingerprint, ignoreCase = true)
        ) {
            return disabled(RuntimeControlCode.DISABLED_POLICY_MISMATCH)
        }
        if (nowEpochMs < snapshot.issuedAtEpochMs || nowEpochMs >= snapshot.expiresAtEpochMs) {
            return disabled(RuntimeControlCode.DISABLED_EXPIRED)
        }
        val control = snapshot.controls[feature]
            ?: return disabled(RuntimeControlCode.DISABLED_NOT_CONFIGURED)
        if (rolloutRing !in control.enabledRings) {
            return disabled(RuntimeControlCode.DISABLED_ROLLOUT_RING)
        }
        return RuntimeControlDecision(true, RuntimeControlCode.ENABLED)
    }

    private fun disabled(code: RuntimeControlCode) = RuntimeControlDecision(false, code)
}
