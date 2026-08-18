package com.eay.inventory

import com.eay.mobile.core.AcceptedScan
import com.eay.mobile.core.BarcodeSymbology
import com.eay.mobile.core.BlindCountLineEvidence
import com.eay.mobile.core.ScannerSource
import com.eay.mobile.core.SyncQuarantineReason
import com.eay.mobile.core.SyncServerOutcome
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal
import java.security.MessageDigest

class OfflineContractTest {
    @Test fun eventIdentitySurvivesRetries() {
        val event = OfflineEvent(
            "e-1",
            41,
            "{}",
            "a".repeat(64),
            authBindingId = "session-a",
            attempts = 2,
        )
        assertEquals("e-1", event.copy(attempts = 3).eventId)
        assertEquals(41, event.copy(attempts = 3).deviceSequence)
        assertEquals("session-a", event.copy(attempts = 3).authBindingId)
    }

    @Test fun releaseUsesTwoDistinctPins() {
        assertTrue(BuildConfig.TLS_PIN_PRIMARY.startsWith("sha256/"))
        assertTrue(BuildConfig.TLS_PIN_BACKUP.startsWith("sha256/"))
        assertTrue(BuildConfig.TLS_PIN_PRIMARY != BuildConfig.TLS_PIN_BACKUP)
    }

    @Test fun queueCorruptionFailsClosed() {
        val canonical = "{\"barcode\":\"869\"}"
        val hash = MessageDigest.getInstance("SHA-256").digest(canonical.toByteArray())
            .joinToString("") { "%02x".format(it) }
        val event = OfflineEvent(
            "e-2",
            42,
            canonical,
            hash,
            authBindingId = "session-a",
        )
        assertTrue(QueueIntegrity.valid(event, "session-a"))
        assertEquals(
            SyncQuarantineReason.CORRUPT_EVENT,
            QueueIntegrity.failureReason(
                event.copy(canonicalPayload = canonical + "x"),
                "session-a",
            ),
        )
    }

    @Test fun interactiveSessionChangeBlocksReplay() {
        val canonical = "{\"event_id\":\"e-3\"}"
        val hash = TerminalEventCanonical.hash(canonical)
        val event = OfflineEvent(
            "e-3",
            43,
            canonical,
            hash,
            authBindingId = "session-a",
        )
        assertEquals(
            SyncQuarantineReason.AUTH_BINDING_CHANGED,
            QueueIntegrity.failureReason(event, "session-b"),
        )
    }

    @Test fun migratedOrMalformedBindingFailsClosed() {
        val canonical = "{\"event_id\":\"e-4\"}"
        val hash = TerminalEventCanonical.hash(canonical)
        assertTrue(!QueueIntegrity.valid(OfflineEvent("e-4", 44, canonical, hash), "session-a"))
        assertTrue(
            !QueueIntegrity.valid(
                OfflineEvent(
                    "e-4",
                    44,
                    canonical,
                    hash,
                    authBindingId = "session-a",
                ),
                "",
            ),
        )
    }

    @Test fun exactDuplicateIdentityIsIdempotentAcrossQueueStateChanges() {
        val canonical = "{\"event_id\":\"e-5\"}"
        val hash = TerminalEventCanonical.hash(canonical)
        val durable = OfflineEvent(
            "e-5",
            45,
            canonical,
            hash,
            authBindingId = "session-a",
            state = "QUARANTINED",
            attempts = 3,
            quarantineReason = SyncQuarantineReason.BUSINESS_CONFLICT.name,
        )
        val retry = OfflineEvent("e-5", 45, canonical, hash, authBindingId = "session-a")
        assertTrue(OfflineEventIdentity.sameImmutableIdentity(durable, retry))
    }

    @Test fun duplicateEventIdWithDifferentImmutableIdentityFailsClosed() {
        val canonical = "{\"event_id\":\"e-6\"}"
        val hash = TerminalEventCanonical.hash(canonical)
        val durable = OfflineEvent("e-6", 46, canonical, hash, authBindingId = "session-a")

        assertTrue(
            !OfflineEventIdentity.sameImmutableIdentity(
                durable,
                durable.copy(deviceSequence = 47),
            ),
        )
        assertTrue(
            !OfflineEventIdentity.sameImmutableIdentity(
                durable,
                durable.copy(canonicalPayload = canonical + " "),
            ),
        )
        assertTrue(
            !OfflineEventIdentity.sameImmutableIdentity(
                durable,
                durable.copy(payloadHash = "0".repeat(64)),
            ),
        )
        assertTrue(
            !OfflineEventIdentity.sameImmutableIdentity(
                durable,
                durable.copy(authBindingId = "session-b"),
            ),
        )
    }

    @Test fun canonicalEventIsStableAndQuantityNormalized() {
        val body = TerminalEventCanonical.body(
            TerminalEventInput(
                activeShiftId = "SHIFT-20260813-001",
                attemptId = ATTEMPT_ID,
                barcode = " 869 ",
                deviceSequence = 7,
                documentId = "550E8400-E29B-41D4-A716-446655440000",
                eventId = "550E8400-E29B-41D4-A716-446655440001",
                leaseId = LEASE_ID,
                locationId = "a01",
                occurredAt = "2026-08-13T20:00:00Z",
                quantity = BigDecimal("2.000"),
                symbology = "EAN13",
            ),
        )
        assertTrue(body.contains("\"quantity\":\"2\""))
        assertTrue(body.contains("\"active_shift_id\":\"SHIFT-20260813-001\""))
        assertTrue(body.contains("\"attempt_id\":\"$ATTEMPT_ID\""))
        assertTrue(body.contains("\"lease_id\":\"$LEASE_ID\""))
        assertEquals(64, TerminalEventCanonical.hash(body).length)
    }

