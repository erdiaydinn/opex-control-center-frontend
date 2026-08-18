package com.eay.inventory

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InventorySyncContractTest {
    private val canonical =
        "{\"active_shift_id\":\"SHIFT-20260818-001\"," +
            "\"attempt_id\":\"$ATTEMPT_ID\",\"lease_id\":\"$LEASE_ID\"," +
            "\"barcode\":\"8690000000001\"}"

    @Test
    fun `matching server mission attestation may ACK`() {
        assertTrue(
            InventorySyncContract.responseMatchesSignedMission(
                canonical,
                "SHIFT-20260818-001",
                ATTEMPT_ID,
                LEASE_ID,
            ),
        )
    }

    @Test
    fun `missing or different mission attestation fails closed`() {
        assertFalse(
            InventorySyncContract.responseMatchesSignedMission(
                canonical,
                null,
                ATTEMPT_ID,
                LEASE_ID,
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedMission(
                canonical,
                "SHIFT-20260818-001",
                "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                LEASE_ID,
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedMission(
                canonical,
                "SHIFT-20260818-001",
                ATTEMPT_ID,
                "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            ),
        )
    }

    @Test
    fun `malformed durable payload cannot be ACKed by server response`() {
        assertFalse(
            InventorySyncContract.responseMatchesSignedMission(
                "{\"active_shift_id\":\"SHIFT-20260818-001\"}",
                "SHIFT-20260818-001",
                ATTEMPT_ID,
                LEASE_ID,
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedMission(
                "not-json",
                "SHIFT-20260818-001",
                ATTEMPT_ID,
                LEASE_ID,
            ),
        )
    }

    companion object {
        private const val ATTEMPT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        private const val LEASE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    }
}
