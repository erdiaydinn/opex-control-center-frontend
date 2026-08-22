package com.eay.inventory

import com.eay.mobile.core.MobileRuntimeProfile
import org.junit.Assert.assertEquals
import org.junit.Test

class InventoryLocalMissionTruthTest {
    private val task = InventoryTerminalCountTask(
        missionId = "inventory.count:mission-1",
        documentId = "22222222-2222-4222-8222-222222222222",
        activeShiftId = "shift-1",
        warehouseId = "FULYA",
        locationId = "A-04",
        name = "Weekly count",
        state = "COUNTING",
        revision = 1,
        locationCount = 2,
        operation = "inventory.count",
        runtimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
    )

    @Test
    fun `pending completion keeps mission awaiting server`() {
        assertEquals(
            InventoryLocalCompletionState.AWAITING_SERVER,
            InventoryLocalMissionTruth.stateFor(task, listOf(completion("PENDING"))),
        )
        assertEquals(
            InventoryLocalCompletionState.AWAITING_SERVER,
            InventoryLocalMissionTruth.stateFor(task, listOf(completion("RETRY_WAIT"))),
        )
    }

    @Test
    fun `quarantined completion keeps mission closed for review`() {
        assertEquals(
            InventoryLocalCompletionState.REQUIRES_REVIEW,
            InventoryLocalMissionTruth.stateFor(task, listOf(completion("QUARANTINED"))),
        )
    }

    @Test
    fun `quarantine wins over retry when duplicate local evidence exists`() {
        assertEquals(
            InventoryLocalCompletionState.REQUIRES_REVIEW,
            InventoryLocalMissionTruth.stateFor(
                task,
                listOf(completion("RETRY_WAIT", sequence = 10), completion("QUARANTINED", sequence = 11)),
            ),
        )
    }

    @Test
    fun `acked or unrelated completion cannot close an open mission locally`() {
        assertEquals(
            InventoryLocalCompletionState.OPEN,
            InventoryLocalMissionTruth.stateFor(task, listOf(completion("ACKED"))),
        )
        assertEquals(
            InventoryLocalCompletionState.OPEN,
            InventoryLocalMissionTruth.stateFor(
                task,
                listOf(completion("PENDING", locationId = "B-05")),
            ),
        )
    }

    @Test
    fun `location binding follows canonical trim and uppercase semantics`() {
        assertEquals(
            InventoryLocalCompletionState.AWAITING_SERVER,
            InventoryLocalMissionTruth.stateFor(
                task,
                listOf(completion("PENDING", locationId = " a-04 ")),
            ),
        )
    }

    @Test
    fun `unknown unsettled state fails closed`() {
        assertEquals(
            InventoryLocalCompletionState.REQUIRES_REVIEW,
            InventoryLocalMissionTruth.stateFor(task, listOf(completion("MYSTERY"))),
        )
    }

    private fun completion(
        state: String,
        locationId: String = "A-04",
        sequence: Long = 9,
    ): OfflineEvent {
        val canonical = LocationCompletionCanonical.body(
            LocationCompletionInput(
                activeShiftId = "shift-1",
                attemptId = ATTEMPT_ID,
                confirmedLineCount = 2,
                deviceSequence = sequence,
                documentId = task.documentId,
                eventId = "11111111-1111-4111-8111-${sequence.toString().padStart(12, '0')}",
                leaseId = LEASE_ID,
                locationId = locationId,
                occurredAt = "2026-08-18T15:00:00Z",
            ),
        )
        return OfflineEvent(
            eventId = "11111111-1111-4111-8111-${sequence.toString().padStart(12, '0')}",
            deviceSequence = sequence,
            canonicalPayload = canonical,
            payloadHash = LocationCompletionCanonical.hash(canonical),
            authBindingId = "binding-1",
            state = state,
        )
    }

    companion object {
        private const val ATTEMPT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        private const val LEASE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    }
}
