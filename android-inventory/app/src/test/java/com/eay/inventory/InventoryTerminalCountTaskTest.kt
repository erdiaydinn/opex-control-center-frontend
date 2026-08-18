package com.eay.inventory

import com.eay.mobile.core.BlindCountLocationToken
import com.eay.mobile.core.MobileRuntimeProfile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryTerminalCountTaskTest {
    @Test
    fun `location mission maps to blind target and durable event context`() {
        val task = task(locationId = " a-04 ")

        val target = task.blindCountTarget()
        val context = task.eventContext()

        assertEquals("inventory.count:mission-1", target.missionId)
        assertEquals(BlindCountLocationToken.hash("A-04"), target.locationTokenHash)
        assertEquals("22222222-2222-4222-8222-222222222222", context.documentId)
        assertEquals("SHIFT-20260818-001", context.activeShiftId)
        assertEquals(" a-04 ", context.locationId)
        assertEquals(MobileRuntimeProfile.EAY_TERMINAL, task.runtimeProfile)
    }

    @Test
    fun `task contract contains no expected stock authority`() {
        val fields = InventoryTerminalCountTask::class.java.declaredFields
            .map { it.name.lowercase() }
        assertTrue(
            fields.none {
                it.contains("expected") ||
                    it.contains("systemstock") ||
                    it.contains("cost") ||
                    it.contains("variance") ||
                    it.contains("sku")
            },
        )
    }

    @Test
    fun `missing server shift provenance fails closed`() {
        assertThrows(IllegalArgumentException::class.java) {
            task(activeShiftId = "")
        }
    }

    @Test
    fun `non counting task fails closed`() {
        assertThrows(IllegalArgumentException::class.java) {
            task(state = "APPROVED")
        }
    }

    private fun task(
        locationId: String = "A-04",
        state: String = "COUNTING",
        activeShiftId: String = "SHIFT-20260818-001",
    ) = InventoryTerminalCountTask(
        missionId = "inventory.count:mission-1",
        documentId = "22222222-2222-4222-8222-222222222222",
        activeShiftId = activeShiftId,
        warehouseId = "FULYA",
        locationId = locationId,
        name = "Weekly cycle count",
        state = state,
        revision = 1,
        locationCount = 12,
    )
}
