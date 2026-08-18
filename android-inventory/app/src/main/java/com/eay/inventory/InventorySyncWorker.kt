package com.eay.inventory

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.eay.mobile.core.SyncQuarantineReason
import com.eay.mobile.core.SyncRetryPolicy
import com.eay.mobile.core.SyncServerOutcome
import com.eay.mobile.core.SyncServerVerdict
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.UUID

object InventorySyncClassifier {
    fun classify(
        httpCode: Int,
        accepted: Boolean?,
        idempotentReplay: Boolean?,
    ): SyncServerVerdict = when {
        httpCode in 200..299 && accepted == true && idempotentReplay == true ->
            SyncServerVerdict(
                SyncServerOutcome.EXACT_REPLAY,
                "HTTP_${httpCode}_EXACT_REPLAY",
            )
        httpCode in 200..299 && accepted == true ->
            SyncServerVerdict(
                SyncServerOutcome.COMMITTED,
                "HTTP_${httpCode}_COMMITTED",
            )
        httpCode == 401 ->
            SyncServerVerdict(SyncServerOutcome.AUTH_REJECTED, "HTTP_401")
        httpCode == 403 ->
            SyncServerVerdict(SyncServerOutcome.POLICY_REJECTED, "HTTP_403")
        httpCode == 409 ->
            SyncServerVerdict(SyncServerOutcome.BUSINESS_CONFLICT, "HTTP_409")
        httpCode == 410 ->
            SyncServerVerdict(SyncServerOutcome.DEVICE_REJECTED, "HTTP_410")
        httpCode == 408 || httpCode == 429 || httpCode >= 500 ->
            SyncServerVerdict(SyncServerOutcome.RETRYABLE_FAILURE, "HTTP_$httpCode")
        else ->
            SyncServerVerdict(SyncServerOutcome.PERMANENT_REJECTED, "HTTP_$httpCode")
    }
}

class InventorySyncWorker(
    context: Context,
    parameters: WorkerParameters,
) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val db = InventoryDatabase.get(applicationContext)
        val dao = db.events()
        val session = db.sessions().current() ?: return@withContext Result.failure()
        if (session.authBindingId.isBlank()) return@withContext Result.failure()

        if (!ensureFreshAccessToken(session)) {
            return@withContext Result.retry()
        }

        val due = dao.due(System.currentTimeMillis())
        if (due.isEmpty()) {
            return@withContext if (dao.pendingCount() > 0) {
                Result.retry()
            } else {
                Result.success()
            }
        }

        val http = PinnedHttp.client()
        val url = BuildConfig.API_BASE_URL.trimEnd('/') +
            "/api/inventory/v1/terminal/events"
        for (event in due) {
            val localFailure = QueueIntegrity.failureReason(
                event,
                session.authBindingId,
            )
            if (localFailure != null) {
                dao.quarantine(
                    event.eventId,
                    localFailure.name,
                    "LOCAL_INTEGRITY",
                )
                continue
            }

            val timestamp = TerminalEventCanonical.utcTimestamp()
            val nonce = UUID.randomUUID().toString().replace("-", "")
            val signature = DeviceRequestSigner.sign(
                timestamp,
                nonce,
                event.payloadHash,
            )
            val request = Request.Builder()
                .url(url)
                .header(
                    "Authorization",
                    "Bearer ${AccessTokenMemory.requireFresh()}",
                )
                .header(
                    "X-EAY-Device-ID",
                    ManagedDeviceIdentity(applicationContext).requireDeviceId(),
                )
                .header("X-EAY-Request-Timestamp", timestamp)
                .header("X-EAY-Request-Nonce", nonce)
                .header("X-EAY-Device-Signature", signature)
                .post(
                    event.canonicalPayload.toRequestBody(
                        "application/json".toMediaType(),
                    ),
                )
                .build()

            val response = try {
                http.newCall(request).execute()
            } catch (_: IOException) {
                if (scheduleRetry(dao, event, "NETWORK_EXCEPTION")) {
                    return@withContext Result.retry()
                }
                continue
            }

            response.use {
                val body = it.body?.string().orEmpty()
                val json = runCatching { JSONObject(body) }.getOrNull()
                val accepted = json?.optBoolean("accepted")
                val replay = json?.optBoolean("idempotent_replay")
                val verdict = InventorySyncClassifier.classify(
                    it.code,
                    accepted,
                    replay,
                )
                when (verdict.outcome) {
                    SyncServerOutcome.COMMITTED,
                    SyncServerOutcome.EXACT_REPLAY,
                    -> dao.ack(event.eventId, verdict.code)

                    SyncServerOutcome.AUTH_REJECTED -> {
                        AccessTokenMemory.clear()
                        if (scheduleRetry(dao, event, verdict.code)) {
                            return@withContext Result.retry()
                        }
                    }

                    SyncServerOutcome.RETRYABLE_FAILURE -> {
                        if (scheduleRetry(dao, event, verdict.code)) {
                            return@withContext Result.retry()
                        }
                    }

                    SyncServerOutcome.DEVICE_REJECTED -> dao.quarantine(
                        event.eventId,
                        SyncQuarantineReason.DEVICE_REVOKED.name,
                        verdict.code,
                    )

                    SyncServerOutcome.POLICY_REJECTED -> dao.quarantine(
                        event.eventId,
                        SyncQuarantineReason.POLICY_REJECTED.name,
                        verdict.code,
                    )

                    SyncServerOutcome.BUSINESS_CONFLICT -> dao.quarantine(
                        event.eventId,
                        SyncQuarantineReason.BUSINESS_CONFLICT.name,
                        verdict.code,
                    )

                    SyncServerOutcome.PERMANENT_REJECTED -> dao.quarantine(
                        event.eventId,
                        SyncQuarantineReason.PERMANENT_REJECTED.name,
                        verdict.code,
                    )
                }
            }
        }
        if (dao.pendingCount() > 0) Result.retry() else Result.success()
    }

    private suspend fun scheduleRetry(
        dao: OfflineEventDao,
        event: OfflineEvent,
        serverCode: String,
    ): Boolean {
        val nextAttempts = event.attempts + 1
        if (nextAttempts >= RETRY_POLICY.maxAttempts) {
            dao.quarantine(
                event.eventId,
                SyncQuarantineReason.RETRY_EXHAUSTED.name,
                serverCode,
            )
            return false
        }
        val delay = RETRY_POLICY.delayAfterFailure(nextAttempts)
        dao.retry(
            event.eventId,
            System.currentTimeMillis() + delay,
            serverCode,
        )
        return true
    }

    private suspend fun ensureFreshAccessToken(session: AuthSession): Boolean {
        if (AccessTokenMemory.freshOrNull() != null) return true
        return TokenRefresh.refresh(applicationContext, session).isSuccess
    }

    companion object {
        private const val UNIQUE = "eay-inventory-sync-v2"
        private val RETRY_POLICY = SyncRetryPolicy(
            maxAttempts = 8,
            initialDelayMs = 2_000,
            maxDelayMs = 15 * 60_000,
        )

        fun enqueue(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = OneTimeWorkRequestBuilder<InventorySyncWorker>()
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                UNIQUE,
                ExistingWorkPolicy.KEEP,
                request,
            )
        }
    }
}
