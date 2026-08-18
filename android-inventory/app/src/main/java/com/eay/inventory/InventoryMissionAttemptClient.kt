package com.eay.inventory

import android.content.Context
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.time.OffsetDateTime
import java.time.Instant
import java.util.Locale
import java.util.UUID

data class InventoryMissionAttemptClaim(
    val attemptId: String,
    val leaseId: String,
    val documentId: String,
    val locationId: String,
    val activeShiftId: String,
    val validFrom: String,
    val expiresAt: String,
) {
    init {
        UUID.fromString(attemptId)
        UUID.fromString(leaseId)
        UUID.fromString(documentId)
        require(locationId.isNotBlank())
        require(activeShiftId.matches(Regex("^[A-Za-z0-9._:-]{1,128}$")))
        val start = OffsetDateTime.parse(validFrom)
        val end = OffsetDateTime.parse(expiresAt)
        require(end.isAfter(start))
    }
}

data class MissionClaimInput(
    val activeShiftId: String,
    val documentId: String,
    val leaseSeconds: Int,
    val locationId: String,
)

object MissionClaimCanonical {
    fun body(input: MissionClaimInput): String {
        val activeShift = input.activeShiftId.trim()
        val documentId = UUID.fromString(input.documentId.trim()).toString()
        val location = input.locationId.trim().uppercase(Locale.ROOT)
        require(activeShift.matches(Regex("^[A-Za-z0-9._:-]{1,128}$")))
        require(input.leaseSeconds in 60..1800)
        require(location.isNotBlank())
        return buildString {
            append('{')
            append("\"active_shift_id\":").append(jsonString(activeShift)).append(',')
            append("\"document_id\":").append(jsonString(documentId)).append(',')
            append("\"lease_seconds\":").append(input.leaseSeconds).append(',')
            append("\"location_id\":").append(jsonString(location))
            append('}')
        }
    }

    fun hash(body: String): String = MessageDigest.getInstance("SHA-256")
        .digest(body.toByteArray(StandardCharsets.UTF_8))
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
                } else append(character)
            }
        }
        append('"')
    }
}

enum class InventoryMissionClaimCode {
    OK,
    AUTH_REQUIRED,
    POLICY_REJECTED,
    DEVICE_REJECTED,
    CONFLICT,
    RETRYABLE,
    CONTRACT_REJECTED,
    PERMANENT_REJECTED,
}

data class InventoryMissionClaimResult(
    val code: InventoryMissionClaimCode,
    val claim: InventoryMissionAttemptClaim? = null,
) {
    val accepted: Boolean get() = code == InventoryMissionClaimCode.OK && claim != null
}

class InventoryMissionAttemptClient(context: Context) {
    private val appContext = context.applicationContext

    fun claim(task: InventoryTerminalCountTask, leaseSeconds: Int = 900): InventoryMissionClaimResult {
        val token = AccessTokenMemory.freshOrNull()
            ?: return InventoryMissionClaimResult(InventoryMissionClaimCode.AUTH_REQUIRED)
        val deviceId = runCatching { ManagedDeviceIdentity(appContext).requireDeviceId() }
            .getOrElse { return InventoryMissionClaimResult(InventoryMissionClaimCode.DEVICE_REJECTED) }
        val canonical = MissionClaimCanonical.body(
            MissionClaimInput(
                activeShiftId = task.activeShiftId,
                documentId = task.documentId,
                leaseSeconds = leaseSeconds,
                locationId = task.locationId,
            ),
        )
        val payloadHash = MissionClaimCanonical.hash(canonical)
        val timestamp = Instant.now().toString()
        val nonce = UUID.randomUUID().toString()
        val proof = "$deviceId\n$timestamp\n$nonce\n$payloadHash".toByteArray(Charsets.UTF_8)
        val signature = runCatching { DeviceRequestSigner.sign(proof) }
            .getOrElse { return InventoryMissionClaimResult(InventoryMissionClaimCode.DEVICE_REJECTED) }
        val body = JSONObject(canonical).put("payload_hash", payloadHash).toString()
        val request = Request.Builder()
            .url(BuildConfig.API_BASE_URL.trimEnd('/') + "/api/inventory/v1/terminal/mission-attempts/claim")
            .header("Authorization", "Bearer $token")
            .header("X-EAY-Device-ID", deviceId.toString())
            .header("X-EAY-Request-Timestamp", timestamp)
            .header("X-EAY-Request-Nonce", nonce)
            .header("X-EAY-Device-Signature", signature)
            .post(body.toRequestBody("application/json".toMediaType()))
            .build()

        val response = try {
            PinnedApi.client.newCall(request).execute()
        } catch (_: IOException) {
            return InventoryMissionClaimResult(InventoryMissionClaimCode.RETRYABLE)
        }
        response.use {
            val classified = classifyHttp(it.code)
            if (classified != InventoryMissionClaimCode.OK) {
                if (classified == InventoryMissionClaimCode.AUTH_REQUIRED) AccessTokenMemory.clear()
                return InventoryMissionClaimResult(classified)
            }
            val claim = runCatching {
                val json = JSONObject(it.body?.string().orEmpty())
                InventoryMissionAttemptClaim(
                    attemptId = json.getString("attempt_id"),
                    leaseId = json.getString("lease_id"),
                    documentId = json.getString("document_id"),
                    locationId = json.getString("location_id"),
                    activeShiftId = json.getString("active_shift_id"),
                    validFrom = json.getString("valid_from"),
                    expiresAt = json.getString("expires_at"),
                )
            }.getOrElse {
                return InventoryMissionClaimResult(InventoryMissionClaimCode.CONTRACT_REJECTED)
            }
            val contractMatches =
                claim.documentId == task.documentId &&
                    claim.locationId.trim().uppercase(Locale.ROOT) == task.locationId.trim().uppercase(Locale.ROOT) &&
                    claim.activeShiftId == task.activeShiftId
            if (!contractMatches) {
                return InventoryMissionClaimResult(InventoryMissionClaimCode.CONTRACT_REJECTED)
            }
            return InventoryMissionClaimResult(InventoryMissionClaimCode.OK, claim)
        }
    }

    private fun classifyHttp(code: Int): InventoryMissionClaimCode = when {
        code in 200..299 -> InventoryMissionClaimCode.OK
        code == 401 -> InventoryMissionClaimCode.AUTH_REQUIRED
        code == 403 -> InventoryMissionClaimCode.POLICY_REJECTED
        code == 409 -> InventoryMissionClaimCode.CONFLICT
        code == 410 -> InventoryMissionClaimCode.DEVICE_REJECTED
        code == 408 || code == 429 || code >= 500 -> InventoryMissionClaimCode.RETRYABLE
        else -> InventoryMissionClaimCode.PERMANENT_REJECTED
    }
}
