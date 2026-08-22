package com.eay.inventory

import java.math.BigDecimal
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.time.OffsetDateTime
import java.util.Locale
import java.util.UUID

data class TerminalEventInput(
    val activeShiftId: String,
    val attemptId: String,
    val barcode: String,
    val deviceSequence: Long,
    val documentId: String,
    val eventId: String,
    val leaseId: String,
    val locationId: String,
    val occurredAt: String,
    val quantity: BigDecimal,
    val symbology: String,
)

/**
 * Android counterpart of backend inventory `terminal_event_hash_input` plus
 * `canonical_payload_hash`. Any drift here makes an otherwise valid offline
 * event fail closed at the server boundary, so the exact JSON form is covered
 * by a cross-language golden vector.
 */
object TerminalEventCanonical {
    fun body(input: TerminalEventInput): String {
        val activeShiftId = input.activeShiftId.trim()
        val attemptId = normalizeUuid(input.attemptId)
        val barcode = input.barcode.trim()
        val locationId = input.locationId.trim().uppercase(Locale.ROOT)
        val symbology = input.symbology.trim()
        val documentId = normalizeUuid(input.documentId)
        val eventId = normalizeUuid(input.eventId)
        val leaseId = normalizeUuid(input.leaseId)
        val occurredAt = input.occurredAt.trim()

        require(activeShiftId.matches(Regex("^[A-Za-z0-9._:-]{1,128}$")))
        require(barcode.isNotBlank())
        require(input.deviceSequence > 0)
        require(locationId.isNotBlank())
        require(symbology.isNotBlank())
        require(input.quantity.signum() >= 0)
        OffsetDateTime.parse(occurredAt)

        val quantity = input.quantity.stripTrailingZeros().toPlainString()
        return buildString {
            append('{')
            append("\"active_shift_id\":").append(jsonString(activeShiftId)).append(',')
            append("\"attempt_id\":").append(jsonString(attemptId)).append(',')
            append("\"barcode\":").append(jsonString(barcode)).append(',')
            append("\"device_sequence\":").append(input.deviceSequence).append(',')
            append("\"document_id\":").append(jsonString(documentId)).append(',')
            append("\"event_id\":").append(jsonString(eventId)).append(',')
            append("\"lease_id\":").append(jsonString(leaseId)).append(',')
            append("\"location_id\":").append(jsonString(locationId)).append(',')
            append("\"occurred_at\":").append(jsonString(occurredAt)).append(',')
            append("\"quantity\":").append(jsonString(quantity)).append(',')
            append("\"symbology\":").append(jsonString(symbology))
            append('}')
        }
    }

    private fun normalizeUuid(value: String): String = UUID.fromString(value.trim()).toString()

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
                else -> if (character.code < 0x20) {
                    append("\\u%04x".format(character.code))
                } else {
                    append(character)
                }
            }
        }
        append('"')
    }

    fun hash(canonicalBody: String): String = MessageDigest.getInstance("SHA-256")
        .digest(canonicalBody.toByteArray(StandardCharsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}
