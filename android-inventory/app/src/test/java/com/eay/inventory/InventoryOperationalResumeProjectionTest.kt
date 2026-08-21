package com.eay.inventory

import com.eay.mobile.core.OperationalMissionDefinition
import com.eay.mobile.core.OperationalMissionType
import com.eay.mobile.core.OperationalStepKind
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryOperationalResumeProjectionTest {
    private val missionId = "11111111-1111-1111-1111-111111111111"
    private val claimId = "22222222-2222-2222-2222-222222222222"
    private val authBinding = "AUTH-1"

    @Test
    fun `valid same-claim durable prefix resumes at the first unrecorded step`() {
        val task = pickingTask()
        val events = listOf(
            event(OperationalStepKind.SOURCE_LOCATION, "A01", 11, "33333333-3333-3333-3333-333333333331"),
            event(OperationalStepKind.ITEM, "8690000000001", 12, "33333333-3333-3333-3333-333333333332"),
        )

        assertEquals(
            InventoryLocalCompletionState.OPEN,
            InventoryOperationalLocalTruth.classify(listOf(task), events)[missionId],
        )
        val projection = InventoryOperationalLocalTruth.project(
            task,
            events,
            authBinding,
            claimId,
        )
        assertEquals(InventoryLocalCompletionState.OPEN, projection.state)
        assertEquals(2, projection.evidence.size)
        assertEquals(OperationalStepKind.QUANTITY, projection.nextStep)
        assertEquals(claimId, projection.localClaimId)

        val seeded = InventoryOperationalResumeSession.seed(
            task,
            InventoryOperationalClaim(
                missionId = missionId,
                claimId = claimId,
                activeShiftId = "SHIFT-A",
                nextStep = OperationalStepKind.SOURCE_LOCATION,
                resumeEvidence = projection.evidence,
            ),
            projection.evidence,
        )
        assertEquals(OperationalStepKind.QUANTITY, seeded.nextStep)
        assertEquals(2, seeded.evidence.size)
    }

    @Test
    fun `current auth binding substitution fails closed`() {
        val task = pickingTask()
        val projection = InventoryOperationalLocalTruth.project(
            task,
            listOf(event(OperationalStepKind.SOURCE_LOCATION, "A01", 11, "33333333-3333-3333-3333-333333333331")),
            "AUTH-OTHER",
            claimId,
        )
        assertEquals(InventoryLocalCompletionState.REQUIRES_REVIEW, projection.state)
    }

    @Test
    fun `fresh server claim must equal the durable local claim`() {
        val task = pickingTask()
        val projection = InventoryOperationalLocalTruth.project(
            task,
            listOf(event(OperationalStepKind.SOURCE_LOCATION, "A01", 11, "33333333-3333-3333-3333-333333333331")),
            authBinding,
            "99999999-9999-9999-9999-999999999999",
        )
        assertEquals(InventoryLocalCompletionState.REQUIRES_REVIEW, projection.state)
    }

    @Test
    fun `step gaps never become local workflow authority`() {
        val task = pickingTask()
        val projection = InventoryOperationalLocalTruth.project(
            task,
            listOf(event(OperationalStepKind.ITEM, "8690000000001", 11, "33333333-3333-3333-3333-333333333331")),
            authBinding,
            claimId,
        )
        assertEquals(InventoryLocalCompletionState.REQUIRES_REVIEW, projection.state)
    }

    @Test
    fun `server-ahead overlap waits for signed exact replay instead of guessing`() {
        val task = pickingTask(completedSteps = 1)
        val sourceStillLocal = event(
            OperationalStepKind.SOURCE_LOCATION,
            "A01",
            11,
            "33333333-3333-3333-3333-333333333331",
        )
        val projection = InventoryOperationalLocalTruth.project(
            task,
            listOf(sourceStillLocal),
            authBinding,
            claimId,
        )
        assertEquals(InventoryLocalCompletionState.AWAITING_SERVER, projection.state)
        assertTrue(projection.evidence.isEmpty())
    }

    @Test
    fun `locally completed mission waits for server reconciliation`() {
        val task = pickingTask()
        val events = listOf(
            event(OperationalStepKind.SOURCE_LOCATION, "A01", 11, "33333333-3333-3333-3333-333333333331"),
            event(OperationalStepKind.ITEM, "8690000000001", 12, "33333333-3333-3333-3333-333333333332"),
            event(OperationalStepKind.QUANTITY, "4", 13, "33333333-3333-3333-3333-333333333333"),
            event(OperationalStepKind.CONTAINER, "TOTE-1", 14, "33333333-3333-3333-3333-333333333334"),
            event(OperationalStepKind.COMPLETE, "COMPLETE", 15, "33333333-3333-3333-3333-333333333335"),
        )
        val projection = InventoryOperationalLocalTruth.project(
            task,
            events,
            authBinding,
            claimId,
        )
        assertEquals(InventoryLocalCompletionState.AWAITING_SERVER, projection.state)
    }

    @Test
    fun `raw value tampering is detected even though transport payload hash excludes raw value`() {
        val task = pickingTask()
        val original = event(
            OperationalStepKind.SOURCE_LOCATION,
            "A01",
            11,
            "33333333-3333-3333-3333-333333333331",
        )
        val tamperedPayload = JSONObject(original.canonicalPayload)
            .put("value", "A02")
            .toString()
        // Backend transport hash deliberately excludes raw value. The restart projector
        // must still recompute the typed value hash before allowing local resume.
        assertEquals(original.payloadHash, InventoryOperationalEventCanonical.payloadHash(tamperedPayload))
        val projection = InventoryOperationalLocalTruth.project(
            task,
            listOf(original.copy(canonicalPayload = tamperedPayload)),
            authBinding,
            claimId,
        )
        assertEquals(InventoryLocalCompletionState.REQUIRES_REVIEW, projection.state)
    }

    private fun pickingTask(completedSteps: Int = 0): InventoryOperationalTask {
        val definition = OperationalMissionDefinition.picking(missionId)
        return InventoryOperationalTask(
            missionId = missionId,
            activeShiftId = "SHIFT-A",
            warehouseId = "WH-1",
            missionType = OperationalMissionType.PICKING,
            operation = definition.operation,
            externalReference = "PICK-REF-1",
            state = "CLAIMED",
            steps = definition.steps,
            completedSteps = completedSteps,
            totalSteps = definition.steps.size,
            nextStep = definition.steps[completedSteps],
            claimStatus = "RESUMABLE",
            skuId = "SKU-1",
            plannedQuantity = "4",
            sourceLocationId = "A01",
            destinationLocationId = null,
            containerId = "TOTE-1",
            allowedConditions = emptyList(),
        )
    }

    private fun event(
        step: OperationalStepKind,
        value: String,
        sequence: Long,
        eventId: String,
        eventClaimId: String = claimId,
        eventAuthBinding: String = authBinding,
    ): OfflineEvent = InventoryOperationalEventCanonical.create(
        InventoryOperationalEventInput(
            context = InventoryOperationalEventContext(
                missionId = missionId,
                claimId = eventClaimId,
                activeShiftId = "SHIFT-A",
            ),
            stepKind = step,
            rawValue = value,
            eventId = eventId,
            deviceSequence = sequence,
            occurredAt = "2026-08-21T07:00:00Z",
        ),
        eventAuthBinding,
    )
}
