package com.eay.inventory

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.security.MessageDigest

class ServerFrozenSkuIdentityTest {
    private val documentId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    private val barcode = "8690000000001"
    private val payload = """{"document_id":"$documentId","barcode":"$barcode","quantity":"47"}"""

    @Test
    fun `known identity binds server snapshot to signed barcode without stock truth`() {
        val identityBody = """{"barcode":"$barcode","document_id":"$documentId","sku":"SKU-REAL-1","status":"KNOWN"}"""
        val response = JSONObject().put(
            "sku_identity",
            JSONObject(identityBody).put("snapshot_hash", sha256(identityBody)),
        )

        val identity = ServerFrozenSkuIdentity.verify(response, payload)!!

        assertEquals("SKU-REAL-1", identity.sku)
        assertEquals(ServerSkuIdentityStatus.KNOWN, identity.status)
        val publicShape = identity.toString().lowercase()
        listOf("quantity", "expected", "cost", "variance", "stock").forEach {
            assert(!publicShape.contains(it))
        }
    }

    @Test
    fun `substituted sku barcode document or proof fails closed`() {
        val body = """{"barcode":"$barcode","document_id":"$documentId","sku":"SKU-REAL-1","status":"KNOWN"}"""
        val response = JSONObject().put(
            "sku_identity",
            JSONObject(body).put("snapshot_hash", sha256(body)),
        )

        assertNull(ServerFrozenSkuIdentity.verify(response, payload.replace(barcode, "8690000000002")))
        response.getJSONObject("sku_identity").put("sku", "SKU-SUBSTITUTED")
        assertNull(ServerFrozenSkuIdentity.verify(response, payload))
    }

    @Test
    fun `unexpected barcode cannot receive invented sku`() {
        val body = """{"barcode":"$barcode","document_id":"$documentId","sku":null,"status":"UNEXPECTED"}"""
        val response = JSONObject().put(
            "sku_identity",
            JSONObject(body).put("snapshot_hash", sha256(body)),
        )

        val identity = ServerFrozenSkuIdentity.verify(response, payload)!!
        assertNull(identity.sku)
        assertEquals(ServerSkuIdentityStatus.UNEXPECTED, identity.status)
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray())
        .joinToString("") { "%02x".format(it) }
}
