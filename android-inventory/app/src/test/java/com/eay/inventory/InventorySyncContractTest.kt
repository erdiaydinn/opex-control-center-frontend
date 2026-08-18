package com.eay.inventory

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InventorySyncContractTest {
    private val canonical =
        "{\"active_shift_id\":\"SHIFT-20260818-001\"," +
            "\"attempt_id\":\"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1\"," +
            "\"lease_id\":\"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1\"," +
            "\"barcode\":\"8690000000001\"}"

    @Test
    fun `matching server mission authority may ACK`() {
        assertTrue(
            InventorySyncContract.responseMatchesSignedAuthority(
                canonical,
                "SHIFT-20260818-001",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            ),
        )
    }

    @Test
    fun `missing or different server authority fails closed`() {
        assertFalse(
            InventorySyncContract.responseMatchesSignedAuthority(
                canonical,
                null,
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedAuthority(
                canonical,
                "SHIFT-OTHER",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedAuthority(
                canonical,
                "SHIFT-20260818-001",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedAuthority(
                canonical,
                "SHIFT-20260818-001",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2",
            ),
        )
    }

    @Test
    fun `malformed durable payload cannot be ACKed by server response`() {
        assertFalse(
            InventorySyncContract.responseMatchesSignedAuthority(
                "{\"barcode\":\"8690000000001\"}",
                "SHIFT-20260818-001",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            ),
        )
        assertFalse(
            InventorySyncContract.responseMatchesSignedAuthority(
                "not-json",
                "SHIFT-20260818-001",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            ),
        )
    }
}
