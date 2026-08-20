package com.eay.inventory

import com.eay.mobile.core.OperationalMissionDefinition
import com.eay.mobile.core.OperationalMissionType
import org.junit.Assert.assertEquals
import org.junit.Test

class InventoryOperationalLocalTruthTest {
    private val missionId = "11111111-1111-1111-1111-111111111111"

    @Test
    fun `pending operational evidence blocks restart until server settles it`() {
        val task = task()
        val pending = event("PENDING")
        assertEquals(
            InventoryLocalCompletionState.AWAITING_SERVER,
            InventoryOperationalLocalTruth.stateFor(task, listOf(pending)),
        )
        assertEquals(
            InventoryLocalCompletionState.OPEN,
            InventoryOperationalLocalTruth.stateFor(task, listOf(pending.copy(state = "ACKED"))),
        )
    }

    @Test
    fun `quarantined or unknown durable state fails closed`() {
        val task = task()
        assertEquals(
            InventoryLocalCompletionState.REQUIRES_REVIEW,
            InventoryOperationalLocalTruth.stateFor(task, listOf(event("QUARANTINED"))),
        )
        assertEquals(
            InventoryLocalCompletionState.REQUIRES_REVIEW,
            InventoryOperationalLocalTruth.stateFor(task, listOf(event("MYSTERY"))),
        )
    }

    @Test
    fun `count completion evidence does not bind an operational mission`() {
        val countPayload = """{"event_kind":"LOCATION_COMPLETE","document_id":"22222222-2222-2222-2222-222222222222","location_id":"A01"}"""
        assertEquals(null, InventoryOperationalLocalTruth.missionBinding(countPayload))
    }

    private fun task(): InventoryOperationalTask {
        val definition = OperationalMissionDefinition.picking(missionId)
        return InventoryOperationalTask(
            missionId = missionId,
            activeShiftId = "SHIFT-A",
            warehouseId = "WH-1",
            missionType = OperationalMissionType.PICKING,
            operation = definition.operation,
            externalReference = "REF-1",
            state = "OPEN",
            steps = definition.steps,
            completedSteps = 0,
            totalSteps = definition.steps.size,
            nextStep = definition.steps.first(),
            claimStatus = "AVAILABLE",
            skuId = "SKU-1",
            plannedQuantity = "4",
            sourceLocationId = "A01",
            destinationLocationId = null,
            containerId = "TOTE-1",
            allowedConditions = emptyList(),
        )
    }

    private fun event(state: String) = OfflineEvent(
        eventId = "33333333-3333-3333-3333-333333333333",
        deviceSequence = 1,
        canonicalPayload = """{"active_shift_id":"SHIFT-A","claim_id":"44444444-4444-4444-4444-444444444444","device_sequence":1,"event_id":"33333333-3333-3333-3333-333333333333","mission_id":"$missionId","occurred_at":"2026-08-20T12:00:00Z","step_kind":"ITEM","value":"SKU-1","value_hash":"${"a".repeat(64)}"}""",
        payloadHash = "b".repeat(64),
        authBindingId = "AUTH-1",
        state = state,
    )
}
