package com.eay.inventory

import com.eay.mobile.core.SyncServerOutcome
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InventorySyncChaosContractTest {
    @Test
    fun `accepted commit and exact replay are the only successful terminal outcomes`() {
        assertEquals(
            SyncServerOutcome.COMMITTED,
            InventorySyncClassifier.classify(200, accepted = true, idempotentReplay = false).outcome,
        )
        assertEquals(
            SyncServerOutcome.EXACT_REPLAY,
            InventorySyncClassifier.classify(200, accepted = true, idempotentReplay = true).outcome,
        )
        assertEquals(
            SyncServerOutcome.PERMANENT_REJECTED,
            InventorySyncClassifier.classify(200, accepted = false, idempotentReplay = false).outcome,
        )
    }

    @Test
    fun `authentication policy device and business failures remain distinct`() {
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
            SyncServerOutcome.DEVICE_REJECTED,
            InventorySyncClassifier.classify(410, null, null).outcome,
        )
    }

    @Test
    fun `network pressure and server outage stay retryable while malformed requests do not`() {
        listOf(408, 429, 500, 503).forEach { code ->
            assertEquals(
                SyncServerOutcome.RETRYABLE_FAILURE,
                InventorySyncClassifier.classify(code, null, null).outcome,
            )
        }
        listOf(400, 404, 422).forEach { code ->
            assertEquals(
                SyncServerOutcome.PERMANENT_REJECTED,
                InventorySyncClassifier.classify(code, null, null).outcome,
            )
        }
    }

    @Test
    fun `server ack cannot substitute shift attempt or lease`() {
        val payload =
            "{\"active_shift_id\":\"SHIFT-1\"," +
                "\"attempt_id\":\"$ATTEMPT_ID\"," +
                "\"lease_id\":\"$LEASE_ID\"}"

        assertTrue(
            InventorySyncContract.responseMatchesSignedMission(
                payload,
                "SHIFT-1",
                ATTEMPT_ID,
                LEASE_ID,
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedMission(
                payload,
                "SHIFT-2",
                ATTEMPT_ID,
                LEASE_ID,
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedMission(
                payload,
                "SHIFT-1",
                OTHER_ATTEMPT_ID,
                LEASE_ID,
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedMission(
                payload,
                "SHIFT-1",
                ATTEMPT_ID,
                OTHER_LEASE_ID,
            ),
        )
    }

    companion object {
        private const val ATTEMPT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        private const val LEASE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        private const val OTHER_ATTEMPT_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        private const val OTHER_LEASE_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    }
}
