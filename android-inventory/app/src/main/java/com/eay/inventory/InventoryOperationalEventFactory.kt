package com.eay.inventory

import com.eay.mobile.core.OperationalStepKind
import com.eay.mobile.core.OperationalValueCanonicalizer
import org.json.JSONObject
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.time.OffsetDateTime
import java.util.Locale
import java.util.UUID

data class InventoryOperationalEventContext(
    val missionId: String,
    val claimId: String,
    val activeShiftId: String,
)

data class InventoryOperationalEventInput(
    val context: InventoryOperationalEventContext,
    val stepKind: OperationalStepKind,
    val rawValue: String,
    val eventId: String,
    val deviceSequence: Long,
    val occurredAt: String,
)

object InventoryOperationalEventCanonical {
    fun create(input: InventoryOperationalEventInput, authBindingId: String): OfflineEvent {
        require(authBindingId.isNotBlank())
        val body = body(input)
        return OfflineEvent(
            eventId = normalizeUuid(input.eventId),
            deviceSequence = input.deviceSequence,
            canonicalPayload = body,
            payloadHash = payloadHash(body),
            authBindingId = authBindingId,
        )
    }

    fun body(input: InventoryOperationalEventInput): String {
        val shift = input.context.activeShiftId.trim()
        val claim = normalizeUuid(input.context.claimId)
        val event = normalizeUuid(input.eventId)
        val mission = normalizeUuid(input.context.missionId)
        val occurredAt = input.occurredAt.trim()
        val value = OperationalValueCanonicalizer.normalize(input.stepKind, input.rawValue)
        val valueHash = OperationalValueCanonicalizer.hash(input.stepKind, input.rawValue)
        require(shift.matches(Regex("^[A-Za-z0-9._:-]{1,128}$")))
        require(input.deviceSequence > 0)
        OffsetDateTime.parse(occurredAt)
        return buildString {
            append('{')
            append("\"active_shift_id\":").append(jsonString(shift)).append(',')
            append("\"claim_id\":").append(jsonString(claim)).append(',')
            append("\"device_sequence\":").append(input.deviceSequence).append(',')
            append("\"event_id\":").append(jsonString(event)).append(',')
            append("\"mission_id\":").append(jsonString(mission)).append(',')
            append("\"occurred_at\":").append(jsonString(occurredAt)).append(',')
            append("\"step_kind\":").append(jsonString(input.stepKind.name)).append(',')
            append("\"value\":").append(jsonString(value)).append(',')
            append("\"value_hash\":").append(jsonString(valueHash))
            append('}')
        }
    }

    fun isOperationalBody(canonicalPayload: String): Boolean = runCatching {
        val json = JSONObject(canonicalPayload)
        json.has("mission_id") && json.has("claim_id") && json.has("step_kind") && json.has("value_hash")
    }.getOrDefault(false)

    fun payloadHash(canonicalPayload: String): String {
        val json = JSONObject(canonicalPayload)
        val canonicalHashInput = buildString {
            append('{')
            append("\"active_shift_id\":").append(jsonString(json.getString("active_shift_id").trim())).append(',')
            append("\"claim_id\":").append(jsonString(normalizeUuid(json.getString("claim_id")))).append(',')
            append("\"device_sequence\":").append(json.getLong("device_sequence")).append(',')
            append("\"event_id\":").append(jsonString(normalizeUuid(json.getString("event_id")))).append(',')
            append("\"mission_id\":").append(jsonString(normalizeUuid(json.getString("mission_id")))).append(',')
            append("\"occurred_at\":").append(jsonString(json.getString("occurred_at"))).append(',')
            append("\"step_kind\":").append(jsonString(json.getString("step_kind").trim().uppercase(Locale.ROOT))).append(',')
            append("\"value_hash\":").append(jsonString(json.getString("value_hash").lowercase(Locale.ROOT)))
            append('}')
        }
        return sha256(canonicalHashInput)
    }

    private fun normalizeUuid(value: String): String = UUID.fromString(value.trim()).toString()

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(StandardCharsets.UTF_8))
        .joinToString("") { "%02x".format(Locale.ROOT, it) }

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
                    append("\\u%04x".format(Locale.ROOT, character.code))
                } else {
                    append(character)
                }
            }
        }
        append('"')
    }
}
