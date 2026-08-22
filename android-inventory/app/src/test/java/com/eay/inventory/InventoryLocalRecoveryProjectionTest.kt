package com.eay.inventory

import org.junit.Assert.assertEquals
import org.junit.Test

class InventoryLocalRecoveryProjectionTest {
    private val documentId = "22222222-2222-4222-8222-222222222222"

    private fun task() = InventoryTerminalCountTask(
        missionId = "inventory.count:test",
        documentId = documentId,
        activeShiftId = "SHIFT-1",
        warehouseId = "WH-1",
        locationId = "A01",
        name = "Count A01",
        state = "COUNTING",
        revision = 1,
        locationCount = 1,
    )

    private fun event(
        eventId: String,
        sequence: Long,
        canonicalPayload: String,
        state: String = "PENDING",
        reason: String? = null,
    ) = OfflineEvent(
        eventId = eventId,
        deviceSequence = sequence,
        canonicalPayload = canonicalPayload,
        payloadHash = "a".repeat(64),
        authBindingId = "binding",
        state = state,
        quarantineReason = reason,
    )

    @Test
    fun fullQueueDepthIncludesCountLinesWhileMissionTruthUsesCompletionOnly() {
        val countLine = event(
            eventId = "11111111-1111-4111-8111-000000000001",
            sequence = 1,
            canonicalPayload = """{"document_id":"$documentId","location_id":"A01","barcode":"8690000000001"}""",
        )
        val completion = event(
            eventId = "11111111-1111-4111-8111-000000000002",
            sequence = 2,
            canonicalPayload = """{"document_id":"$documentId","event_kind":"LOCATION_COMPLETE","location_id":"A01"}""",
        )

        val projection = InventoryLocalRecoveryProjectionReader.project(
            tasks = listOf(task()),
            unsettled = listOf(countLine, completion),
        )

        assertEquals(
            InventoryLocalCompletionState.AWAITING_SERVER,
            projection.missionTruth["inventory.count:test"],
        )
        val recovery = requireNotNull(projection.recovery)
        assertEquals(2, recovery.affectedEventCount)
        assertEquals(2, recovery.pendingEventCount)
        assertEquals(0, recovery.quarantinedEventCount)
    }

    @Test
    fun quarantinedCountLineSurfacesRecoveryEvenWithoutLocationCompletion() {
        val quarantined = event(
            eventId = "11111111-1111-4111-8111-000000000003",
            sequence = 1,
            canonicalPayload = """{"document_id":"$documentId","location_id":"A01","barcode":"8690000000001"}""",
            state = "QUARANTINED",
            reason = "BUSINESS_CONFLICT",
        )

        val projection = InventoryLocalRecoveryProjectionReader.project(
            tasks = listOf(task()),
            unsettled = listOf(quarantined),
        )

        assertEquals(
            InventoryLocalCompletionState.OPEN,
            projection.missionTruth["inventory.count:test"],
        )
        val recovery = requireNotNull(projection.recovery)
        assertEquals(InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW, recovery.primaryIntent)
        assertEquals(1, recovery.quarantinedEventCount)
    }
}
