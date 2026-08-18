package com.eay.inventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LocationCompletionContractTest {
    @Test
    fun `completion canonical payload matches backend golden vector`() {
        val body = LocationCompletionCanonical.body(
            LocationCompletionInput(
                activeShiftId = " SHIFT-20260818-001 ",
                deviceSequence = 8,
                documentId = "22222222-2222-4222-8222-222222222222",
                eventId = "33333333-3333-4333-8333-333333333333",
                locationId = " a-04 ",
                occurredAt = "2026-08-18T15:05:00Z",
            ),
        )
        val expected =
            "{\"active_shift_id\":\"SHIFT-20260818-001\",\"device_sequence\":8," +
                "\"document_id\":\"22222222-2222-4222-8222-222222222222\"," +
                "\"event_id\":\"33333333-3333-4333-8333-333333333333\"," +
                "\"event_kind\":\"LOCATION_COMPLETE\",\"location_id\":\"A-04\"," +
                "\"occurred_at\":\"2026-08-18T15:05:00Z\"}"
        assertEquals(expected, body)
        assertEquals(
            "631e5b6c4447c10bda695763e432cccae8af623426eab370ee3db9d1cd4ab6ba",
            LocationCompletionCanonical.hash(body),
        )
    }

    @Test
    fun `completion factory binds shift location and auth session into durable event`() {
        val event = InventoryLocationCompletionEventFactory.create(
            context = InventoryCountEventContext(
                missionId = "inventory.count:mission-1",
                documentId = "22222222-2222-4222-8222-222222222222",
                activeShiftId = "SHIFT-20260818-001",
                locationId = "A-04",
            ),
            deviceSequence = 8,
            eventId = "33333333-3333-4333-8333-333333333333",
            occurredAt = "2026-08-18T15:05:00Z",
            authBindingId = "session-a",
        )
        assertEquals("session-a", event.authBindingId)
        assertEquals(8, event.deviceSequence)
        assertTrue(event.canonicalPayload.contains("\"active_shift_id\":\"SHIFT-20260818-001\""))
        assertTrue(event.canonicalPayload.contains("\"event_kind\":\"LOCATION_COMPLETE\""))
        assertTrue(QueueIntegrity.valid(event, "session-a"))
    }

    @Test
    fun `sync routing admits only count line or location completion contracts`() {
        val countLine = """{"active_shift_id":"SHIFT-1","barcode":"869"}"""
        val completion =
            """{"active_shift_id":"SHIFT-1","event_kind":"LOCATION_COMPLETE"}"""
        val unknown = """{"active_shift_id":"SHIFT-1","event_kind":"DELETE_ALL"}"""

        assertEquals(
            "/api/inventory/v1/terminal/events",
            InventorySyncContract.endpointPath(countLine),
        )
        assertEquals(
            "/api/inventory/v1/terminal/location-completions",
            InventorySyncContract.endpointPath(completion),
        )
        assertNull(InventorySyncContract.endpointPath(unknown))
        assertNull(InventorySyncContract.endpointPath("not-json"))
    }
}
