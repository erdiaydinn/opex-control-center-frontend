package com.eay.mobile.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FleetHealthTest {
    private fun observation(
        pending: Int = 0,
        quarantined: Int = 0,
        scanner: ScannerHealth = ScannerHealth.HEALTHY,
        crashes: Int = 0,
        anrs: Int = 0,
        connectivity: ConnectivityState = ConnectivityState.ONLINE,
        syncAgeMs: Long? = 1_000,
    ) = FleetHealthObservation(
        fleetDeviceToken = "fleet-device-token-0001",
        fleetSiteToken = "fleet-site-token-0001",
        runtimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
        deviceClass = FleetDeviceClass.RUGGED,
        appVersion = "30.0.1",
        rolloutRing = RolloutRing.LAB,
        connectivity = connectivity,
        pendingSyncCount = pending,
        quarantinedSyncCount = quarantined,
        oldestPendingAgeMs = if (pending > 0) 1_000 else null,
        lastSuccessfulSyncAgeMs = syncAgeMs,
        scannerHealth = scanner,
        recentCrashCount = crashes,
        recentAnrCount = anrs,
        batteryBucket = BatteryBucket.NORMAL,
        observedAtEpochMs = 1_800_000_000_000L,
    )

    @Test
    fun `healthy terminal emits privacy bounded telemetry`() {
        val value = observation()
        assertTrue(value.isStructurallyValid())
        assertEquals(FleetOperationalHealth.HEALTHY, FleetHealthClassifier.classify(value))
        val attributes = value.telemetryAttributes()
        assertEquals("fleet-device-token-0001", attributes["fleet_device_token"])
        assertFalse(attributes.containsKey("device_id"))
        assertFalse(attributes.containsKey("actor_id"))
        assertFalse(attributes.containsKey("barcode"))
    }

    @Test
    fun `scanner outage or repeated crash is critical`() {
        assertEquals(
            FleetOperationalHealth.CRITICAL,
            FleetHealthClassifier.classify(observation(scanner = ScannerHealth.UNAVAILABLE)),
        )
        assertEquals(
            FleetOperationalHealth.CRITICAL,
            FleetHealthClassifier.classify(observation(crashes = 3)),
        )
    }

    @Test
    fun `quarantine anr or stale online sync is degraded`() {
        assertEquals(
            FleetOperationalHealth.DEGRADED,
            FleetHealthClassifier.classify(observation(quarantined = 1)),
        )
        assertEquals(
            FleetOperationalHealth.DEGRADED,
            FleetHealthClassifier.classify(observation(anrs = 1)),
        )
        assertEquals(
            FleetOperationalHealth.DEGRADED,
            FleetHealthClassifier.classify(observation(syncAgeMs = 15 * 60 * 1000L)),
        )
    }

    @Test
    fun `offline device is not falsely degraded only because last sync is old`() {
        assertEquals(
            FleetOperationalHealth.HEALTHY,
            FleetHealthClassifier.classify(
                observation(
                    connectivity = ConnectivityState.OFFLINE,
                    syncAgeMs = 60 * 60 * 1000L,
                ),
            ),
        )
    }
}
