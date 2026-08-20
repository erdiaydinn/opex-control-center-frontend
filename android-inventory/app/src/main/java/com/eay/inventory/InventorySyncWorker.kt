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
import okhttp3.FormBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.time.Instant
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

object InventorySyncContract {
    private const val COUNT_LINE_PATH = "/api/inventory/v1/terminal/events"
    private const val LOCATION_COMPLETE_PATH = "/api/inventory/v1/terminal/location-completions"

    fun endpointPath(canonicalPayload: String): String? = runCatching {
        val json = JSONObject(canonicalPayload)
        when (json.optString("event_kind")) {
            "" -> COUNT_LINE_PATH
            "LOCATION_COMPLETE" -> LOCATION_COMPLETE_PATH
            else -> null
        }
    }.getOrNull()

    fun isLocationCompletion(canonicalPayload: String): Boolean = runCatching {
        JSONObject(canonicalPayload).optString("event_kind") == "LOCATION_COMPLETE"
    }.getOrDefault(false)

    fun responseMatchesSignedShift(
        canonicalPayload: String,
        serverShiftId: String?,
    ): Boolean {
        val normalizedServerShift = serverShiftId?.trim().orEmpty()
        if (normalizedServerShift.isBlank()) return false
        return runCatching {
            JSONObject(canonicalPayload)
                .getString("active_shift_id")
                .trim() == normalizedServerShift
        }.getOrDefault(false)
    }

    fun responseMatchesSignedMission(
        canonicalPayload: String,
        serverShiftId: String?,
        serverAttemptId: String?,
        serverLeaseId: String?,
    ): Boolean {
        val shift = serverShiftId?.trim().orEmpty()
        val attempt = serverAttemptId?.trim().orEmpty()
        val lease = serverLeaseId?.trim().orEmpty()
        if (shift.isBlank() || attempt.isBlank() || lease.isBlank()) return false
        return runCatching {
            val payload = JSONObject(canonicalPayload)
            payload.getString("active_shift_id").trim() == shift &&
                UUID.fromString(payload.getString("attempt_id").trim()).toString() ==
                UUID.fromString(attempt).toString() &&
                UUID.fromString(payload.getString("lease_id").trim()).toString() ==
                UUID.fromString(lease).toString()
        }.getOrDefault(false)
    }
}

