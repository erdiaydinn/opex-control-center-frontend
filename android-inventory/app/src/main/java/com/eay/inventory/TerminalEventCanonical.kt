package com.eay.inventory

import org.json.JSONObject
import java.math.BigDecimal
import java.security.MessageDigest

data class TerminalEventInput(
    val barcode: String,
    val deviceSequence: Long,
    val documentId: String,
    val eventId: String,
    val locationId: String,
    val occurredAt: String,
    val quantity: BigDecimal,
    val symbology: String,
)

object TerminalEventCanonical {
    fun body(input: TerminalEventInput): String = buildString {
        append('{')
        append("\"barcode\":").append(JSONObject.quote(input.barcode.trim())).append(',')
        append("\"device_sequence\":").append(input.deviceSequence).append(',')
        append("\"document_id\":").append(JSONObject.quote(input.documentId.lowercase())).append(',')
        append("\"event_id\":").append(JSONObject.quote(input.eventId.lowercase())).append(',')
        append("\"location_id\":").append(JSONObject.quote(input.locationId.trim().uppercase())).append(',')
        append("\"occurred_at\":").append(JSONObject.quote(input.occurredAt)).append(',')
        append("\"quantity\":").append(JSONObject.quote(input.quantity.stripTrailingZeros().toPlainString())).append(',')
        append("\"symbology\":").append(JSONObject.quote(input.symbology.trim()))
        append('}')
    }

    fun hash(canonicalBody: String): String = MessageDigest.getInstance("SHA-256")
        .digest(canonicalBody.toByteArray())
        .joinToString("") { "%02x".format(it) }
}
