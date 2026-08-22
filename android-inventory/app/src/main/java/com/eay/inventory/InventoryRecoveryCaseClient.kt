package com.eay.inventory

import android.content.Context
import com.eay.mobile.core.SyncQuarantineReason
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.time.Instant
import java.util.Locale
import java.util.UUID

enum class InventoryRecoveryCaseCode {
    OK,
    NOT_ELIGIBLE,
    AUTH_REQUIRED,
    POLICY_REJECTED,
    DEVICE_REJECTED,
    BUSINESS_CONFLICT,
    RETRYABLE,
    CONTRACT_REJECTED,
    PERMANENT_REJECTED,
}

data class InventoryRecoveryCaseResult(
    val code: InventoryRecoveryCaseCode,
    val caseId: String? = null,
) {
    val accepted: Boolean get() = code == InventoryRecoveryCaseCode.OK && caseId != null
}

data class InventoryRecoveryCaseRequest(
    val eventId: String,
    val documentId: String,
    val locationId: String,
    val payloadHash: String,
    val quarantineReason: String,
    val serverCode: String?,
)

/**
 * Cross-language canonical request contract matching backend recovery_request_hash.
 *
 * The recovery command intentionally carries no barcode, quantity, tenant, employee,
 * device, lease or stock truth. Those remain in immutable local evidence or server
 * authority. Only the exact event identity/hash and safe provenance can open review.
 */
object InventoryRecoveryCaseContract {
    private val eligibleReasons = setOf(
        SyncQuarantineReason.BUSINESS_CONFLICT,
        SyncQuarantineReason.DEPENDENCY_BLOCKED,
        SyncQuarantineReason.RETRY_EXHAUSTED,
    )

    fun from(event: OfflineEvent): InventoryRecoveryCaseRequest? {
        if (event.state.trim().uppercase(Locale.ROOT) != "QUARANTINED") return null
        if (!event.recoveryCaseId.isNullOrBlank()) return null
        val reason = runCatching {
            SyncQuarantineReason.valueOf(event.quarantineReason.orEmpty())
        }.getOrNull() ?: return null
        if (reason !in eligibleReasons) return null
        val normalizedPayloadHash = event.payloadHash.trim().lowercase(Locale.ROOT)
        if (!normalizedPayloadHash.matches(Regex("^[0-9a-f]{64}$"))) return null
        if (TerminalEventCanonical.hash(event.canonicalPayload) != normalizedPayloadHash) return null
        val canonical = runCatching { JSONObject(event.canonicalPayload) }.getOrNull() ?: return null
        val eventId = runCatching {
            UUID.fromString(canonical.getString("event_id").trim()).toString()
        }.getOrNull() ?: return null
        if (eventId != runCatching { UUID.fromString(event.eventId.trim()).toString() }.getOrNull()) {
            return null
        }
        val documentId = runCatching {
            UUID.fromString(canonical.getString("document_id").trim()).toString()
        }.getOrNull() ?: return null
        val locationId = canonical.optString("location_id").trim().uppercase(Locale.ROOT)
        if (locationId.isBlank()) return null
        return InventoryRecoveryCaseRequest(
            eventId = eventId,
            documentId = documentId,
            locationId = locationId,
            payloadHash = normalizedPayloadHash,
            quarantineReason = reason.name,
            serverCode = event.lastServerCode?.trim()?.takeIf { it.isNotBlank() },
        )
    }

    fun canonicalCommand(request: InventoryRecoveryCaseRequest): String = buildString {
        append('{')
        append("\"document_id\":")
            .append(JSONObject.quote(normalizeUuid(request.documentId)))
            .append(',')
        append("\"event_id\":")
            .append(JSONObject.quote(normalizeUuid(request.eventId)))
            .append(',')
        append("\"location_id\":")
            .append(JSONObject.quote(request.locationId.trim().uppercase(Locale.ROOT)))
            .append(',')
        append("\"payload_hash\":")
            .append(JSONObject.quote(request.payloadHash.trim().lowercase(Locale.ROOT)))
            .append(',')
        append("\"quarantine_reason\":")
            .append(JSONObject.quote(request.quarantineReason.trim().uppercase(Locale.ROOT)))
            .append(',')
        append("\"server_code\":")
        val serverCode = request.serverCode?.trim()?.takeIf { it.isNotBlank() }
        if (serverCode == null) append("null") else append(JSONObject.quote(serverCode))
        append('}')
    }

