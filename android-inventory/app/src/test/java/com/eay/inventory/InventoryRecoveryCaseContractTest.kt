package com.eay.inventory

import com.eay.mobile.core.SyncQuarantineReason
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryRecoveryCaseContractTest {
    @Test
    fun `business quarantine becomes safe recovery request without raw count truth`() {
        val event = OfflineEvent(
            eventId = EVENT_ID,
            deviceSequence = 7,
            canonicalPayload = canonicalEvent(),
            payloadHash = "a".repeat(64),
            authBindingId = "auth-a",
            state = "QUARANTINED",
            quarantineReason = SyncQuarantineReason.BUSINESS_CONFLICT.name,
            lastServerCode = "COUNT_REVISION_CONFLICT",
        )
        val request = requireNotNull(InventoryRecoveryCaseContract.from(event))
        assertEquals(DOCUMENT_ID, request.documentId)
        assertEquals(EVENT_ID, request.eventId)
        assertEquals("A-04", request.locationId)
        assertEquals(SyncQuarantineReason.BUSINESS_CONFLICT.name, request.quarantineReason)
        assertEquals(
            "2cba02f00c8b3cf3af43da5abebc8b46939dc3c81e20c19b4e88163af10de8d4",
            InventoryRecoveryCaseContract.hash(request),
        )
        val body = InventoryRecoveryCaseContract.body(request)
        assertTrue(!body.contains("barcode"))
        assertTrue(!body.contains("quantity"))
        assertTrue(!body.contains("tenant"))
        assertTrue(!body.contains("employee"))
        assertTrue(!body.contains("device_id"))
    }

    @Test
    fun `security and device quarantine cannot enter supervisor business recovery`() {
        for (
            reason in listOf(
                SyncQuarantineReason.AUTH_BINDING_CHANGED,
                SyncQuarantineReason.TENANT_BINDING_CHANGED,
                SyncQuarantineReason.DEVICE_REVOKED,
                SyncQuarantineReason.CORRUPT_EVENT,
                SyncQuarantineReason.LEDGER_CHAIN_MISMATCH,
            )
        ) {
            assertNull(
                InventoryRecoveryCaseContract.from(
                    OfflineEvent(
                        eventId = EVENT_ID,
                        deviceSequence = 7,
                        canonicalPayload = canonicalEvent(),
                        payloadHash = "a".repeat(64),
                        authBindingId = "auth-a",
                        state = "QUARANTINED",
                        quarantineReason = reason.name,
                    ),
                ),
            )
        }
    }

    @Test
    fun `existing recovery case cannot be reopened from local queue`() {
        assertNull(
            InventoryRecoveryCaseContract.from(
                OfflineEvent(
                    eventId = EVENT_ID,
                    deviceSequence = 7,
                    canonicalPayload = canonicalEvent(),
                    payloadHash = "a".repeat(64),
                    authBindingId = "auth-a",
                    state = "QUARANTINED",
                    quarantineReason = SyncQuarantineReason.BUSINESS_CONFLICT.name,
                    recoveryCaseId = "33333333-3333-4333-8333-333333333333",
                    recoveryState = "REQUESTED",
                ),
            ),
        )
    }

    @Test
    fun `recovery response must bind exact event and evidence policy`() {
        val event = OfflineEvent(
            eventId = EVENT_ID,
            deviceSequence = 7,
            canonicalPayload = canonicalEvent(),
            payloadHash = "a".repeat(64),
            authBindingId = "auth-a",
            state = "QUARANTINED",
            quarantineReason = SyncQuarantineReason.BUSINESS_CONFLICT.name,
            lastServerCode = "COUNT_REVISION_CONFLICT",
        )
        val request = requireNotNull(InventoryRecoveryCaseContract.from(event))
        val response = JSONObject()
            .put("case_id", "33333333-3333-4333-8333-333333333333")
            .put("event_id", EVENT_ID)
            .put("document_id", DOCUMENT_ID)
            .put("location_id", "A-04")
            .put("payload_hash", "a".repeat(64))
            .put("evidence_policy", "PRESERVE_NO_CLIENT_PROMOTION")
        assertEquals(
            "33333333-3333-4333-8333-333333333333",
            InventoryRecoveryCaseContract.bindResponse(request, response),
        )
        assertThrows(IllegalArgumentException::class.java) {
            InventoryRecoveryCaseContract.bindResponse(
                request,
                JSONObject(response.toString()).put("payload_hash", "b".repeat(64)),
            )
        }
    }

    @Test
    fun `canonical payload event id substitution is rejected`() {
        val event = OfflineEvent(
            eventId = EVENT_ID,
            deviceSequence = 7,
            canonicalPayload = JSONObject(canonicalEvent())
                .put("event_id", "44444444-4444-4444-8444-444444444444")
                .toString(),
            payloadHash = "a".repeat(64),
            authBindingId = "auth-a",
            state = "QUARANTINED",
            quarantineReason = SyncQuarantineReason.BUSINESS_CONFLICT.name,
        )
        assertNull(InventoryRecoveryCaseContract.from(event))
    }

    private fun canonicalEvent(): String =
        "{\"active_shift_id\":\"SHIFT-1\",\"attempt_id\":\"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa\"," +
            "\"barcode\":\"8690000000001\",\"device_sequence\":7," +
            "\"document_id\":\"$DOCUMENT_ID\",\"event_id\":\"$EVENT_ID\"," +
            "\"lease_id\":\"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb\",\"location_id\":\"A-04\"," +
            "\"occurred_at\":\"2026-08-20T07:00:00Z\",\"quantity\":\"5\",\"symbology\":\"EAN13\"}"

    companion object {
        private const val DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
        private const val EVENT_ID = "11111111-1111-4111-8111-111111111111"
    }
}
