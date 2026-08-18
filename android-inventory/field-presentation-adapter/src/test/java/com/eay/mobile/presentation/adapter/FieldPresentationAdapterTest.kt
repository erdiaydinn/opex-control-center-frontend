package com.eay.mobile.presentation.adapter

import com.eay.mobile.core.BlindCountSession
import com.eay.mobile.core.BlindCountStep
import com.eay.mobile.core.BlindCountTarget
import com.eay.mobile.core.ConnectivityState
import com.eay.mobile.core.DeviceTrustLevel
import com.eay.mobile.core.FieldMission
import com.eay.mobile.core.FieldMissionKind
import com.eay.mobile.core.FieldMissionPriority
import com.eay.mobile.core.FieldMissionState
import com.eay.mobile.core.IntegrityVerdict
import com.eay.mobile.core.MobileAuthorizationSnapshot
import com.eay.mobile.core.MobileExecutionContext
import com.eay.mobile.core.MobileOperationPolicy
import com.eay.mobile.core.MobileRuntimeProfile
import com.eay.mobile.core.OperationRisk
import com.eay.mobile.core.SyncQuarantineReason
import com.eay.mobile.core.SyncRecord
import com.eay.mobile.core.SyncRecordState
import com.eay.mobile.core.MobileEventEnvelope
import com.eay.mobile.presentation.FieldMissionVisualKind
import com.eay.mobile.presentation.FieldSyncVisualState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FieldPresentationAdapterTest {
    private val now = 1_500L

    @Test
    fun `mission enablement is derived from authoritative MissionGate`() {
        val allowed = FieldPresentationAdapter.missionCard(
            mission = mission(actorId = "actor-1"),
            context = context(actorId = "actor-1"),
            authorization = authorization(actorId = "actor-1"),
            nowEpochMs = now,
            copy = MissionPresentationCopy(primaryActionLabel = "Start"),
        )
        assertTrue(allowed.enabled)
        assertEquals(FieldMissionVisualKind.COUNT, allowed.kind)

        val denied = FieldPresentationAdapter.missionCard(
            mission = mission(actorId = "actor-2"),
            context = context(actorId = "actor-1"),
            authorization = authorization(actorId = "actor-1"),
            nowEpochMs = now,
            copy = MissionPresentationCopy(primaryActionLabel = "Start"),
        )
        assertFalse(denied.enabled)
    }

    @Test
    fun `blind count projection cannot expose item hash or expected stock`() {
        val target = BlindCountTarget(
            missionId = "mission-1",
            locationTokenHash = "b".repeat(64),
            targetLineCount = 10,
        )
        val session = BlindCountSession(
            missionId = "mission-1",
            step = BlindCountStep.ENTER_QUANTITY,
            locationVerified = true,
            currentItemHash = "a".repeat(64),
            currentQuantity = null,
            confirmedLineCount = 2,
        )
        val state = FieldPresentationAdapter.blindCount(
            session = session,
            target = target,
            copy = BlindCountPresentationCopy(
                locationLabel = "A-04",
                stepLabel = "Enter quantity",
                scannedItemLabel = "Product 123",
            ),
            syncState = FieldSyncVisualState.PENDING,
        )

        val fields = state::class.java.declaredFields.map { it.name.lowercase() }
        assertFalse(fields.any { it.contains("hash") || it.contains("expected") || it.contains("systemstock") })
        assertEquals("Product 123", state.scannedItemLabel)
        assertEquals(2, state.confirmedLines)
        assertEquals(10, state.totalLines)
    }

    @Test
    fun `sync projection prioritizes quarantine over offline and pending`() {
        val summary = FieldPresentationAdapter.syncSummary(
            connectivity = ConnectivityState.OFFLINE,
            records = listOf(
                syncRecord(SyncRecordState.QUEUED),
                syncRecord(
                    state = SyncRecordState.QUARANTINED,
                    quarantineReason = SyncQuarantineReason.BUSINESS_CONFLICT,
                    eventId = "event-2",
                    sequence = 2,
                ),
            ),
        )
        assertEquals(FieldSyncVisualState.QUARANTINED, summary.state)
        assertEquals(2, summary.pendingCount)
    }

    @Test
    fun `terminal runtime maps without copying execution identity`() {
        val header = FieldPresentationAdapter.shellHeader(
            locationLabel = "Fulya",
            deviceLabel = "Terminal 04",
            runtimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
            sync = FieldPresentationAdapter.syncSummary(ConnectivityState.ONLINE, emptyList()),
        )
        assertEquals(FieldSyncVisualState.SYNCED, header.syncState)
        assertEquals("Fulya", header.locationLabel)
        val fields = header::class.java.declaredFields.map { it.name.lowercase() }
        assertFalse(fields.any { it.contains("tenant") || it.contains("actor") || it.contains("authbinding") })
    }

    private fun mission(actorId: String) = FieldMission(
        missionId = "mission-1",
        tenantId = "tenant-1",
        assignedActorId = actorId,
        locationId = "location-1",
        kind = FieldMissionKind.COUNT,
        operation = "inventory.count",
        title = "Cycle count",
        priority = FieldMissionPriority.HIGH,
        state = FieldMissionState.READY,
        runtimeProfiles = setOf(MobileRuntimeProfile.EAY_TERMINAL),
        createdAtEpochMs = 1_000L,
        dueAtEpochMs = 5_000L,
    )

    private fun context(actorId: String) = MobileExecutionContext(
        tenantId = "tenant-1",
        actorId = actorId,
        employeeId = "employee-1",
        locationId = "location-1",
        deviceId = "device-1",
        installationId = "installation-1",
        authBindingId = "auth-1",
        shiftId = "shift-1",
        runtimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
        deviceTrust = DeviceTrustLevel.HARDWARE_BOUND,
        integrityVerdict = IntegrityVerdict.PASS,
        connectivity = ConnectivityState.ONLINE,
        appVersion = "1.0.0",
        policyFingerprint = "f".repeat(64),
    )

    private fun authorization(actorId: String) = MobileAuthorizationSnapshot(
        tenantId = "tenant-1",
        actorId = actorId,
        deviceId = "device-1",
        locationId = "location-1",
        authBindingId = "auth-1",
        policyFingerprint = "f".repeat(64),
        operationPolicies = mapOf(
            "inventory.count" to MobileOperationPolicy(
                operation = "inventory.count",
                risk = OperationRisk.HIGH,
                offlineAllowed = true,
                requiresActiveShift = true,
            ),
        ),
        issuedAtEpochMs = 1_000L,
        expiresAtEpochMs = 2_000L,
    )

    private fun syncRecord(
        state: SyncRecordState,
        quarantineReason: SyncQuarantineReason? = null,
        eventId: String = "event-1",
        sequence: Long = 1,
    ) = SyncRecord(
        event = MobileEventEnvelope(
            eventId = eventId,
            tenantId = "tenant-1",
            actorId = "actor-1",
            deviceId = "device-1",
            installationId = "installation-1",
            authBindingId = "auth-1",
            missionId = "mission-1",
            operation = "inventory.count",
            deviceSequence = sequence,
            occurredAt = "2026-08-18T15:00:00Z",
            payloadHash = "a".repeat(64),
            previousLedgerHash = null,
            policyFingerprint = "f".repeat(64),
            appVersion = "1.0.0",
        ),
        state = state,
        quarantineReason = quarantineReason,
    )
}
