package com.eay.inventory

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InventorySyncContractTest {
    private val canonical =
        "{\"active_shift_id\":\"SHIFT-20260818-001\",\"barcode\":\"8690000000001\"}"

    @Test
    fun `matching server shift attestation may ACK`() {
        assertTrue(
            InventorySyncContract.responseMatchesSignedShift(
                canonical,
                "SHIFT-20260818-001",
            ),
        )
    }

    @Test
    fun `missing or different server shift attestation fails closed`() {
        assertFalse(InventorySyncContract.responseMatchesSignedShift(canonical, null))
        assertFalse(InventorySyncContract.responseMatchesSignedShift(canonical, ""))
        assertFalse(
            InventorySyncContract.responseMatchesSignedShift(
                canonical,
                "SHIFT-OTHER",
            ),
        )
    }

    @Test
    fun `malformed durable payload cannot be ACKed by server response`() {
        assertFalse(
            InventorySyncContract.responseMatchesSignedShift(
                "{\"barcode\":\"8690000000001\"}",
                "SHIFT-20260818-001",
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedShift(
                "not-json",
                "SHIFT-20260818-001",
            ),
        )
    }
}