    fun hash(request: InventoryRecoveryCaseRequest): String = MessageDigest.getInstance("SHA-256")
        .digest(canonicalCommand(request).toByteArray(StandardCharsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

    fun body(request: InventoryRecoveryCaseRequest): String = JSONObject()
        .put("event_id", normalizeUuid(request.eventId))
        .put("document_id", normalizeUuid(request.documentId))
        .put("location_id", request.locationId.trim().uppercase(Locale.ROOT))
        .put("payload_hash", request.payloadHash.trim().lowercase(Locale.ROOT))
        .put("quarantine_reason", request.quarantineReason.trim().uppercase(Locale.ROOT))
        .put(
            "server_code",
            request.serverCode?.trim()?.takeIf { it.isNotBlank() } ?: JSONObject.NULL,
        )
        .toString()

    fun classifyHttp(httpCode: Int): InventoryRecoveryCaseCode = when {
        httpCode in 200..299 -> InventoryRecoveryCaseCode.OK
        httpCode == 401 -> InventoryRecoveryCaseCode.AUTH_REQUIRED
        httpCode == 403 -> InventoryRecoveryCaseCode.POLICY_REJECTED
        httpCode == 409 -> InventoryRecoveryCaseCode.BUSINESS_CONFLICT
        httpCode == 410 -> InventoryRecoveryCaseCode.DEVICE_REJECTED
        httpCode == 408 || httpCode == 429 || httpCode >= 500 -> InventoryRecoveryCaseCode.RETRYABLE
        else -> InventoryRecoveryCaseCode.PERMANENT_REJECTED
    }

    fun bindResponse(
        request: InventoryRecoveryCaseRequest,
        response: JSONObject,
    ): String {
        require(response.getString("event_id") == normalizeUuid(request.eventId))
        require(response.getString("document_id") == normalizeUuid(request.documentId))
        require(
            response.getString("location_id").trim().uppercase(Locale.ROOT) ==
                request.locationId.trim().uppercase(Locale.ROOT),
        )
        require(response.getString("payload_hash") == request.payloadHash.lowercase(Locale.ROOT))
        require(response.getString("evidence_policy") == "PRESERVE_NO_CLIENT_PROMOTION")
        return UUID.fromString(response.getString("case_id")).toString()
    }

    private fun normalizeUuid(value: String): String = UUID.fromString(value.trim()).toString()
}

/**
 * Opens a signed, replay-protected server review case for one immutable quarantined
 * event. It has no API for retry, delete, rebind, lease renewal or stock mutation.
 */
class InventoryRecoveryCaseClient(context: Context) {
    private val appContext = context.applicationContext

    fun requestReview(event: OfflineEvent): InventoryRecoveryCaseResult {
        val recovery = InventoryRecoveryCaseContract.from(event)
            ?: return InventoryRecoveryCaseResult(InventoryRecoveryCaseCode.NOT_ELIGIBLE)
        val token = AccessTokenMemory.freshOrNull()
            ?: return InventoryRecoveryCaseResult(InventoryRecoveryCaseCode.AUTH_REQUIRED)
        val deviceId = runCatching {
            ManagedDeviceIdentity(appContext).requireDeviceId()
        }.getOrElse {
            return InventoryRecoveryCaseResult(InventoryRecoveryCaseCode.DEVICE_REJECTED)
        }
        val commandHash = InventoryRecoveryCaseContract.hash(recovery)
        val timestamp = Instant.now().toString()
        val nonce = UUID.randomUUID().toString()
        val proof = "$deviceId\n$timestamp\n$nonce\n$commandHash".toByteArray(Charsets.UTF_8)
        val signature = runCatching { DeviceRequestSigner.sign(proof) }.getOrElse {
            return InventoryRecoveryCaseResult(InventoryRecoveryCaseCode.DEVICE_REJECTED)
        }
        val request = Request.Builder()
            .url(BuildConfig.API_BASE_URL.trimEnd('/') + "/api/inventory/v1/recovery-cases")
            .header("Authorization", "Bearer $token")
            .header("X-EAY-Device-ID", deviceId.toString())
            .header("X-EAY-Request-Timestamp", timestamp)
            .header("X-EAY-Request-Nonce", nonce)
            .header("X-EAY-Device-Signature", signature)
            .post(
                InventoryRecoveryCaseContract.body(recovery)
                    .toRequestBody("application/json".toMediaType()),
            )
            .build()

        val response = try {
            PinnedApi.client.newCall(request).execute()
        } catch (_: IOException) {
            return InventoryRecoveryCaseResult(InventoryRecoveryCaseCode.RETRYABLE)
        }
        response.use {
            val classified = InventoryRecoveryCaseContract.classifyHttp(it.code)
            if (classified != InventoryRecoveryCaseCode.OK) {
                if (classified == InventoryRecoveryCaseCode.AUTH_REQUIRED) AccessTokenMemory.clear()
                return InventoryRecoveryCaseResult(classified)
            }
            return runCatching {
                InventoryRecoveryCaseResult(
                    InventoryRecoveryCaseCode.OK,
                    InventoryRecoveryCaseContract.bindResponse(
                        recovery,
                        JSONObject(it.body?.string().orEmpty()),
                    ),
                )
            }.getOrElse {
                InventoryRecoveryCaseResult(InventoryRecoveryCaseCode.CONTRACT_REJECTED)
            }
        }
    }
}
