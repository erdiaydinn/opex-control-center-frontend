package com.eay.inventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryTerminalTaskClientTest {
    @Test
    fun `wire rows map to unique location-bound count missions`() {
        val tasks = InventoryTerminalTaskContract.map(
            listOf(
                row(
                    missionId = "inventory.count:mission-a",
                    locationId = " A-04 ",
                ),
                row(
                    missionId = "inventory.count:mission-b",
                    locationId = "B-05",
                ),
            ),
        )

        assertEquals(2, tasks.size)
        assertEquals(" A-04 ", tasks[0].locationId)
        assertEquals("SHIFT-20260818-001", tasks[0].activeShiftId)
        assertEquals("inventory.count", tasks[0].operation)
        assertEquals("EAY_TERMINAL", tasks[0].runtimeProfile.name)
    }

    @Test
    fun `missing server shift provenance fails closed`() {
        assertThrows(IllegalArgumentException::class.java) {
            InventoryTerminalTaskContract.map(
                listOf(row("inventory.count:a", "A-04", activeShiftId = "")),
            )
        }
    }

    @Test
    fun `duplicate mission id fails closed`() {
        assertThrows(IllegalArgumentException::class.java) {
            InventoryTerminalTaskContract.map(
                listOf(
                    row("inventory.count:same", "A-04"),
                    row("inventory.count:same", "B-05"),
                ),
            )
        }
    }

    @Test
    fun `duplicate document location binding fails closed after normalization`() {
        assertThrows(IllegalArgumentException::class.java) {
            InventoryTerminalTaskContract.map(
                listOf(
                    row("inventory.count:a", "A-04"),
                    row("inventory.count:b", " a-04 "),
                ),
            )
        }
    }

    @Test
    fun `wrong operation or runtime profile fails closed`() {
        assertThrows(IllegalArgumentException::class.java) {
            InventoryTerminalTaskContract.map(
                listOf(row("inventory.count:a", "A-04", operation = "inventory.approve")),
            )
        }
        assertThrows(IllegalArgumentException::class.java) {
            InventoryTerminalTaskContract.map(
                listOf(row("inventory.count:a", "A-04", runtimeProfile = "EAY_ONE")),
            )
        }
    }

    @Test
    fun `stock truth fields are rejected before parsing`() {
        assertThrows(IllegalArgumentException::class.java) {
            InventoryTerminalTaskContract.rejectForbiddenFieldNames(
                setOf("mission_id", "location_id", "expected_quantity"),
            )
        }
        assertThrows(IllegalArgumentException::class.java) {
            InventoryTerminalTaskContract.rejectForbiddenFieldNames(
                setOf("mission_id", "location_id", "Variance_Value"),
            )
        }
    }

    @Test
    fun `http classification has no anonymous fallback`() {
        assertEquals(
            InventoryTaskFetchCode.AUTH_REQUIRED,
            InventoryTerminalTaskContract.classifyHttp(401),
        )
        assertEquals(
            InventoryTaskFetchCode.POLICY_REJECTED,
            InventoryTerminalTaskContract.classifyHttp(403),
        )
        assertEquals(
            InventoryTaskFetchCode.RETRYABLE,
            InventoryTerminalTaskContract.classifyHttp(503),
        )
        assertEquals(
            InventoryTaskFetchCode.PERMANENT_REJECTED,
            InventoryTerminalTaskContract.classifyHttp(422),
        )
        assertTrue(InventoryTerminalTaskContract.classifyHttp(200) == InventoryTaskFetchCode.OK)
    }

    private fun row(
        missionId: String,
        locationId: String,
        activeShiftId: String = "SHIFT-20260818-001",
        operation: String = "inventory.count",
        runtimeProfile: String = "EAY_TERMINAL",
    ) = InventoryTerminalTaskWire(
        missionId = missionId,
        documentId = "22222222-2222-4222-8222-222222222222",
        activeShiftId = activeShiftId,
        warehouseId = "FULYA",
        locationId = locationId,
        name = "Weekly cycle count",
        state = "COUNTING",
        revision = 3,
        locationCount = 2,
        operation = operation,
        runtimeProfile = runtimeProfile,
    )
}
