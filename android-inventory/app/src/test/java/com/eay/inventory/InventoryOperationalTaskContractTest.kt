package com.eay.inventory

import com.eay.mobile.core.OperationalMissionDefinition
import com.eay.mobile.core.OperationalMissionType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryOperationalTaskContractTest {
    @Test
    fun `all four operational task contracts match shared canonical definitions`() {
        OperationalMissionType.entries.forEach { type ->
            val definition = definition(type)
            val task = validTask(type, definition)
            assertEquals(task, InventoryOperationalTaskContract.validate(task))
        }
    }

    @Test
    fun `task contract rejects execution-only fields and step drift`() {
        assertTrue(runCatching {
            InventoryOperationalTaskContract.rejectForbiddenFields(setOf("mission_id", "item_value_hash"))
        }.isFailure)

        val definition = OperationalMissionDefinition.picking(MISSION_ID)
        val drifted = validTask(OperationalMissionType.PICKING, definition).copy(
            steps = definition.steps.dropLast(1),
            totalSteps = definition.steps.size - 1,
        )
        assertTrue(runCatching { InventoryOperationalTaskContract.validate(drifted) }.isFailure)
    }

    @Test
    fun `receiving requires server frozen condition choices`() {
        val definition = OperationalMissionDefinition.receiving(MISSION_ID)
        val missing = validTask(OperationalMissionType.RECEIVING, definition).copy(
            allowedConditions = emptyList(),
        )
        assertTrue(runCatching { InventoryOperationalTaskContract.validate(missing) }.isFailure)
    }

    @Test
    fun `non receiving missions reject unexpected condition choices`() {
        val definition = OperationalMissionDefinition.picking(MISSION_ID)
        val polluted = validTask(OperationalMissionType.PICKING, definition).copy(
            allowedConditions = listOf("GOOD"),
        )
        assertTrue(runCatching { InventoryOperationalTaskContract.validate(polluted) }.isFailure)
    }

    @Test
    fun `required physical guidance cannot be missing`() {
        val picking = validTask(
            OperationalMissionType.PICKING,
            OperationalMissionDefinition.picking(MISSION_ID),
        ).copy(sourceLocationId = null)
        assertTrue(runCatching { InventoryOperationalTaskContract.validate(picking) }.isFailure)

        val receiving = validTask(
            OperationalMissionType.RECEIVING,
            OperationalMissionDefinition.receiving(MISSION_ID),
        ).copy(containerId = null)
        assertTrue(runCatching { InventoryOperationalTaskContract.validate(receiving) }.isFailure)
    }

    @Test
    fun `planned quantity and condition list must be canonicalizable`() {
        val picking = validTask(
            OperationalMissionType.PICKING,
            OperationalMissionDefinition.picking(MISSION_ID),
        ).copy(plannedQuantity = "-1")
        assertTrue(runCatching { InventoryOperationalTaskContract.validate(picking) }.isFailure)

        val receiving = validTask(
            OperationalMissionType.RECEIVING,
            OperationalMissionDefinition.receiving(MISSION_ID),
        ).copy(allowedConditions = listOf("GOOD", "good"))
        assertTrue(runCatching { InventoryOperationalTaskContract.validate(receiving) }.isFailure)
    }

    private fun definition(type: OperationalMissionType) = when (type) {
        OperationalMissionType.PICKING -> OperationalMissionDefinition.picking(MISSION_ID)
        OperationalMissionType.PUTAWAY -> OperationalMissionDefinition.putaway(MISSION_ID)
        OperationalMissionType.RECEIVING -> OperationalMissionDefinition.receiving(MISSION_ID)
        OperationalMissionType.TRANSFER -> OperationalMissionDefinition.transfer(MISSION_ID)
    }

    private fun validTask(
        type: OperationalMissionType,
        definition: OperationalMissionDefinition,
    ) = InventoryOperationalTask(
        missionId = definition.missionId,
        activeShiftId = "SHIFT-A",
        warehouseId = "WH-1",
        missionType = type,
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
        sourceLocationId = if (definition.steps.any { it.name == "SOURCE_LOCATION" }) "A01" else null,
        destinationLocationId = if (definition.steps.any { it.name == "DESTINATION_LOCATION" }) "B02" else null,
        containerId = if (definition.steps.any { it.name == "CONTAINER" }) "TOTE-1" else null,
        allowedConditions = if (type == OperationalMissionType.RECEIVING) listOf("GOOD", "DAMAGED") else emptyList(),
    )

    companion object {
        private const val MISSION_ID = "11111111-1111-1111-1111-111111111111"
    }
}
