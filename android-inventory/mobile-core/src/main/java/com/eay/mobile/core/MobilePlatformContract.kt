package com.eay.mobile.core

enum class MobileRuntimeProfile {
    EAY_ONE,
    EAY_TERMINAL,
}

enum class DeviceTrustLevel {
    UNVERIFIED,
    REGISTERED,
    MANAGED,
    HARDWARE_BOUND,
}

enum class IntegrityVerdict {
    UNKNOWN,
    PASS,
    FAIL,
}

enum class ConnectivityState {
    ONLINE,
    OFFLINE,
}

enum class OperationRisk {
    LOW,
    MEDIUM,
    HIGH,
    CRITICAL,
}

data class MobileExecutionContext(
    val tenantId: String,
    val actorId: String,
    val employeeId: String,
    val locationId: String,
    val deviceId: String,
    val installationId: String,
    val authBindingId: String,
    val shiftId: String?,
    val runtimeProfile: MobileRuntimeProfile,
    val deviceTrust: DeviceTrustLevel,
    val integrityVerdict: IntegrityVerdict,
    val connectivity: ConnectivityState,
    val appVersion: String,
    val policyFingerprint: String,
)

data class MobileOperationPolicy(
    val operation: String,
    val risk: OperationRisk,
    val offlineAllowed: Boolean,
    val requiresActiveShift: Boolean,
)

data class MobileAuthorizationSnapshot(
    val tenantId: String,
    val actorId: String,
    val deviceId: String,
    val locationId: String,
    val authBindingId: String,
    val policyFingerprint: String,
    val operationPolicies: Map<String, MobileOperationPolicy>,
    val issuedAtEpochMs: Long,
    val expiresAtEpochMs: Long,
)
