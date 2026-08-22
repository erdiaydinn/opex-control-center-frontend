package com.eay.inventory

import android.content.Context
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

enum class InventoryMissionClaimCode {
    OK,
    AUTH_REQUIRED,
    POLICY_REJECTED,
    DEVICE_REJECTED,
    BUSINESS_CONFLICT,
    RETRYABLE,
    CONTRACT_REJECTED,
    PERMANENT_REJECTED,
}

data class InventoryMissionClaimResult(
    val code: InventoryMissionClaimCode,
    val task: InventoryTerminalCountTask? = null,
) {
    val accepted: Boolean get() = code == InventoryMissionClaimCode.OK && task != null
}

object InventoryMissionClaimContract {
    fun canonicalBody(documentId: String, locationId: String): String {
        val document = UUID.fromString(documentId.trim()).toString()
        val location = locationId.trim().uppercase(Locale.ROOT)
        require(location.isNotBlank())
        return "{\"document_id\":${JSONObject.quote(document)},\"location_id\":${JSONObject.quote(location)}}"
    }

    fun hash(canonicalBody: String): String = MessageDigest.getInstance("SHA-256")
        .digest(canonicalBody.toByteArray(StandardCharsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

    fun classifyHttp(httpCode: Int): InventoryMissionClaimCode = when {
        httpCode in 200..299 -> InventoryMissionClaimCode.OK
        httpCode == 401 -> InventoryMissionClaimCode.AUTH_REQUIRED
        httpCode == 403 -> InventoryMissionClaimCode.POLICY_REJECTED
        httpCode == 409 -> InventoryMissionClaimCode.BUSINESS_CONFLICT
        httpCode == 410 -> InventoryMissionClaimCode.DEVICE_REJECTED
        httpCode == 408 || httpCode == 429 || httpCode >= 500 -> InventoryMissionClaimCode.RETRYABLE
        else -> InventoryMissionClaimCode.PERMANENT_REJECTED
    }

    fun bindResponse(
        source: InventoryTerminalCountTask,
        response: JSONObject,
    ): InventoryTerminalCountTask {
        require(response.getString("mission_id") == source.missionId) {
            "Mission claim response mission binding mismatch"
        }
        require(response.getString("document_id") == UUID.fromString(source.documentId).toString()) {
            "Mission claim response document binding mismatch"
        }
        require(
            response.getString("location_id").trim().uppercase(Locale.ROOT) ==
                source.locationId.trim().uppercase(Locale.ROOT),
        ) { "Mission claim response location binding mismatch" }
        require(response.getString("active_shift_id") == source.activeShiftId) {
            "Mission claim response shift binding mismatch"
        }
        require(response.getString("claim_status") == InventoryMissionClaimStatus.OWNED.name) {
            "Mission claim response did not grant an owned lease"
        }
        return source.copy(
            claimStatus = InventoryMissionClaimStatus.OWNED,
            attemptId = response.getString("attempt_id"),
            leaseId = response.getString("lease_id"),
            leaseValidUntil = response.getString("lease_valid_until"),
        )
    }
}

/**
 * Server-authoritative mission claim client. The signed request proves the managed
 * device submitted the exact document/location claim payload; the Android UI does
 * not mint attempts, leases, permissions, shifts or tenant authority.
 *
 * Even a task listed as OWNED is re-claimed here. Task-list state is only a snapshot;
 * the claim endpoint is the authority that confirms a still-live lease or issues the
 * next immutable lease interval for the same governed owner after expiry.
 */
class InventoryTerminalMissionClaimClient(context: Context) {
    private val appContext = context.applicationContext

    fun claim(task: InventoryTerminalCountTask): InventoryMissionClaimResult {
        val token = AccessTokenMemory.freshOrNull()
            ?: return InventoryMissionClaimResult(InventoryMissionClaimCode.AUTH_REQUIRED)
        val deviceId = runCatching {
            ManagedDeviceIdentity(appContext).requireDeviceId()
        }.getOrElse {
            return InventoryMissionClaimResult(InventoryMissionClaimCode.DEVICE_REJECTED)
        }
        val canonical = runCatching {
            InventoryMissionClaimContract.canonicalBody(task.documentId, task.locationId)
        }.getOrElse {
            return InventoryMissionClaimResult(InventoryMissionClaimCode.CONTRACT_REJECTED)
        }
        val payloadHash = InventoryMissionClaimContract.hash(canonical)
        val timestamp = Instant.now().toString()
        val nonce = UUID.randomUUID().toString()
        val proof = "$deviceId\n$timestamp\n$nonce\n$payloadHash".toByteArray(Charsets.UTF_8)
        val signature = runCatching { DeviceRequestSigner.sign(proof) }.getOrElse {
            return InventoryMissionClaimResult(InventoryMissionClaimCode.DEVICE_REJECTED)
        }
        val requestBody = JSONObject(canonical)
            .put("payload_hash", payloadHash)
            .toString()
        val request = Request.Builder()
            .url(BuildConfig.API_BASE_URL.trimEnd('/') + "/api/inventory/v1/terminal/missions/claim")
            .header("Authorization", "Bearer $token")
            .header("X-EAY-Device-ID", deviceId.toString())
            .header("X-EAY-Request-Timestamp", timestamp)
            .header("X-EAY-Request-Nonce", nonce)
            .header("X-EAY-Device-Signature", signature)
            .post(requestBody.toRequestBody("application/json".toMediaType()))
            .build()

        val response = try {
            PinnedApi.client.newCall(request).execute()
        } catch (_: IOException) {
            return InventoryMissionClaimResult(InventoryMissionClaimCode.RETRYABLE)
        }
        response.use {
            val classified = InventoryMissionClaimContract.classifyHttp(it.code)
            if (classified != InventoryMissionClaimCode.OK) {
                if (classified == InventoryMissionClaimCode.AUTH_REQUIRED) AccessTokenMemory.clear()
                return InventoryMissionClaimResult(classified)
            }
            return runCatching {
                val claimed = InventoryMissionClaimContract.bindResponse(
                    task,
                    JSONObject(it.body?.string().orEmpty()),
                )
                InventoryMissionClaimResult(InventoryMissionClaimCode.OK, claimed)
            }.getOrElse {
                InventoryMissionClaimResult(InventoryMissionClaimCode.CONTRACT_REJECTED)
            }
        }
    }
}