    @Test fun canonicalEventMatchesBackendGoldenVectorByteForByte() {
        val body = TerminalEventCanonical.body(
            TerminalEventInput(
                activeShiftId = "SHIFT-20260818-001",
                attemptId = ATTEMPT_ID,
                barcode = " 8690000000001 ",
                deviceSequence = 7,
                documentId = DOCUMENT_ID,
                eventId = "11111111-1111-4111-8111-111111111111",
                leaseId = LEASE_ID,
                locationId = " a-04 ",
                occurredAt = "2026-08-18T15:00:00Z",
                quantity = BigDecimal("5.000"),
                symbology = " EAN13 ",
            ),
        )
        val expectedBody =
            "{\"active_shift_id\":\"SHIFT-20260818-001\",\"attempt_id\":\"$ATTEMPT_ID\"," +
                "\"barcode\":\"8690000000001\",\"device_sequence\":7," +
                "\"document_id\":\"$DOCUMENT_ID\"," +
                "\"event_id\":\"11111111-1111-4111-8111-111111111111\"," +
                "\"lease_id\":\"$LEASE_ID\",\"location_id\":\"A-04\"," +
                "\"occurred_at\":\"2026-08-18T15:00:00Z\"," +
                "\"quantity\":\"5\",\"symbology\":\"EAN13\"}"
        assertEquals(expectedBody, body)
        assertEquals(
            "7ea0134fc401ec93770b492ecd423dd0644df1f79d153c4b6f58ad2ed62489e5",
            TerminalEventCanonical.hash(body),
        )
    }

    @Test fun confirmedBlindCountLineCreatesImmutableQueueEvent() {
        val acceptedScan = AcceptedScan(
            sourceEventId = "scan-1",
            source = ScannerSource.HARDWARE_DATAWEDGE,
            symbology = BarcodeSymbology.EAN13,
            value = "8690000000001",
            payloadHash = "c".repeat(64),
            capturedAtEpochMs = 1_500L,
        )
        val evidence = BlindCountLineEvidence(
            missionId = "mission-1",
            itemPayloadHash = acceptedScan.payloadHash,
            quantity = 5,
        )
        val event = InventoryCountEventFactory.create(
            context = context(),
            acceptedScan = acceptedScan,
            evidence = evidence,
            deviceSequence = 7,
            eventId = "11111111-1111-4111-8111-111111111111",
            occurredAt = "2026-08-18T15:00:00Z",
            authBindingId = "session-a",
        )
        assertEquals(
            "7ea0134fc401ec93770b492ecd423dd0644df1f79d153c4b6f58ad2ed62489e5",
            event.payloadHash,
        )
        assertTrue(QueueIntegrity.valid(event, "session-a"))
        assertEquals(7, event.deviceSequence)
    }

    @Test fun confirmedBlindCountLineRejectsScanEvidenceSubstitution() {
        val acceptedScan = AcceptedScan(
            sourceEventId = "scan-2",
            source = ScannerSource.HARDWARE_DATAWEDGE,
            symbology = BarcodeSymbology.EAN13,
            value = "8690000000001",
            payloadHash = "c".repeat(64),
            capturedAtEpochMs = 1_500L,
        )
        assertThrows(IllegalArgumentException::class.java) {
            InventoryCountEventFactory.create(
                context = context(),
                acceptedScan = acceptedScan,
                evidence = BlindCountLineEvidence(
                    missionId = "mission-1",
                    itemPayloadHash = "d".repeat(64),
                    quantity = 5,
                ),
                deviceSequence = 7,
                eventId = "11111111-1111-4111-8111-111111111111",
                occurredAt = "2026-08-18T15:00:00Z",
                authBindingId = "session-a",
            )
        }
    }

    @Test fun serverClassificationSeparatesRetryConflictAndPolicy() {
        assertEquals(
            SyncServerOutcome.EXACT_REPLAY,
            InventorySyncClassifier.classify(200, true, true).outcome,
        )
        assertEquals(
            SyncServerOutcome.AUTH_REJECTED,
            InventorySyncClassifier.classify(401, null, null).outcome,
        )
        assertEquals(
            SyncServerOutcome.POLICY_REJECTED,
            InventorySyncClassifier.classify(403, null, null).outcome,
        )
        assertEquals(
            SyncServerOutcome.BUSINESS_CONFLICT,
            InventorySyncClassifier.classify(409, null, null).outcome,
        )
        assertEquals(
            SyncServerOutcome.RETRYABLE_FAILURE,
            InventorySyncClassifier.classify(503, null, null).outcome,
        )
        assertEquals(
            SyncServerOutcome.PERMANENT_REJECTED,
            InventorySyncClassifier.classify(422, null, null).outcome,
        )
    }

    private fun context() = InventoryCountEventContext(
        missionId = "mission-1",
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
