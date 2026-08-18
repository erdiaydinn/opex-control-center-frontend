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
        assertEquals(1, sink.attempts.size)
    }

    @Test
    fun `queue failure preserves confirm state and reuses exact event identity`() = runBlocking {
        val sink = RecordingSink(retryableFailuresRemaining = 1)
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
        assertEquals(2, sink.attempts.size)
        assertEquals(sink.attempts[0], sink.attempts[1])
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
    fun `location scan must bind both blind target and event context`() {
        val sink = RecordingSink()
        val controller = BlindCountTerminalController(
            target = BlindCountTarget(
                missionId = "mission-1",
                locationTokenHash = com.eay.mobile.core.BlindCountLocationToken.hash("A-04"),
            ),
            eventContext = InventoryCountEventContext(
                missionId = "mission-1",
                documentId = "22222222-2222-4222-8222-222222222222",
                activeShiftId = "SHIFT-20260818-001",
                locationId = "B-05",
            ),
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
                eventContext = InventoryCountEventContext(
                    missionId = "mission-2",
                    documentId = "22222222-2222-4222-8222-222222222222",
                    activeShiftId = "SHIFT-20260818-001",
                    locationId = "A-04",
                ),
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
        eventContext = InventoryCountEventContext(
            missionId = "mission-1",
            documentId = "22222222-2222-4222-8222-222222222222",
            activeShiftId = "SHIFT-20260818-001",
            locationId = "A-04",
        ),
        eventSink = sink,
        eventIdFactory = { eventId },
        occurredAtFactory = { occurredAt },
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
        var retryableFailuresRemaining: Int = 0,
        val contractFailure: Boolean = false,
    ) : ConfirmedCountEventSink {
        val attempts = mutableListOf<Pair<String, String>>()

        override suspend fun enqueueConfirmedCount(
            context: InventoryCountEventContext,
            acceptedScan: AcceptedScan,
            evidence: com.eay.mobile.core.BlindCountLineEvidence,
            eventId: String,
            occurredAt: String,
        ): OfflineEvent {
            attempts += eventId to occurredAt
            if (contractFailure) {
                throw IllegalArgumentException("simulated immutable contract violation")
            }
            if (retryableFailuresRemaining > 0) {
                retryableFailuresRemaining -= 1
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
    }
}
