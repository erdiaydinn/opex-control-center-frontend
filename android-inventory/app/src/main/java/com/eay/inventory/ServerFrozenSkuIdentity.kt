package com.eay.inventory

import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID

enum class ServerSkuIdentityStatus { KNOWN, UNEXPECTED }

/**
 * Identity acknowledgement for exactly one submitted barcode.
 *
 * This is intentionally not a catalog or stock snapshot: expected quantity,
 * cost and variance have no representation in the Android contract.
 */
data class ServerFrozenSkuIdentity(
    val documentId: String,
    val barcode: String,
    val sku: String?,
    val status: ServerSkuIdentityStatus,
    val snapshotHash: String,
) {
    init {
        UUID.fromString(documentId)
        require(barcode.isNotBlank())
        require(snapshotHash.matches(Regex("^[a-f0-9]{64}$")))
        require((status == ServerSkuIdentityStatus.KNOWN) == !sku.isNullOrBlank())
    }

    companion object {
        fun verify(response: JSONObject, signedPayload: String): ServerFrozenSkuIdentity? =
            runCatching {
                val request = JSONObject(signedPayload)
                val identity = response.getJSONObject("sku_identity")
                val documentId = identity.getString("document_id").trim()
                val barcode = identity.getString("barcode").trim()
                val status = ServerSkuIdentityStatus.valueOf(identity.getString("status"))
                val sku = if (identity.isNull("sku")) null else identity.getString("sku").trim()
                val snapshotHash = identity.getString("snapshot_hash").trim()
                require(documentId == UUID.fromString(request.getString("document_id")).toString())
                require(barcode == request.getString("barcode").trim())
                val canonical = buildString {
                    append("{\"barcode\":\"").append(jsonEscape(barcode))
                    append("\",\"document_id\":\"").append(documentId)
                    append("\",\"sku\":")
                    if (sku == null) append("null") else append("\"").append(jsonEscape(sku)).append("\"")
                    append(",\"status\":\"").append(status.name).append("\"}")
                }
                require(sha256(canonical) == snapshotHash)
                ServerFrozenSkuIdentity(documentId, barcode, sku, status, snapshotHash)
            }.getOrNull()

        private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
            .digest(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }

        private fun jsonEscape(value: String): String = JSONObject.quote(value).removeSurrounding("\"")
    }
}
