package com.eay.inventory

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.FormBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.time.Instant
import java.security.MessageDigest
import java.util.UUID

class InventorySyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val database = InventoryDatabase.get(applicationContext)
        val deviceId = runCatching { ManagedDeviceIdentity(applicationContext).requireDeviceId() }.getOrElse { return Result.failure() }
        val session = database.sessions().get() ?: return Result.failure()
        if (session.authBindingId.isBlank()) return Result.failure()
        val dao = database.events()
        val token = AccessTokenMemory.freshOrNull() ?: refreshAccessToken() ?: return Result.retry()
        val due = dao.due(System.currentTimeMillis())
        for (event in due) {
            if (!QueueIntegrity.valid(event, session.authBindingId)) return Result.failure()
            val timestamp = Instant.now().toString()
            val nonce = UUID.randomUUID().toString()
            val proof = "$deviceId\n$timestamp\n$nonce\n${event.payloadHash}".toByteArray()
            val request = Request.Builder()
                .url("${BuildConfig.API_BASE_URL.trimEnd('/')}/api/inventory/v1/terminal/events")
                .header("Authorization", "Bearer $token")
                .header("X-EAY-Device-ID", deviceId.toString())
                .header("X-EAY-Request-Timestamp", timestamp)
                .header("X-EAY-Request-Nonce", nonce)
                .header("X-EAY-Device-Signature", DeviceRequestSigner.sign(proof))
                .post(JSONObject(event.canonicalPayload).put("payload_hash", event.payloadHash).toString()
                    .toRequestBody("application/json".toMediaType()))
                .build()
            try {
                PinnedApi.client.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        val accepted = JSONObject(response.body?.string().orEmpty()).optBoolean("accepted")
                        if (!accepted) return Result.failure()
                        dao.acknowledge(event.eventId)
                    } else if (response.code in 400..499 && response.code != 408 && response.code != 429) {
                        return Result.failure()
                    } else {
                        dao.retry(event.eventId, nextAttempt(event.attempts))
                        return Result.retry()
                    }
                }
            } catch (_: Exception) {
                dao.retry(event.eventId, nextAttempt(event.attempts))
                return Result.retry()
            }
        }
        return Result.success()
    }

    private fun nextAttempt(attempts: Int): Long {
        val seconds = minOf(900L, 2L shl minOf(attempts, 8))
        return System.currentTimeMillis() + seconds * 1000L
    }

    private suspend fun refreshAccessToken(): String? {
        val sessionDao = InventoryDatabase.get(applicationContext).sessions()
        val session = sessionDao.get() ?: return null
        if (session.authBindingId.isBlank() || !session.tokenEndpoint.startsWith("https://")) return null
        val request = Request.Builder().url(session.tokenEndpoint)
            .post(FormBody.Builder()
                .add("grant_type", "refresh_token")
                .add("refresh_token", session.refreshToken)
                .add("client_id", session.clientId)
                .build())
            .build()
        return try {
            PinnedApi.client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return null
                val body = JSONObject(response.body?.string().orEmpty())
                val token = body.optString("access_token").takeIf { it.isNotBlank() } ?: return null
                val expiresAt = System.currentTimeMillis() + body.optLong("expires_in", 300L) * 1000
                val rotated = body.optString("refresh_token").takeIf { it.isNotBlank() }
                if (rotated != null) sessionDao.put(session.copy(refreshToken = rotated))
                AccessTokenMemory.replace(token, expiresAt)
                token
            }
        } catch (_: Exception) { null }
    }
}

object QueueIntegrity {
    fun valid(event: OfflineEvent, currentAuthBindingId: String): Boolean {
        if (currentAuthBindingId.isBlank() || event.authBindingId.isBlank()) return false
        if (event.authBindingId != currentAuthBindingId) return false
        val digest = MessageDigest.getInstance("SHA-256").digest(event.canonicalPayload.toByteArray())
            .joinToString("") { "%02x".format(it) }
        return digest == event.payloadHash
    }
}
