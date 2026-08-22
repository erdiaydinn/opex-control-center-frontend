package com.eay.inventory

import com.eay.mobile.core.BlindCountLocationToken
import com.eay.mobile.core.MobileRuntimeProfile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryTerminalCountTaskTest {
    @Test
    fun `owned location mission maps to blind target and lease-bound event context`() {
        val task = task(locationId = " a-04 ", owned = true)

        val target = task.blindCountTarget()
        val context = task.eventContext()

        assertEquals("inventory.count:mission-1", target.missionId)
        assertEquals(BlindCountLocationToken.hash("A-04"), target.locationTokenHash)
        assertEquals("22222222-2222-4222-8222-222222222222", context.documentId)
        assertEquals("SHIFT-20260818-001", context.activeShiftId)
        assertEquals(ATTEMPT_ID, context.attemptId)
        assertEquals(LEASE_ID, context.leaseId)
        assertEquals(" a-04 ", context.locationId)
        assertEquals(MobileRuntimeProfile.EAY_TERMINAL, task.runtimeProfile)
    }

    @Test
    fun `available mission cannot create event authority`() {
        val available = task()
        assertThrows(IllegalArgumentException::class.java) { available.eventContext() }
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
    fun `owned mission requires complete lease tuple`() {
        assertThrows(IllegalArgumentException::class.java) {
            task(owned = true, leaseId = null)
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
        owned: Boolean = false,
        leaseId: String? = if (owned) LEASE_ID else null,
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
        claimStatus = if (owned) InventoryMissionClaimStatus.OWNED else InventoryMissionClaimStatus.AVAILABLE,
        attemptId = if (owned) ATTEMPT_ID else null,
        leaseId = leaseId,
        leaseValidUntil = if (owned) "2026-08-18T15:15:00Z" else null,
    )

    companion object {
        private const val ATTEMPT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        private const val LEASE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    }
}
