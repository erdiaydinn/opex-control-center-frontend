package com.eay.inventory

import com.eay.mobile.core.AcceptedScan
import com.eay.mobile.core.BarcodeSymbology
import com.eay.mobile.core.BlindCountStep
import com.eay.mobile.core.BlindCountTarget
import com.eay.mobile.core.ScannerSource
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class BlindCountTerminalControllerTest {
    @Test
    fun `confirmed line advances only after durable queue insert`() = runBlocking {
        val sink = RecordingSink()
        val controller = controller(sink = sink, targetLineCount = 2)

        assertTrue(controller.onAcceptedScan(locationScan("A-04")).accepted)
        assertEquals(BlindCountStep.SCAN_ITEM, controller.session().step)
        assertTrue(controller.onAcceptedScan(itemScan()).accepted)
        assertTrue(controller.enterQuantity(5).accepted)
        assertEquals(BlindCountStep.CONFIRM_ITEM, controller.session().step)

        val result = controller.confirmItem()

        assertTrue(result.accepted)
        assertNotNull(result.durableEvent)
        assertEquals(BlindCountStep.SCAN_ITEM, result.session.step)
        assertEquals(1, result.session.confirmedLineCount)
        assertEquals(1, sink.lineAttempts.size)
        assertTrue(result.durableEvent!!.canonicalPayload.contains("\"attempt_id\":\"$ATTEMPT_ID\""))
        assertTrue(result.durableEvent!!.canonicalPayload.contains("\"lease_id\":\"$LEASE_ID\""))
    }

    @Test
    fun `queue failure preserves confirm state and reuses exact event identity`() = runBlocking {
        val sink = RecordingSink(retryableLineFailuresRemaining = 1)
        val controller = controller(
            sink = sink,
            eventId = "11111111-1111-4111-8111-111111111111",
            occurredAt = "2026-08-18T15:00:00Z",
        )
        controller.onAcceptedScan(locationScan("A-04"))
        controller.onAcceptedScan(itemScan())
        controller.enterQuantity(5)

        val first = controller.confirmItem()
        assertEquals(BlindCountControllerCode.PERSIST_RETRY, first.code)
        assertEquals(BlindCountStep.CONFIRM_ITEM, controller.session().step)
        assertEquals(0, controller.session().confirmedLineCount)

        val second = controller.confirmItem()
        assertTrue(second.accepted)
        assertEquals(1, second.session.confirmedLineCount)
        assertEquals(2, sink.lineAttempts.size)
        assertEquals(sink.lineAttempts[0], sink.lineAttempts[1])
    }

    @Test
    fun `retryable count identity created before lease expiry survives a later retry`() = runBlocking {
        val sink = RecordingSink(retryableLineFailuresRemaining = 1)
        var currentOccurredAt = "2026-08-18T15:14:59Z"
        val controller = BlindCountTerminalController(
            target = BlindCountTarget(
                missionId = "mission-1",
                locationTokenHash = com.eay.mobile.core.BlindCountLocationToken.hash("A-04"),
            ),
            eventContext = context(),
            leaseValidUntil = LEASE_VALID_UNTIL,
            eventSink = sink,
            eventIdFactory = { "11111111-1111-4111-8111-111111111111" },
            occurredAtFactory = { currentOccurredAt },
        )
        controller.onAcceptedScan(locationScan("A-04"))
        controller.onAcceptedScan(itemScan())
        controller.enterQuantity(5)

        val first = controller.confirmItem()
        assertEquals(BlindCountControllerCode.PERSIST_RETRY, first.code)
        currentOccurredAt = "2026-08-18T15:16:00Z"

        val second = controller.confirmItem()
        assertTrue(second.accepted)
        assertEquals(2, sink.lineAttempts.size)
        assertEquals(sink.lineAttempts[0], sink.lineAttempts[1])
        assertEquals("2026-08-18T15:14:59Z", sink.lineAttempts[1].second)
    }

    @Test
    fun `event exactly at lease expiry is still eligible for historical attestation`() = runBlocking {
        val sink = RecordingSink()
        val controller = controller(
            sink = sink,
            occurredAt = LEASE_VALID_UNTIL,
        )
        controller.onAcceptedScan(locationScan("A-04"))
        controller.onAcceptedScan(itemScan())
        controller.enterQuantity(5)

        assertTrue(controller.confirmItem().accepted)
        assertEquals(1, sink.lineAttempts.size)
    }

    @Test
    fun `expired lease blocks count before durable queue write`() = runBlocking {
        val sink = RecordingSink()
        val controller = controller(
            sink = sink,
            occurredAt = "2026-08-18T15:16:00Z",
        )
        controller.onAcceptedScan(locationScan("A-04"))
        controller.onAcceptedScan(itemScan())
        controller.enterQuantity(5)

        val result = controller.confirmItem()

        assertEquals(BlindCountControllerCode.DENY_LEASE_EXPIRED, result.code)
        assertEquals(BlindCountStep.CONFIRM_ITEM, result.session.step)
        assertTrue(sink.lineAttempts.isEmpty())
    }

    @Test
    fun `zero line location completion fails closed before queue insert`() = runBlocking {
        val sink = RecordingSink()
        val controller = controller(
            sink = sink,
            eventId = "33333333-3333-4333-8333-333333333333",
            occurredAt = "2026-08-18T15:05:00Z",
        )
        controller.onAcceptedScan(locationScan("A-04"))

        val result = controller.completeLocation()

        assertEquals(BlindCountControllerCode.DENY_FLOW, result.code)
        assertEquals(com.eay.mobile.core.BlindCountCode.DENY_TARGET, result.flowCode)
        assertEquals(BlindCountStep.SCAN_ITEM, result.session.step)
        assertTrue(sink.completionAttempts.isEmpty())
    }

    @Test
    fun `retryable completion identity created before lease expiry survives a later retry`() = runBlocking {
        val sink = RecordingSink(retryableCompletionFailuresRemaining = 1)
        var currentOccurredAt = "2026-08-18T15:14:59Z"
        val controller = BlindCountTerminalController(
            target = BlindCountTarget(
                missionId = "mission-1",
                locationTokenHash = com.eay.mobile.core.BlindCountLocationToken.hash("A-04"),
            ),
            eventContext = context(),
            leaseValidUntil = LEASE_VALID_UNTIL,
            eventSink = sink,
            eventIdFactory = { "33333333-3333-4333-8333-333333333333" },
            occurredAtFactory = { currentOccurredAt },
        )
        controller.onAcceptedScan(locationScan("A-04"))
        controller.onAcceptedScan(itemScan())
        controller.enterQuantity(5)
        assertTrue(controller.confirmItem().accepted)

        val first = controller.completeLocation()
        assertEquals(BlindCountControllerCode.PERSIST_RETRY, first.code)
        currentOccurredAt = "2026-08-18T15:16:00Z"

        val second = controller.completeLocation()
        assertTrue(second.accepted)
        assertEquals(2, sink.completionAttempts.size)
        assertEquals(sink.completionAttempts[0], sink.completionAttempts[1])
        assertEquals("2026-08-18T15:14:59Z", sink.completionAttempts[1].second)
    }

    @Test
    fun `expired lease blocks location completion before durable queue write`() = runBlocking {
        val sink = RecordingSink()
        val occurredAt = ArrayDeque(
            listOf("2026-08-18T15:05:00Z", "2026-08-18T15:16:00Z"),
        )
        val controller = BlindCountTerminalController(
            target = BlindCountTarget(
                missionId = "mission-1",
                locationTokenHash = com.eay.mobile.core.BlindCountLocationToken.hash("A-04"),
            ),
            eventContext = context(),
            leaseValidUntil = LEASE_VALID_UNTIL,
            eventSink = sink,
            occurredAtFactory = { occurredAt.removeFirst() },
        )
        controller.onAcceptedScan(locationScan("A-04"))
        controller.onAcceptedScan(itemScan())
        controller.enterQuantity(5)
        assertTrue(controller.confirmItem().accepted)

        val result = controller.completeLocation()

        assertEquals(BlindCountControllerCode.DENY_LEASE_EXPIRED, result.code)
        assertEquals(BlindCountStep.SCAN_ITEM, result.session.step)
        assertTrue(sink.completionAttempts.isEmpty())
    }

    @Test
    fun `completion carries exact confirmed line count`() = runBlocking {
        val sink = RecordingSink()
        val controller = controller(sink = sink)
        controller.onAcceptedScan(locationScan("A-04"))
        controller.onAcceptedScan(itemScan())
        controller.enterQuantity(5)
        controller.confirmItem()

        val completion = controller.completeLocation()

        assertTrue(completion.accepted)
        assertEquals(1, sink.completionAttempts.single().third)
        assertTrue(completion.durableEvent!!.canonicalPayload.contains("\"confirmed_line_count\":1"))
    }

    @Test
    fun `completion queue failure preserves state and exact identity`() = runBlocking {
        val sink = RecordingSink(retryableCompletionFailuresRemaining = 1)
        val controller = controller(
            sink = sink,
            eventId = "33333333-3333-4333-8333-333333333333",
            occurredAt = "2026-08-18T15:05:00Z",
        )
        controller.onAcceptedScan(locationScan("A-04"))
        controller.onAcceptedScan(itemScan())
        controller.enterQuantity(5)
        assertTrue(controller.confirmItem().accepted)

        val first = controller.completeLocation()
        assertEquals(BlindCountControllerCode.PERSIST_RETRY, first.code)
        assertEquals(BlindCountStep.SCAN_ITEM, controller.session().step)

        val second = controller.completeLocation()
        assertTrue(second.accepted)
        assertEquals(BlindCountStep.COMPLETE, second.session.step)
        assertEquals(2, sink.completionAttempts.size)
        assertEquals(sink.completionAttempts[0], sink.completionAttempts[1])
    }

    @Test
    fun `contract violation is not mislabeled as retryable persistence`() {
        val sink = RecordingSink(contractFailure = true)
        val controller = controller(sink = sink)
        controller.onAcceptedScan(locationScan("A-04"))
        controller.onAcceptedScan(itemScan())
        controller.enterQuantity(5)

        assertThrows(IllegalArgumentException::class.java) {
            runBlocking { controller.confirmItem() }
        }
        assertEquals(BlindCountStep.CONFIRM_ITEM, controller.session().step)
        assertEquals(0, controller.session().confirmedLineCount)
    }

    @Test
    fun `completion contract violation is not retried`() {
        val completionSink = RecordingSink(completionContractFailure = true)
        val completionController = controller(sink = completionSink)
        completionController.onAcceptedScan(locationScan("A-04"))
        completionController.onAcceptedScan(itemScan())
        completionController.enterQuantity(5)
        runBlocking { completionController.confirmItem() }

        assertThrows(IllegalArgumentException::class.java) {
            runBlocking { completionController.completeLocation() }
        }
        assertEquals(BlindCountStep.SCAN_ITEM, completionController.session().step)
    }

    @Test
    fun `location scan must bind both blind target and event context`() {
        val sink = RecordingSink()
        val controller = BlindCountTerminalController(
            target = BlindCountTarget(
                missionId = "mission-1",
                locationTokenHash = com.eay.mobile.core.BlindCountLocationToken.hash("A-04"),
            ),
            eventContext = context(missionId = "mission-1", locationId = "B-05"),
            leaseValidUntil = LEASE_VALID_UNTIL,
            eventSink = sink,
        )

        val result = controller.onAcceptedScan(locationScan("A-04"))

        assertEquals(BlindCountControllerCode.DENY_LOCATION_CONTEXT, result.code)
        assertEquals(BlindCountStep.SCAN_LOCATION, controller.session().step)
    }

    @Test
    fun `controller accepts location case and surrounding whitespace after scanner admission`() {
        val sink = RecordingSink()
        val controller = controller(sink = sink)

        val result = controller.onAcceptedScan(locationScan(" a-04 "))

        assertTrue(result.accepted)
        assertEquals(BlindCountStep.SCAN_ITEM, result.session.step)
    }

    @Test
    fun `controller refuses target and event context from different missions`() {
        assertThrows(IllegalArgumentException::class.java) {
            BlindCountTerminalController(
                target = BlindCountTarget(
                    missionId = "mission-1",
                    locationTokenHash = com.eay.mobile.core.BlindCountLocationToken.hash("A-04"),
                ),
                eventContext = context(missionId = "mission-2"),
                leaseValidUntil = LEASE_VALID_UNTIL,
                eventSink = RecordingSink(),
            )
        }
    }

    private fun controller(
        sink: RecordingSink,
        targetLineCount: Int? = null,
        eventId: String = "11111111-1111-4111-8111-111111111111",
        occurredAt: String = "2026-08-18T15:00:00Z",
    ) = BlindCountTerminalController(
        target = BlindCountTarget(
            missionId = "mission-1",
            locationTokenHash = com.eay.mobile.core.BlindCountLocationToken.hash("A-04"),
            targetLineCount = targetLineCount,
        ),
        eventContext = context(),
        leaseValidUntil = LEASE_VALID_UNTIL,
        eventSink = sink,
        eventIdFactory = { eventId },
        occurredAtFactory = { occurredAt },
    )

    private fun context(
        missionId: String = "mission-1",
        locationId: String = "A-04",
    ) = InventoryCountEventContext(
        missionId = missionId,
        documentId = DOCUMENT_ID,
        activeShiftId = "SHIFT-20260818-001",
        attemptId = ATTEMPT_ID,
        leaseId = LEASE_ID,
        locationId = locationId,
    )

    private fun locationScan(value: String) = AcceptedScan(
        sourceEventId = "location-scan-1",
        source = ScannerSource.HARDWARE_DATAWEDGE,
        symbology = BarcodeSymbology.CODE128,
        value = value,
        payloadHash = TerminalEventCanonical.hash(value),
        capturedAtEpochMs = 1_500L,
    )

    private fun itemScan() = AcceptedScan(
        sourceEventId = "item-scan-1",
        source = ScannerSource.HARDWARE_DATAWEDGE,
        symbology = BarcodeSymbology.EAN13,
        value = "8690000000001",
        payloadHash = TerminalEventCanonical.hash("8690000000001"),
        capturedAtEpochMs = 1_600L,
    )

    private class RecordingSink(
        var retryableLineFailuresRemaining: Int = 0,
        var retryableCompletionFailuresRemaining: Int = 0,
        val contractFailure: Boolean = false,
        val completionContractFailure: Boolean = false,
    ) : BlindCountEventSink {
        val lineAttempts = mutableListOf<Pair<String, String>>()
        val completionAttempts = mutableListOf<Triple<String, String, Int>>()

        override suspend fun enqueueConfirmedCount(
            context: InventoryCountEventContext,
            acceptedScan: AcceptedScan,
            evidence: com.eay.mobile.core.BlindCountLineEvidence,
            eventId: String,
            occurredAt: String,
        ): OfflineEvent {
            lineAttempts += eventId to occurredAt
            if (contractFailure) {
                throw IllegalArgumentException("simulated immutable contract violation")
            }
            if (retryableLineFailuresRemaining > 0) {
                retryableLineFailuresRemaining -= 1
                throw RetryableCountPersistenceException(
                    IllegalStateException("simulated durable queue failure"),
                )
            }
            return InventoryCountEventFactory.create(
                context = context,
                acceptedScan = acceptedScan,
                evidence = evidence,
                deviceSequence = 1,
                eventId = eventId,
                occurredAt = occurredAt,
                authBindingId = "binding-1",
            )
        }

        override suspend fun enqueueLocationCompletion(
            context: InventoryCountEventContext,
            confirmedLineCount: Int,
            eventId: String,
            occurredAt: String,
        ): OfflineEvent {
            completionAttempts += Triple(eventId, occurredAt, confirmedLineCount)
            if (completionContractFailure) {
                throw IllegalArgumentException("simulated immutable completion violation")
            }
            if (retryableCompletionFailuresRemaining > 0) {
                retryableCompletionFailuresRemaining -= 1
                throw RetryableCountPersistenceException(
                    IllegalStateException("simulated durable completion failure"),
                )
            }
            return InventoryLocationCompletionEventFactory.create(
                context = context,
                confirmedLineCount = confirmedLineCount,
                deviceSequence = 2,
                eventId = eventId,
                occurredAt = occurredAt,
                authBindingId = "binding-1",
            )
        }
    }

    companion object {
        private const val DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
        private const val ATTEMPT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        private const val LEASE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        private const val LEASE_VALID_UNTIL = "2026-08-18T15:15:00Z"
    }
}
