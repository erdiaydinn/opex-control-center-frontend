package com.eay.inventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryLocationCompletionEventFactoryTest {
    private val context = InventoryCountEventContext(
        missionId = "inventory.count:mission-a",
        documentId = "22222222-2222-4222-8222-222222222222",
        activeShiftId = "SHIFT-20260818-001",
        locationId = " a-04 ",
    )

    @Test
    fun `completion canonical body matches backend golden vector`() {
        val event = InventoryLocationCompletionEventFactory.create(
            context = context,
            confirmedLineCount = 3,
            deviceSequence = 8,
            eventId = "33333333-3333-4333-8333-333333333333",
            occurredAt = "2026-08-18T15:05:00Z",
            authBindingId = "binding-1",
        )
        val expected =
            "{\"active_shift_id\":\"SHIFT-20260818-001\",\"confirmed_line_count\":3," +
                "\"device_sequence\":8,\"document_id\":\"22222222-2222-4222-8222-222222222222\"," +
                "\"event_id\":\"33333333-3333-4333-8333-333333333333\"," +
                "\"event_kind\":\"LOCATION_COMPLETE\",\"location_id\":\"A-04\"," +
                "\"occurred_at\":\"2026-08-18T15:05:00Z\"}"

        assertEquals(expected, event.canonicalPayload)
        assertEquals(
            "96cdbfae950df83e725c3c269a8be900a0ee85880977575afa06cbde88eec7d0",
            event.payloadHash,
        )
    }

    @Test
    fun `verified empty location can carry explicit zero line count`() {
        val event = InventoryLocationCompletionEventFactory.create(
            context = context,
            confirmedLineCount = 0,
            deviceSequence = 9,
            eventId = "44444444-4444-4444-8444-444444444444",
            occurredAt = "2026-08-18T15:06:00Z",
            authBindingId = "binding-1",
        )
        assertTrue(event.canonicalPayload.contains("\"confirmed_line_count\":0"))
    }
}