class InventorySyncWorker(
    context: Context,
    parameters: WorkerParameters,
) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val db = InventoryDatabase.get(applicationContext)
        val dao = db.events()
        val deviceId = runCatching {
            ManagedDeviceIdentity(applicationContext).requireDeviceId()
        }.getOrElse { return@withContext Result.failure() }
        val session = db.sessions().get() ?: return@withContext Result.failure()
        if (session.authBindingId.isBlank()) return@withContext Result.failure()

        if (AccessTokenMemory.freshOrNull() == null && refreshAccessToken(session) == null) {
            return@withContext Result.retry()
        }

        // Quarantined business evidence is not a dead end and does not require an
        // operator to press a mutation button. Route only the explicitly recoverable
        // reasons through the signed server-side maker-checker case flow. Security,
        // device and integrity quarantines never enter this loop.
        if (!routeSupervisorRecovery(dao)) {
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
            val endpointPath = InventorySyncContract.endpointPath(event.canonicalPayload)
            if (endpointPath == null) {
                dao.quarantine(
                    event.eventId,
                    SyncQuarantineReason.CORRUPT_EVENT.name,
                    "UNSUPPORTED_EVENT_KIND",
                )
                continue
            }
            if (InventorySyncContract.isLocationCompletion(event.canonicalPayload)) {
                when (
                    InventoryLocationCompletionDependency.evaluate(
                        event,
                        dao.unsettledBefore(event.deviceSequence),
                    )
                ) {
                    LocationCompletionDependencyDecision.CLEAR -> Unit
                    LocationCompletionDependencyDecision.WAIT ->
                        return@withContext Result.retry()
                    LocationCompletionDependencyDecision.BLOCKED -> {
                        dao.quarantine(
                            event.eventId,
                            SyncQuarantineReason.DEPENDENCY_BLOCKED.name,
                            "LOCATION_COUNT_DEPENDENCY_BLOCKED",
                        )
                        continue
                    }
                }
            }

            val timestamp = Instant.now().toString()
            val nonce = UUID.randomUUID().toString()
            val proof = "$deviceId\n$timestamp\n$nonce\n${event.payloadHash}"
                .toByteArray(Charsets.UTF_8)
            val signature = DeviceRequestSigner.sign(proof)
            val requestBody = JSONObject(event.canonicalPayload)
                .put("payload_hash", event.payloadHash)
                .toString()
            val request = Request.Builder()
                .url(BuildConfig.API_BASE_URL.trimEnd('/') + endpointPath)
                .header(
                    "Authorization",
                    "Bearer ${AccessTokenMemory.requireFresh()}",
                )
                .header("X-EAY-Device-ID", deviceId.toString())
                .header("X-EAY-Request-Timestamp", timestamp)
                .header("X-EAY-Request-Nonce", nonce)
                .header("X-EAY-Device-Signature", signature)
                .post(
                    requestBody.toRequestBody(
                        "application/json".toMediaType(),
                    ),
                )
                .build()

            val response = try {
                PinnedApi.client.newCall(request).execute()
            } catch (_: IOException) {
                if (scheduleRetry(dao, event, "NETWORK_EXCEPTION")) {
                    return@withContext Result.retry()
                }
                null
            }
            if (response == null) continue

            response.use {
                val body = it.body?.string().orEmpty()
                val json = runCatching { JSONObject(body) }.getOrNull()
                val accepted = json?.optBoolean("accepted")
                val replay = json?.optBoolean("idempotent_replay")
                if (
                    it.code in 200..299 &&
                    accepted == true &&
                    !InventorySyncContract.responseMatchesSignedMission(
                        event.canonicalPayload,
                        json?.optString("active_shift_id")?.takeIf { value -> value.isNotBlank() },
                        json?.optString("attempt_id")?.takeIf { value -> value.isNotBlank() },
                        json?.optString("lease_id")?.takeIf { value -> value.isNotBlank() },
                    )
                ) {
                    dao.quarantine(
                        event.eventId,
                        SyncQuarantineReason.SERVER_CONTRACT_MISMATCH.name,
                        "MISSION_ATTESTATION_MISMATCH",
                    )
                    return@use
                }
                if (
                    it.code in 200..299 &&
                    accepted == true &&
                    endpointPath == "/api/inventory/v1/terminal/events" &&
                    ServerFrozenSkuIdentity.verify(json ?: JSONObject(), event.canonicalPayload) == null
                ) {
                    dao.quarantine(
                        event.eventId,
                        SyncQuarantineReason.SERVER_CONTRACT_MISMATCH.name,
                        "SKU_IDENTITY_SNAPSHOT_MISMATCH",
                    )
                    return@use
                }
                val verdict = InventorySyncClassifier.classify(
                    it.code,
                    accepted,
                    replay,
                )
                when (verdict.outcome) {
                    SyncServerOutcome.COMMITTED,
                    SyncServerOutcome.EXACT_REPLAY,
                    -> dao.acknowledgeWithCode(event.eventId, verdict.code)

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

        // Route any business quarantine created by this pass before declaring the
        // work settled. A transient recovery-service failure retries WorkManager;
        // immutable evidence remains quarantined throughout.
        if (!routeSupervisorRecovery(dao)) {
            return@withContext Result.retry()
        }
        if (dao.pendingCount() > 0) Result.retry() else Result.success()
    }

    private suspend fun routeSupervisorRecovery(dao: OfflineEventDao): Boolean {
        val client = InventoryRecoveryCaseClient(applicationContext)
        for (event in dao.recoveryCandidates()) {
            val recovery = InventoryRecoveryContract.classify(event) ?: continue
            if (recovery.intent != InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW) {
                continue
            }
            when (val result = client.requestReview(event)) {
                is InventoryRecoveryCaseResult -> when {
                    result.accepted -> {
                        val caseId = requireNotNull(result.caseId)
                        val changed = dao.markRecoveryRequested(event.eventId, caseId)
                        if (changed != 1) {
                            // Never silently attach a case to evidence that changed under us.
                            dao.quarantine(
                                event.eventId,
                                SyncQuarantineReason.CORRUPT_EVENT.name,
                                "RECOVERY_METADATA_RACE",
                            )
                        }
                    }

                    result.code == InventoryRecoveryCaseCode.AUTH_REQUIRED ||
                        result.code == InventoryRecoveryCaseCode.RETRYABLE -> return false

                    result.code == InventoryRecoveryCaseCode.DEVICE_REJECTED -> dao.quarantine(
                        event.eventId,
                        SyncQuarantineReason.DEVICE_REVOKED.name,
                        "RECOVERY_DEVICE_REJECTED",
                    )

                    result.code == InventoryRecoveryCaseCode.POLICY_REJECTED -> dao.quarantine(
                        event.eventId,
                        SyncQuarantineReason.POLICY_REJECTED.name,
                        "RECOVERY_POLICY_REJECTED",
                    )

                    result.code == InventoryRecoveryCaseCode.NOT_ELIGIBLE -> dao.quarantine(
                        event.eventId,
                        SyncQuarantineReason.CORRUPT_EVENT.name,
                        "RECOVERY_NOT_ELIGIBLE",
                    )

                    else -> dao.quarantine(
                        event.eventId,
                        SyncQuarantineReason.SERVER_CONTRACT_MISMATCH.name,
                        "RECOVERY_${result.code.name}",
                    )
                }
            }
        }
        return true
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
        dao.retryWithCode(
            event.eventId,
            System.currentTimeMillis() + delay,
            serverCode,
        )
        return true
    }

    private suspend fun refreshAccessToken(session: AuthSession): String? {
        if (
            session.authBindingId.isBlank() ||
            !session.tokenEndpoint.startsWith("https://")
        ) {
            return null
        }
        val request = Request.Builder()
            .url(session.tokenEndpoint)
            .post(
                FormBody.Builder()
                    .add("grant_type", "refresh_token")
                    .add("refresh_token", session.refreshToken)
                    .add("client_id", session.clientId)
                    .build(),
            )
            .build()
        return runCatching {
            PinnedApi.client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return@use null
                val body = JSONObject(response.body?.string().orEmpty())
                val token = body.optString("access_token")
                    .takeIf { it.isNotBlank() }
                    ?: return@use null
                val expiresAt = System.currentTimeMillis() +
                    body.optLong("expires_in", 300L) * 1_000
                val rotated = body.optString("refresh_token")
                    .takeIf { it.isNotBlank() }
                if (rotated != null) {
                    InventoryDatabase.get(applicationContext)
                        .sessions()
                        .put(session.copy(refreshToken = rotated))
                }
                AccessTokenMemory.replace(token, expiresAt)
                token
            }
        }.getOrNull()
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
