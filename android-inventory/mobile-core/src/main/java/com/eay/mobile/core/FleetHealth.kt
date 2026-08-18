package com.eay.mobile.core

enum class FleetDeviceClass {
    PHONE,
    RUGGED,
    TABLET,
    UNKNOWN,
}

enum class RolloutRing(val order: Int) {
    DEVELOPER(0),
    DOGFOOD(10),
    LAB(20),
    PILOT_1(30),
    PILOT_5(40),
    PILOT_20(50),
    PERCENT_25(60),
    PERCENT_50(70),
    PERCENT_100(80),
}

enum class ScannerHealth {
    NOT_APPLICABLE,
    HEALTHY,
    DEGRADED,
    UNAVAILABLE,
}

enum class BatteryBucket {
    UNKNOWN,
    CRITICAL,
    LOW,
    NORMAL,
    HIGH,
}

enum class FleetOperationalHealth {
    HEALTHY,
    DEGRADED,
    CRITICAL,
}

data class FleetHealthObservation(
    val fleetDeviceToken: String,
    val fleetSiteToken: String?,
    val runtimeProfile: MobileRuntimeProfile,
    val deviceClass: FleetDeviceClass,
    val appVersion: String,
    val rolloutRing: RolloutRing,
    val connectivity: ConnectivityState,
    val pendingSyncCount: Int,
    val quarantinedSyncCount: Int,
    val oldestPendingAgeMs: Long?,
    val lastSuccessfulSyncAgeMs: Long?,
    val scannerHealth: ScannerHealth,
    val recentCrashCount: Int,
    val recentAnrCount: Int,
    val batteryBucket: BatteryBucket,
    val observedAtEpochMs: Long,
) {
    fun isStructurallyValid(): Boolean =
        isOpaqueToken(fleetDeviceToken) &&
            (fleetSiteToken == null || isOpaqueToken(fleetSiteToken)) &&
            appVersion.isNotBlank() &&
            appVersion.length <= 64 &&
            pendingSyncCount >= 0 &&
            quarantinedSyncCount >= 0 &&
            (oldestPendingAgeMs == null || oldestPendingAgeMs >= 0) &&
            (lastSuccessfulSyncAgeMs == null || lastSuccessfulSyncAgeMs >= 0) &&
            recentCrashCount >= 0 &&
            recentAnrCount >= 0 &&
            observedAtEpochMs > 0

    fun telemetryAttributes(): Map<String, String> {
        if (!isStructurallyValid()) return emptyMap()
        return MobileTelemetryPolicy.sanitize(
            buildMap {
                put("fleet_device_token", fleetDeviceToken)
                fleetSiteToken?.let { put("fleet_site_token", it) }
                put("runtime_profile", runtimeProfile.name)
                put("device_class", deviceClass.name)
                put("app_version", appVersion)
                put("rollout_ring", rolloutRing.name)
                put("connectivity", connectivity.name)
                put("pending_sync_count", pendingSyncCount.toString())
                put("quarantined_sync_count", quarantinedSyncCount.toString())
                oldestPendingAgeMs?.let { put("oldest_pending_age_ms", it.toString()) }
                lastSuccessfulSyncAgeMs?.let { put("last_successful_sync_age_ms", it.toString()) }
                put("scanner_health", scannerHealth.name)
                put("recent_crash_count", recentCrashCount.toString())
                put("recent_anr_count", recentAnrCount.toString())
                put("battery_bucket", batteryBucket.name)
                put("observed_at_epoch_ms", observedAtEpochMs.toString())
            },
        )
    }

    companion object {
        private val opaqueTokenPattern = Regex("^[A-Za-z0-9._:-]{16,128}$")

        fun isOpaqueToken(value: String): Boolean = opaqueTokenPattern.matches(value)
    }
}

object FleetHealthClassifier {
    private const val CRITICAL_QUARANTINE_COUNT = 100
    private const val DEGRADED_PENDING_COUNT = 500
    private const val DEGRADED_PENDING_AGE_MS = 15 * 60 * 1000L
    private const val DEGRADED_SYNC_AGE_MS = 15 * 60 * 1000L
    private const val CRITICAL_CRASH_COUNT = 3

    fun classify(observation: FleetHealthObservation): FleetOperationalHealth {
        if (!observation.isStructurallyValid()) return FleetOperationalHealth.CRITICAL
        if (observation.recentCrashCount >= CRITICAL_CRASH_COUNT) {
            return FleetOperationalHealth.CRITICAL
        }
        if (observation.quarantinedSyncCount >= CRITICAL_QUARANTINE_COUNT) {
            return FleetOperationalHealth.CRITICAL
        }
        if (
            observation.runtimeProfile == MobileRuntimeProfile.EAY_TERMINAL &&
            observation.scannerHealth == ScannerHealth.UNAVAILABLE
        ) {
            return FleetOperationalHealth.CRITICAL
        }
        if (
            observation.quarantinedSyncCount > 0 ||
            observation.pendingSyncCount >= DEGRADED_PENDING_COUNT ||
            (observation.oldestPendingAgeMs ?: 0) >= DEGRADED_PENDING_AGE_MS ||
            observation.recentAnrCount > 0 ||
            observation.scannerHealth == ScannerHealth.DEGRADED ||
            (
                observation.connectivity == ConnectivityState.ONLINE &&
                    (observation.lastSuccessfulSyncAgeMs ?: 0) >= DEGRADED_SYNC_AGE_MS
                ) ||
            observation.batteryBucket == BatteryBucket.CRITICAL
        ) {
            return FleetOperationalHealth.DEGRADED
        }
        return FleetOperationalHealth.HEALTHY
    }
}
