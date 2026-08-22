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
                attemptId = ATTEMPT_ID,
                confirmedLineCount = 3,
                deviceSequence = 8,
                documentId = DOCUMENT_ID,
                eventId = "33333333-3333-4333-8333-333333333333",
                leaseId = LEASE_ID,
                locationId = " a-04 ",
                occurredAt = "2026-08-18T15:05:00Z",
            ),
        )
        val expected =
            "{\"active_shift_id\":\"SHIFT-20260818-001\"," +
                "\"attempt_id\":\"$ATTEMPT_ID\",\"confirmed_line_count\":3," +
                "\"device_sequence\":8,\"document_id\":\"$DOCUMENT_ID\"," +
                "\"event_id\":\"33333333-3333-4333-8333-333333333333\"," +
                "\"event_kind\":\"LOCATION_COMPLETE\",\"lease_id\":\"$LEASE_ID\"," +
                "\"location_id\":\"A-04\",\"occurred_at\":\"2026-08-18T15:05:00Z\"}"
        assertEquals(expected, body)
        assertEquals(
            "4a070151035e5a333931d0567f2ad5cb320eaf63a4dbcf44d3cfa7d41a9cab5b",
            LocationCompletionCanonical.hash(body),
        )
    }

    @Test
    fun `completion factory binds shift attempt lease count location and auth session`() {
        val event = InventoryLocationCompletionEventFactory.create(
            context = context(),
            confirmedLineCount = 3,
            deviceSequence = 8,
            eventId = "33333333-3333-4333-8333-333333333333",
            occurredAt = "2026-08-18T15:05:00Z",
            authBindingId = "session-a",
        )
        assertEquals("session-a", event.authBindingId)
        assertEquals(8, event.deviceSequence)
        assertTrue(event.canonicalPayload.contains("\"active_shift_id\":\"SHIFT-20260818-001\""))
        assertTrue(event.canonicalPayload.contains("\"attempt_id\":\"$ATTEMPT_ID\""))
        assertTrue(event.canonicalPayload.contains("\"lease_id\":\"$LEASE_ID\""))
        assertTrue(event.canonicalPayload.contains("\"confirmed_line_count\":3"))
        assertTrue(event.canonicalPayload.contains("\"event_kind\":\"LOCATION_COMPLETE\""))
        assertTrue(QueueIntegrity.valid(event, "session-a"))
    }

    @Test
    fun `empty location completion keeps zero line count in signed payload`() {
        val body = LocationCompletionCanonical.body(
            LocationCompletionInput(
                activeShiftId = "SHIFT-20260818-001",
                attemptId = ATTEMPT_ID,
                confirmedLineCount = 0,
                deviceSequence = 9,
                documentId = DOCUMENT_ID,
                eventId = "44444444-4444-4444-8444-444444444444",
                leaseId = LEASE_ID,
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

    private fun context() = InventoryCountEventContext(
        missionId = "inventory.count:mission-1",
        documentId = DOCUMENT_ID,
        activeShiftId = "SHIFT-20260818-001",
        attemptId = ATTEMPT_ID,
        leaseId = LEASE_ID,
        locationId = "A-04",
    )

    companion object {
        private const val DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
        private const val ATTEMPT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        private const val LEASE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    }
}
