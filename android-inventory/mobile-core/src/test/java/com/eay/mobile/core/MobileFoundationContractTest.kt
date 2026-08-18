package com.eay.mobile.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MobileFoundationContractTest {
    private val now = 1_800_000_000_000L

    private fun context(
        trust: DeviceTrustLevel = DeviceTrustLevel.HARDWARE_BOUND,
        integrity: IntegrityVerdict = IntegrityVerdict.PASS,
        connectivity: ConnectivityState = ConnectivityState.ONLINE,
        shiftId: String? = "shift-1",
    ) = MobileExecutionContext(
        tenantId = "tenant-a",
        actorId = "actor-a",
        employeeId = "employee-a",
        locationId = "store-1",
        deviceId = "device-1",
        installationId = "install-1",
        authBindingId = "auth-1",
        shiftId = shiftId,
        runtimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
        deviceTrust = trust,
        integrityVerdict = integrity,
        connectivity = connectivity,
        appVersion = "1.0.0",
        policyFingerprint = "a".repeat(64),
    )

    private fun operationPolicy(
        operation: String = "inventory.count.capture",
        risk: OperationRisk = OperationRisk.MEDIUM,
        offlineAllowed: Boolean = true,
        requiresActiveShift: Boolean = true,
    ) = MobileOperationPolicy(
        operation = operation,
        risk = risk,
        offlineAllowed = offlineAllowed,
        requiresActiveShift = requiresActiveShift,
    )

    private fun snapshot(
        tenantId: String = "tenant-a",
        policy: MobileOperationPolicy = operationPolicy(),
    ) = MobileAuthorizationSnapshot(
        tenantId = tenantId,
        actorId = "actor-a",
        deviceId = "device-1",
        locationId = "store-1",
        authBindingId = "auth-1",
        policyFingerprint = "a".repeat(64),
        operationPolicies = mapOf(policy.operation to policy),
        issuedAtEpochMs = now - 1_000,
        expiresAtEpochMs = now + 60_000,
    )

    @Test
    fun `missing server policy denies by default`() {
        val decision = MobileOperationAdmission.evaluate(
            context(), null, "inventory.count.capture", now,
        )
        assertFalse(decision.allowed)
        assertEquals(AdmissionCode.DENY_MISSING_POLICY, decision.code)
    }

    @Test
    fun `tenant or auth binding mismatch is denied`() {
        val decision = MobileOperationAdmission.evaluate(
            context(), snapshot(tenantId = "tenant-b"), "inventory.count.capture", now,
        )
        assertEquals(AdmissionCode.DENY_BINDING_MISMATCH, decision.code)
    }

    @Test
    fun `server policy owns operation risk so caller cannot downgrade it`() {
        val highRisk = operationPolicy(risk = OperationRisk.HIGH)
        val decision = MobileOperationAdmission.evaluate(
            context(trust = DeviceTrustLevel.MANAGED), snapshot(policy = highRisk),
            highRisk.operation, now,
        )
        assertEquals(AdmissionCode.DENY_DEVICE_TRUST, decision.code)
    }

    @Test
    fun `high risk operation requires verified integrity`() {
        val highRisk = operationPolicy(risk = OperationRisk.HIGH)
        val decision = MobileOperationAdmission.evaluate(
            context(integrity = IntegrityVerdict.UNKNOWN), snapshot(policy = highRisk),
            highRisk.operation, now,
        )
        assertEquals(AdmissionCode.DENY_INTEGRITY, decision.code)
    }

    @Test
    fun `medium risk operation requires managed device`() {
        val decision = MobileOperationAdmission.evaluate(
            context(trust = DeviceTrustLevel.REGISTERED), snapshot(),
            "inventory.count.capture", now,
        )
        assertEquals(AdmissionCode.DENY_DEVICE_TRUST, decision.code)
    }

    @Test
    fun `active shift is operation specific and mandatory when required`() {
        val decision = MobileOperationAdmission.evaluate(
            context(shiftId = null), snapshot(), "inventory.count.capture", now,
        )
        assertEquals(AdmissionCode.DENY_SHIFT, decision.code)

        val noShiftPolicy = operationPolicy(
            operation = "jarvis.ask",
            risk = OperationRisk.LOW,
            offlineAllowed = false,
            requiresActiveShift = false,
        )
        val jarvis = MobileOperationAdmission.evaluate(
            context(shiftId = null), snapshot(policy = noShiftPolicy), "jarvis.ask", now,
        )
        assertTrue(jarvis.allowed)
    }

    @Test
    fun `offline execution is server policy and critical actions stay online only`() {
        val capture = MobileOperationAdmission.evaluate(
            context(connectivity = ConnectivityState.OFFLINE), snapshot(),
            "inventory.count.capture", now,
        )
        assertTrue(capture.allowed)

        val critical = operationPolicy(
            operation = "inventory.count.approve",
            risk = OperationRisk.CRITICAL,
            offlineAllowed = true,
        )
        val approval = MobileOperationAdmission.evaluate(
            context(connectivity = ConnectivityState.OFFLINE), snapshot(policy = critical),
            critical.operation, now,
        )
        assertEquals(AdmissionCode.DENY_OFFLINE, approval.code)
    }

    @Test
    fun `event ledger is deterministic and payload tampering changes proof`() {
        val original = event(payloadHash = "b".repeat(64))
        val altered = event(payloadHash = "c".repeat(64))
        assertEquals(original.ledgerHash(), original.copy().ledgerHash())
        assertNotEquals(original.ledgerHash(), altered.ledgerHash())
        assertTrue(original.isStructurallyValid())
    }

    @Test
    fun `event id payload substitution and device sequence collision fail closed`() {
        val original = event(payloadHash = "b".repeat(64))
        val substitution = original.copy(payloadHash = "c".repeat(64))
        assertEquals(ReplayDisposition.PAYLOAD_SUBSTITUTION, MobileLedgerGuard.compare(original, substitution))

        val collision = original.copy(eventId = "event-2", payloadHash = "d".repeat(64))
        assertEquals(ReplayDisposition.SEQUENCE_COLLISION, MobileLedgerGuard.compare(original, collision))
    }

    @Test
    fun `telemetry redacts credentials operational payloads and raw identity`() {
        val sanitized = MobileTelemetryPolicy.sanitize(
            mapOf(
                "authorization" to "Bearer secret",
                "barcode" to "8690000000000",
                "latitude" to "41.0",
                "actor_id" to "employee-secret",
                "device_id" to "managed-device-1",
                "fleet_device_token" to "fleet-device-token-0001",
                "screen" to "count",
            ),
        )
        assertEquals("[REDACTED]", sanitized["authorization"])
        assertEquals("[REDACTED]", sanitized["barcode"])
        assertEquals("[REDACTED]", sanitized["latitude"])
        assertEquals("[REDACTED]", sanitized["actor_id"])
        assertEquals("[REDACTED]", sanitized["device_id"])
        assertEquals("fleet-device-token-0001", sanitized["fleet_device_token"])
        assertEquals("count", sanitized["screen"])
        assertFalse(MobileTelemetryPolicy.containsForbiddenRawData(sanitized))
    }

    private fun event(payloadHash: String) = MobileEventEnvelope(
        eventId = "event-1",
        tenantId = "tenant-a",
        actorId = "actor-a",
        deviceId = "device-1",
        installationId = "install-1",
        authBindingId = "auth-1",
        missionId = "mission-1",
        operation = "inventory.count.capture",
        deviceSequence = 1,
        occurredAt = "2026-08-18T12:00:00Z",
        payloadHash = payloadHash,
        previousLedgerHash = null,
        policyFingerprint = "a".repeat(64),
        appVersion = "1.0.0",
    )
}
