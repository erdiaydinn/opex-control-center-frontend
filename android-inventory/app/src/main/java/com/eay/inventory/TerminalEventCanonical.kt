package com.eay.inventory

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
        append("\"barcode\":").append(jsonString(input.barcode.trim())).append(',')
        append("\"device_sequence\":").append(input.deviceSequence).append(',')
        append("\"document_id\":").append(jsonString(input.documentId.lowercase())).append(',')
        append("\"event_id\":").append(jsonString(input.eventId.lowercase())).append(',')
        append("\"location_id\":").append(jsonString(input.locationId.trim().uppercase())).append(',')
        append("\"occurred_at\":").append(jsonString(input.occurredAt)).append(',')
        append("\"quantity\":").append(jsonString(input.quantity.stripTrailingZeros().toPlainString())).append(',')
        append("\"symbology\":").append(jsonString(input.symbology.trim()))
        append('}')
    }

    private fun jsonString(value: String): String = buildString {
        append('"')
        value.forEach { character ->
            when (character) {
                '"' -> append("\\\"")
                '\\' -> append("\\\\")
                '\b' -> append("\\b")
                '\u000C' -> append("\\f")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> if (character.code < 0x20) append("\\u%04x".format(character.code)) else append(character)
            }
        }
        append('"')
    }

    fun hash(canonicalBody: String): String = MessageDigest.getInstance("SHA-256")
        .digest(canonicalBody.toByteArray())
        .joinToString("") { "%02x".format(it) }
}
