package com.eay.inventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.MessageDigest
import java.math.BigDecimal

class OfflineContractTest {
    @Test fun eventIdentitySurvivesRetries() {
        val event = OfflineEvent("e-1", 41, "{}", "a".repeat(64), attempts = 2)
        assertEquals("e-1", event.copy(attempts = 3).eventId)
        assertEquals(41, event.copy(attempts = 3).deviceSequence)
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
        assertTrue(QueueIntegrity.valid(OfflineEvent("e-2", 42, canonical, hash)))
        assertTrue(!QueueIntegrity.valid(OfflineEvent("e-2", 42, canonical + "x", hash)))
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
