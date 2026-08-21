package com.eay.inventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.MessageDigest
import java.math.BigDecimal

class OfflineContractTest {
    @Test fun eventIdentitySurvivesRetries() {
        val event = OfflineEvent("e-1", 41, "{}", "a".repeat(64), authBindingId = "session-a", attempts = 2)
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
        val event = OfflineEvent("e-2", 42, canonical, hash, authBindingId = "session-a")
        assertTrue(QueueIntegrity.valid(event, "session-a"))
        assertTrue(!QueueIntegrity.valid(event.copy(canonicalPayload = canonical + "x"), "session-a"))
    }

    @Test fun interactiveSessionChangeBlocksReplay() {
        val canonical = "{\"event_id\":\"e-3\"}"
        val hash = TerminalEventCanonical.hash(canonical)
        val event = OfflineEvent("e-3", 43, canonical, hash, authBindingId = "session-a")
        assertTrue(QueueIntegrity.valid(event, "session-a"))
        assertTrue(!QueueIntegrity.valid(event, "session-b"))
    }

    @Test fun migratedOrMalformedBindingFailsClosed() {
        val canonical = "{\"event_id\":\"e-4\"}"
        val hash = TerminalEventCanonical.hash(canonical)
        assertTrue(!QueueIntegrity.valid(OfflineEvent("e-4", 44, canonical, hash), "session-a"))
        assertTrue(!QueueIntegrity.valid(OfflineEvent("e-4", 44, canonical, hash, authBindingId = "session-a"), ""))
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
            state = "ACKED",
            attempts = 3,
        )
        val retry = OfflineEvent("e-5", 45, canonical, hash, authBindingId = "session-a")
        assertTrue(OfflineEventIdentity.sameImmutableIdentity(durable, retry))
    }

    @Test fun duplicateEventIdWithDifferentImmutableIdentityFailsClosed() {
        val canonical = "{\"event_id\":\"e-6\"}"
        val hash = TerminalEventCanonical.hash(canonical)
        val durable = OfflineEvent("e-6", 46, canonical, hash, authBindingId = "session-a")

        assertTrue(!OfflineEventIdentity.sameImmutableIdentity(
            durable,
            durable.copy(deviceSequence = 47),
        ))
        assertTrue(!OfflineEventIdentity.sameImmutableIdentity(
            durable,
            durable.copy(canonicalPayload = canonical + " "),
        ))
        assertTrue(!OfflineEventIdentity.sameImmutableIdentity(
            durable,
            durable.copy(payloadHash = "0".repeat(64)),
        ))
        assertTrue(!OfflineEventIdentity.sameImmutableIdentity(
            durable,
            durable.copy(authBindingId = "session-b"),
        ))
    }

    @Test fun canonicalEventIsStableAndQuantityNormalized() {
        val body = TerminalEventCanonical.body(TerminalEventInput(
            " 869 ", 7, "550E8400-E29B-41D4-A716-446655440000",
            "550E8400-E29B-41D4-A716-446655440001", "a01", "2026-08-13T20:00:00Z",
            BigDecimal("2.000"), "EAN13",
        ))
        assertTrue(body.contains("\"quantity\":\"2\""))
        assertEquals(64, TerminalEventCanonical.hash(body).length)
    }
}
