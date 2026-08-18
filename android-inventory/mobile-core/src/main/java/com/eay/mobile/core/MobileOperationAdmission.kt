package com.eay.mobile.core

enum class AdmissionCode {
    ALLOW,
    DENY_MISSING_POLICY,
    DENY_BINDING_MISMATCH,
    DENY_POLICY_EXPIRED,
    DENY_POLICY_FINGERPRINT,
    DENY_OPERATION,
    DENY_DEVICE_TRUST,
    DENY_INTEGRITY,
    DENY_SHIFT,
    DENY_OFFLINE,
}

data class AdmissionDecision(
    val allowed: Boolean,
    val code: AdmissionCode,
)

object MobileOperationAdmission {
    fun evaluate(
        context: MobileExecutionContext,
        snapshot: MobileAuthorizationSnapshot?,
        operation: String,
        risk: OperationRisk,
        nowEpochMs: Long,
    ): AdmissionDecision {
        if (snapshot == null) return deny(AdmissionCode.DENY_MISSING_POLICY)
        if (!bindingsMatch(context, snapshot)) return deny(AdmissionCode.DENY_BINDING_MISMATCH)
        if (nowEpochMs < snapshot.issuedAtEpochMs || nowEpochMs >= snapshot.expiresAtEpochMs) {
            return deny(AdmissionCode.DENY_POLICY_EXPIRED)
        }
        if (context.policyFingerprint.isBlank() || context.policyFingerprint != snapshot.policyFingerprint) {
            return deny(AdmissionCode.DENY_POLICY_FINGERPRINT)
        }
        if (operation.isBlank() || operation !in snapshot.allowedOperations) {
            return deny(AdmissionCode.DENY_OPERATION)
        }
        if (context.deviceTrust == DeviceTrustLevel.UNVERIFIED) {
            return deny(AdmissionCode.DENY_DEVICE_TRUST)
        }
        if (risk >= OperationRisk.MEDIUM && context.deviceTrust < DeviceTrustLevel.MANAGED) {
            return deny(AdmissionCode.DENY_DEVICE_TRUST)
        }
        if (risk >= OperationRisk.HIGH && context.integrityVerdict != IntegrityVerdict.PASS) {
            return deny(AdmissionCode.DENY_INTEGRITY)
        }
        if (snapshot.requireActiveShift && context.shiftId.isNullOrBlank()) {
            return deny(AdmissionCode.DENY_SHIFT)
        }
        if (context.connectivity == ConnectivityState.OFFLINE) {
            if (risk == OperationRisk.CRITICAL || operation !in snapshot.offlineAllowedOperations) {
                return deny(AdmissionCode.DENY_OFFLINE)
            }
        }
        return AdmissionDecision(true, AdmissionCode.ALLOW)
    }

    private fun bindingsMatch(context: MobileExecutionContext, snapshot: MobileAuthorizationSnapshot): Boolean =
        context.tenantId.isNotBlank() &&
            context.actorId.isNotBlank() &&
            context.deviceId.isNotBlank() &&
            context.locationId.isNotBlank() &&
            context.authBindingId.isNotBlank() &&
            context.tenantId == snapshot.tenantId &&
            context.actorId == snapshot.actorId &&
            context.deviceId == snapshot.deviceId &&
            context.locationId == snapshot.locationId &&
            context.authBindingId == snapshot.authBindingId

    private fun deny(code: AdmissionCode) = AdmissionDecision(false, code)
}
