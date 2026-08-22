package com.eay.inventory

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class InventoryTerminalMissionClaimContractTest {
    @Test
    fun `claim payload matches backend canonical hash`() {
        val body = InventoryMissionClaimContract.canonicalBody(DOCUMENT_ID, " a-04 ")
        assertEquals(
            "{\"document_id\":\"$DOCUMENT_ID\",\"location_id\":\"A-04\"}",
            body,
        )
        assertEquals(
            "48067d4daccfa2d02a456f39f39a95ac4a627fe13aa93ea2655a34b903ff071d",
            InventoryMissionClaimContract.hash(body),
        )
    }

    @Test
    fun `server claim response becomes exact owned task`() {
        val source = availableTask()
        val owned = InventoryMissionClaimContract.bindResponse(
            source,
            JSONObject()
                .put("mission_id", source.missionId)
                .put("document_id", DOCUMENT_ID)
                .put("location_id", "A-04")
                .put("attempt_id", ATTEMPT_ID)
                .put("lease_id", LEASE_ID)
                .put("active_shift_id", source.activeShiftId)
                .put("lease_valid_until", "2026-08-18T15:15:00Z")
                .put("claim_status", "OWNED"),
        )

        assertEquals(InventoryMissionClaimStatus.OWNED, owned.claimStatus)
        assertEquals(ATTEMPT_ID, owned.attemptId)
        assertEquals(LEASE_ID, owned.leaseId)
        assertEquals(ATTEMPT_ID, owned.eventContext().attemptId)
        assertEquals(LEASE_ID, owned.eventContext().leaseId)
    }

    @Test
    fun `claim response binding mismatch fails closed`() {
        val source = availableTask()
        assertThrows(IllegalArgumentException::class.java) {
            InventoryMissionClaimContract.bindResponse(
                source,
                JSONObject()
                    .put("mission_id", source.missionId)
                    .put("document_id", DOCUMENT_ID)
                    .put("location_id", "OTHER")
                    .put("attempt_id", ATTEMPT_ID)
                    .put("lease_id", LEASE_ID)
                    .put("active_shift_id", source.activeShiftId)
                    .put("lease_valid_until", "2026-08-18T15:15:00Z")
                    .put("claim_status", "OWNED"),
            )
        }
    }

    @Test
    fun `claim response from stale shift fails closed`() {
        val source = availableTask()
        assertThrows(IllegalArgumentException::class.java) {
            InventoryMissionClaimContract.bindResponse(
                source,
                JSONObject()
                    .put("mission_id", source.missionId)
                    .put("document_id", DOCUMENT_ID)
                    .put("location_id", source.locationId)
                    .put("attempt_id", ATTEMPT_ID)
                    .put("lease_id", LEASE_ID)
                    .put("active_shift_id", "SHIFT-STALE")
                    .put("lease_valid_until", "2026-08-18T15:15:00Z")
                    .put("claim_status", "OWNED"),
            )
        }
    }

    @Test
    fun `http claim classification distinguishes conflict from retry`() {
        assertEquals(
            InventoryMissionClaimCode.BUSINESS_CONFLICT,
            InventoryMissionClaimContract.classifyHttp(409),
        )
        assertEquals(
            InventoryMissionClaimCode.RETRYABLE,
            InventoryMissionClaimContract.classifyHttp(503),
        )
        assertEquals(
            InventoryMissionClaimCode.AUTH_REQUIRED,
            InventoryMissionClaimContract.classifyHttp(401),
        )
    }

    private fun availableTask() = InventoryTerminalCountTask(
        missionId = "inventory.count:mission-1",
        documentId = DOCUMENT_ID,
        activeShiftId = "SHIFT-20260818-001",
        warehouseId = "FULYA",
        locationId = "A-04",
        name = "Weekly cycle count",
        state = "COUNTING",
        revision = 2,
        locationCount = 12,
    )

    companion object {
        private const val DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
        private const val ATTEMPT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        private const val LEASE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    }
}
