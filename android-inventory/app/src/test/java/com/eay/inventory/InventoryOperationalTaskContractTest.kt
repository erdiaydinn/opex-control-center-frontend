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
            val definition = when (type) {
                OperationalMissionType.PICKING -> OperationalMissionDefinition.picking("11111111-1111-1111-1111-111111111111")
                OperationalMissionType.PUTAWAY -> OperationalMissionDefinition.putaway("11111111-1111-1111-1111-111111111111")
                OperationalMissionType.RECEIVING -> OperationalMissionDefinition.receiving("11111111-1111-1111-1111-111111111111")
                OperationalMissionType.TRANSFER -> OperationalMissionDefinition.transfer("11111111-1111-1111-1111-111111111111")
            }
            val task = InventoryOperationalTask(
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
                sourceLocationId = "A01",
                destinationLocationId = "B02",
                containerId = "TOTE-1",
                allowedConditions = listOf("GOOD"),
            )
            assertEquals(task, InventoryOperationalTaskContract.validate(task))
        }
    }

    @Test
    fun `task contract rejects execution-only fields and step drift`() {
        assertTrue(runCatching {
            InventoryOperationalTaskContract.rejectForbiddenFields(setOf("mission_id", "item_value_hash"))
        }.isFailure)

        val definition = OperationalMissionDefinition.picking("11111111-1111-1111-1111-111111111111")
        val drifted = InventoryOperationalTask(
            missionId = definition.missionId,
            activeShiftId = "SHIFT-A",
            warehouseId = "WH-1",
            missionType = OperationalMissionType.PICKING,
            operation = definition.operation,
            externalReference = "REF-1",
            state = "OPEN",
            steps = definition.steps.dropLast(1),
            completedSteps = 0,
            totalSteps = definition.steps.size - 1,
            nextStep = definition.steps.first(),
            claimStatus = "AVAILABLE",
            skuId = "SKU-1",
            plannedQuantity = "1",
            sourceLocationId = "A01",
            destinationLocationId = null,
            containerId = "TOTE-1",
            allowedConditions = listOf("GOOD"),
        )
        assertTrue(runCatching { InventoryOperationalTaskContract.validate(drifted) }.isFailure)
    }
}
