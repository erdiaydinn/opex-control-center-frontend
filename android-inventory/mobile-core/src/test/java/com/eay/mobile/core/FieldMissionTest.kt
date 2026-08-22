package com.eay.mobile.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FieldMissionTest {
    private val now = 1_800_000_000_000L

    private fun context(
        actorId: String = "actor-a",
        locationId: String = "store-1",
        connectivity: ConnectivityState = ConnectivityState.ONLINE,
    ) = MobileExecutionContext(
        tenantId = "tenant-a",
        actorId = actorId,
        employeeId = "employee-a",
        locationId = locationId,
        deviceId = "device-1",
        installationId = "install-1",
        authBindingId = "auth-1",
        shiftId = "shift-1",
        runtimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
        deviceTrust = DeviceTrustLevel.HARDWARE_BOUND,
        integrityVerdict = IntegrityVerdict.PASS,
        connectivity = connectivity,
        appVersion = "1.0.0",
        policyFingerprint = "a".repeat(64),
    )

    private fun snapshot(
        offlineAllowed: Boolean = true,
    ): MobileAuthorizationSnapshot {
        val policy = MobileOperationPolicy(
            operation = "inventory.count.capture",
            risk = OperationRisk.MEDIUM,
            offlineAllowed = offlineAllowed,
            requiresActiveShift = true,
        )
        return MobileAuthorizationSnapshot(
            tenantId = "tenant-a",
            actorId = "actor-a",
            deviceId = "device-1",
            locationId = "store-1",
            authBindingId = "auth-1",
            policyFingerprint = "a".repeat(64),
            operationPolicies = mapOf(policy.operation to policy),
            issuedAtEpochMs = now - 1_000,
            expiresAtEpochMs = now + 60_000,
        )
    }

    private fun mission(
        missionId: String = "mission-1",
        actorId: String = "actor-a",
        locationId: String = "store-1",
        priority: FieldMissionPriority = FieldMissionPriority.NORMAL,
        state: FieldMissionState = FieldMissionState.READY,
        dueAt: Long? = now + 30_000,
    ) = FieldMission(
        missionId = missionId,
        tenantId = "tenant-a",
        assignedActorId = actorId,
        locationId = locationId,
        kind = FieldMissionKind.COUNT,
        operation = "inventory.count.capture",
        title = "Cycle Count",
        priority = priority,
        state = state,
        runtimeProfiles = setOf(MobileRuntimeProfile.EAY_TERMINAL),
        createdAtEpochMs = now - 60_000,
        dueAtEpochMs = dueAt,
        estimatedSeconds = 480,
    )

    @Test
    fun `mission launch composes exact assignment and server policy`() {
        val decision = MissionGate.evaluate(
            mission(),
            context(),
            snapshot(),
            now,
        )
        assertTrue(decision.allowed)
        assertEquals(MissionGateCode.ALLOW, decision.code)
    }

    @Test
    fun `mission cannot be replayed to another actor or location`() {
        val wrongActor = MissionGate.evaluate(
            mission(),
            context(actorId = "actor-b"),
            snapshot(),
            now,
        )
        assertFalse(wrongActor.allowed)
        assertEquals(MissionGateCode.DENY_MISSION_ACTOR, wrongActor.code)

        val wrongLocation = MissionGate.evaluate(
            mission(),
            context(locationId = "store-2"),
            snapshot(),
            now,
        )
        assertEquals(MissionGateCode.DENY_MISSION_LOCATION, wrongLocation.code)
    }

    @Test
    fun `completed mission cannot be relaunched`() {
        val decision = MissionGate.evaluate(
            mission(state = FieldMissionState.COMPLETED),
            context(),
            snapshot(),
            now,
        )
        assertEquals(MissionGateCode.DENY_MISSION_STATE, decision.code)
    }

    @Test
    fun `offline mission still obeys server operation policy`() {
        val decision = MissionGate.evaluate(
            mission(),
            context(connectivity = ConnectivityState.OFFLINE),
            snapshot(offlineAllowed = false),
            now,
        )
        assertEquals(MissionGateCode.DENY_OPERATION_POLICY, decision.code)
        assertEquals(AdmissionCode.DENY_OFFLINE, decision.admissionCode)
    }

    @Test
    fun `queue resumes in progress then overdue urgent work deterministically`() {
        val missions = listOf(
            mission(missionId = "normal", priority = FieldMissionPriority.NORMAL),
            mission(
                missionId = "urgent-overdue",
                priority = FieldMissionPriority.URGENT,
                dueAt = now - 1,
            ),
            mission(
                missionId = "resume",
                priority = FieldMissionPriority.LOW,
                state = FieldMissionState.IN_PROGRESS,
                dueAt = now + 120_000,
            ),
        )
        val ordered = MissionQueue.orderedFor(missions, context(), now)
        assertEquals(listOf("resume", "urgent-overdue", "normal"), ordered.map { it.missionId })
    }

    @Test
    fun `queue silently excludes missions outside exact execution context`() {
        val ordered = MissionQueue.orderedFor(
            listOf(
                mission(missionId = "mine"),
                mission(missionId = "other-actor", actorId = "actor-b"),
                mission(missionId = "other-store", locationId = "store-2"),
            ),
            context(),
            now,
        )
        assertEquals(listOf("mine"), ordered.map { it.missionId })
    }
}
