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
                confirmedLineCount = 3,
                deviceSequence = 8,
                documentId = "22222222-2222-4222-8222-222222222222",
                eventId = "33333333-3333-4333-8333-333333333333",
                locationId = " a-04 ",
                occurredAt = "2026-08-18T15:05:00Z",
            ),
        )
        val expected =
            "{\"active_shift_id\":\"SHIFT-20260818-001\",\"confirmed_line_count\":3," +
                "\"device_sequence\":8," +
                "\"document_id\":\"22222222-2222-4222-8222-222222222222\"," +
                "\"event_id\":\"33333333-3333-4333-8333-333333333333\"," +
                "\"event_kind\":\"LOCATION_COMPLETE\",\"location_id\":\"A-04\"," +
                "\"occurred_at\":\"2026-08-18T15:05:00Z\"}"
        assertEquals(expected, body)
        assertEquals(
            "96cdbfae950df83e725c3c269a8be900a0ee85880977575afa06cbde88eec7d0",
            LocationCompletionCanonical.hash(body),
        )
    }

    @Test
    fun `completion factory binds shift count location and auth session into durable event`() {
        val event = InventoryLocationCompletionEventFactory.create(
            context = InventoryCountEventContext(
                missionId = "inventory.count:mission-1",
                documentId = "22222222-2222-4222-8222-222222222222",
                activeShiftId = "SHIFT-20260818-001",
                locationId = "A-04",
            ),
            confirmedLineCount = 3,
            deviceSequence = 8,
            eventId = "33333333-3333-4333-8333-333333333333",
            occurredAt = "2026-08-18T15:05:00Z",
            authBindingId = "session-a",
        )
        assertEquals("session-a", event.authBindingId)
        assertEquals(8, event.deviceSequence)
        assertTrue(event.canonicalPayload.contains("\"active_shift_id\":\"SHIFT-20260818-001\""))
        assertTrue(event.canonicalPayload.contains("\"confirmed_line_count\":3"))
        assertTrue(event.canonicalPayload.contains("\"event_kind\":\"LOCATION_COMPLETE\""))
        assertTrue(QueueIntegrity.valid(event, "session-a"))
    }

    @Test
    fun `empty location completion keeps zero line count in signed payload`() {
        val body = LocationCompletionCanonical.body(
            LocationCompletionInput(
                activeShiftId = "SHIFT-20260818-001",
                confirmedLineCount = 0,
                deviceSequence = 9,
                documentId = "22222222-2222-4222-8222-222222222222",
                eventId = "44444444-4444-4444-8444-444444444444",
                locationId = "A-05",
                occurredAt = "2026-08-18T15:06:00Z",
            ),
        )
        assertTrue(body.contains("\"confirmed_line_count\":0"))
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
