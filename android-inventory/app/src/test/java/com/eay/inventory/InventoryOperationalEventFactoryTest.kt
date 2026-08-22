package com.eay.inventory

import com.eay.mobile.core.OperationalStepKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryOperationalEventFactoryTest {
    private val input = InventoryOperationalEventInput(
        context = InventoryOperationalEventContext(
            missionId = "11111111-1111-1111-1111-111111111111",
            claimId = "22222222-2222-2222-2222-222222222222",
            activeShiftId = "SHIFT-A",
        ),
        stepKind = OperationalStepKind.ITEM,
        rawValue = "8690000000001",
        eventId = "33333333-3333-3333-3333-333333333333",
        deviceSequence = 7,
        occurredAt = "2026-08-20T12:30:00Z",
    )

    @Test
    fun `operational event uses backend exact canonical hash vector`() {
        val event = InventoryOperationalEventCanonical.create(input, "binding-a")
        assertEquals(
            "52ec76c67f696b0361fcddb89f1e174448f5f304ea3ca735adde973f09f8cc3f",
            event.payloadHash,
        )
        assertEquals(event.payloadHash, InventoryOperationalEventCanonical.payloadHash(event.canonicalPayload))
        assertTrue(event.canonicalPayload.contains("\"value\":\"8690000000001\""))
        assertTrue(InventoryOperationalEventCanonical.isOperationalBody(event.canonicalPayload))
        assertEquals(InventorySyncContract.OPERATIONAL_EVENT_PATH, InventorySyncContract.endpointPath(event.canonicalPayload))
    }

    @Test
    fun `operational ack must match signed shift mission and claim`() {
        val body = InventoryOperationalEventCanonical.body(input)
        assertTrue(
            InventorySyncContract.responseMatchesOperational(
                body,
                "SHIFT-A",
                "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222",
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesOperational(
                body,
                "SHIFT-B",
                "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222",
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesOperational(
                body,
                "SHIFT-A",
                "44444444-4444-4444-4444-444444444444",
                "22222222-2222-2222-2222-222222222222",
            ),
        )
    }

    @Test
    fun `operational queue integrity detects hash substitution and session rebinding`() {
        val event = InventoryOperationalEventCanonical.create(input, "binding-a")
        assertEquals(null, InventoryQueueIntegrity.failureReason(event, "binding-a"))
        assertNotEquals(null, InventoryQueueIntegrity.failureReason(event.copy(payloadHash = "0".repeat(64)), "binding-a"))
        assertNotEquals(null, InventoryQueueIntegrity.failureReason(event, "binding-b"))
    }
}
