package com.eay.inventory

import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.time.OffsetDateTime
import java.util.Locale
import java.util.UUID

private const val LOCATION_COMPLETE_KIND = "LOCATION_COMPLETE"

data class LocationCompletionInput(
    val activeShiftId: String,
    val attemptId: String,
    val confirmedLineCount: Int,
    val deviceSequence: Long,
    val documentId: String,
    val eventId: String,
    val leaseId: String,
    val locationId: String,
    val occurredAt: String,
)

object LocationCompletionCanonical {
    fun body(input: LocationCompletionInput): String {
        val activeShiftId = input.activeShiftId.trim()
        val attemptId = UUID.fromString(input.attemptId.trim()).toString()
        val documentId = UUID.fromString(input.documentId.trim()).toString()
        val eventId = UUID.fromString(input.eventId.trim()).toString()
        val leaseId = UUID.fromString(input.leaseId.trim()).toString()
        val locationId = input.locationId.trim().uppercase(Locale.ROOT)
        val occurredAt = input.occurredAt.trim()

        require(activeShiftId.matches(Regex("^[A-Za-z0-9._:-]{1,128}$")))
        require(input.confirmedLineCount >= 0)
        require(input.deviceSequence > 0)
        require(locationId.isNotBlank())
        OffsetDateTime.parse(occurredAt)

        return buildString {
            append('{')
            append("\"active_shift_id\":").append(jsonString(activeShiftId)).append(',')
            append("\"attempt_id\":").append(jsonString(attemptId)).append(',')
            append("\"confirmed_line_count\":").append(input.confirmedLineCount).append(',')
            append("\"device_sequence\":").append(input.deviceSequence).append(',')
            append("\"document_id\":").append(jsonString(documentId)).append(',')
            append("\"event_id\":").append(jsonString(eventId)).append(',')
            append("\"event_kind\":").append(jsonString(LOCATION_COMPLETE_KIND)).append(',')
            append("\"lease_id\":").append(jsonString(leaseId)).append(',')
            append("\"location_id\":").append(jsonString(locationId)).append(',')
            append("\"occurred_at\":").append(jsonString(occurredAt))
            append('}')
        }
    }

    fun hash(canonicalBody: String): String = MessageDigest.getInstance("SHA-256")
        .digest(canonicalBody.toByteArray(StandardCharsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

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
}

object InventoryLocationCompletionEventFactory {
    fun create(
        context: InventoryCountEventContext,
        confirmedLineCount: Int,
        deviceSequence: Long,
        eventId: String,
        occurredAt: String,
        authBindingId: String,
    ): OfflineEvent {
        require(confirmedLineCount >= 0)
        require(deviceSequence > 0)
        require(authBindingId.isNotBlank())
        val normalizedEventId = UUID.fromString(eventId.trim()).toString()
        val canonicalBody = LocationCompletionCanonical.body(
            LocationCompletionInput(
                activeShiftId = context.activeShiftId,
                attemptId = context.attemptId,
                confirmedLineCount = confirmedLineCount,
                deviceSequence = deviceSequence,
                documentId = context.documentId,
                eventId = normalizedEventId,
                leaseId = context.leaseId,
                locationId = context.locationId,
                occurredAt = occurredAt,
            ),
        )
        return OfflineEvent(
            eventId = normalizedEventId,
            deviceSequence = deviceSequence,
            canonicalPayload = canonicalBody,
            payloadHash = LocationCompletionCanonical.hash(canonicalBody),
            authBindingId = authBindingId,
        )
    }
}
