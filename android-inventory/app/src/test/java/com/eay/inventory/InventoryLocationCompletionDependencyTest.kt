package com.eay.inventory

import org.junit.Assert.assertEquals
import org.junit.Test

class InventoryLocationCompletionDependencyTest {
    private val documentId = "22222222-2222-4222-8222-222222222222"

    @Test
    fun `pending same-location count line makes completion wait`() {
        assertEquals(
            LocationCompletionDependencyDecision.WAIT,
            InventoryLocationCompletionDependency.evaluate(
                completion(sequence = 2),
                listOf(countLine(sequence = 1, state = "PENDING")),
            ),
        )
    }

    @Test
    fun `retrying same-location count line makes completion wait`() {
        assertEquals(
            LocationCompletionDependencyDecision.WAIT,
            InventoryLocationCompletionDependency.evaluate(
                completion(sequence = 2),
                listOf(countLine(sequence = 1, state = "RETRY_WAIT")),
            ),
        )
    }

    @Test
    fun `quarantined same-location count line blocks completion`() {
        assertEquals(
            LocationCompletionDependencyDecision.BLOCKED,
            InventoryLocationCompletionDependency.evaluate(
                completion(sequence = 2),
                listOf(countLine(sequence = 1, state = "QUARANTINED")),
            ),
        )
    }

    @Test
    fun `acked same-location count line allows completion`() {
        assertEquals(
            LocationCompletionDependencyDecision.CLEAR,
            InventoryLocationCompletionDependency.evaluate(
                completion(sequence = 2),
                listOf(countLine(sequence = 1, state = "ACKED")),
            ),
        )
    }

    @Test
    fun `unsettled different location does not block this completion`() {
        assertEquals(
            LocationCompletionDependencyDecision.CLEAR,
            InventoryLocationCompletionDependency.evaluate(
                completion(sequence = 3),
                listOf(countLine(sequence = 1, state = "QUARANTINED", locationId = "B-05")),
            ),
        )
    }

    @Test
    fun `malformed prior durable event blocks ambiguous completion ordering`() {
        val malformed = OfflineEvent(
            eventId = "11111111-1111-4111-8111-111111111111",
            deviceSequence = 1,
            canonicalPayload = "{}",
            payloadHash = "a".repeat(64),
            authBindingId = "binding-1",
            state = "QUARANTINED",
        )
        assertEquals(
            LocationCompletionDependencyDecision.BLOCKED,
            InventoryLocationCompletionDependency.evaluate(completion(sequence = 2), listOf(malformed)),
        )
    }

    private fun countLine(
        sequence: Long,
        state: String,
        locationId: String = "A-04",
    ) = OfflineEvent(
        eventId = "11111111-1111-4111-8111-${sequence.toString().padStart(12, '0')}",
        deviceSequence = sequence,
        canonicalPayload =
            "{\"document_id\":\"$documentId\",\"location_id\":\"$locationId\",\"barcode\":\"869\"}",
        payloadHash = "b".repeat(64),
        authBindingId = "binding-1",
        state = state,
    )

    private fun completion(sequence: Long) = OfflineEvent(
        eventId = "33333333-3333-4333-8333-${sequence.toString().padStart(12, '0')}",
        deviceSequence = sequence,
        canonicalPayload =
            "{\"document_id\":\"$documentId\",\"event_kind\":\"LOCATION_COMPLETE\",\"location_id\":\"A-04\"}",
        payloadHash = "c".repeat(64),
        authBindingId = "binding-1",
    )
}
