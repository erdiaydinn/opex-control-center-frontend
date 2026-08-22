package com.eay.inventory

import android.content.Context
import com.eay.mobile.core.OperationalMissionDefinition
import com.eay.mobile.core.OperationalMissionType
import com.eay.mobile.core.OperationalStepEvidence
import com.eay.mobile.core.OperationalStepKind
import com.eay.mobile.core.OperationalValueCanonicalizer
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.time.Duration
import java.time.Instant
import java.time.OffsetDateTime
import java.util.Locale
import java.util.UUID

enum class InventoryMissionPriority { LOW, NORMAL, HIGH, URGENT }

data class InventoryOperationalTask(
    val missionId: String,
    val activeShiftId: String,
    val warehouseId: String,
    val missionType: OperationalMissionType,
    val operation: String,
    val externalReference: String,
    val state: String,
    val steps: List<OperationalStepKind>,
    val completedSteps: Int,
    val totalSteps: Int,
    val nextStep: OperationalStepKind,
    val claimStatus: String,
    val priority: InventoryMissionPriority = InventoryMissionPriority.NORMAL,
    val dueAt: String? = null,
    val estimatedSeconds: Int? = null,
    val skuId: String,
    val plannedQuantity: String,
    val sourceLocationId: String?,
    val destinationLocationId: String?,
    val containerId: String?,
    val allowedConditions: List<String>,
) {
    fun deadlineMinutes(now: Instant = Instant.now()): Int? {
        val deadline = dueAt?.let { OffsetDateTime.parse(it).toInstant() } ?: return null
        val seconds = Duration.between(now, deadline).seconds
        return when {
            seconds > 0L -> ((seconds + 59L) / 60L).toInt()
            seconds < 0L -> -(((-seconds) + 59L) / 60L).toInt()
            else -> 0
        }
    }

    fun estimatedMinutes(): Int? = estimatedSeconds?.let { (it + 59) / 60 }
}

data class InventoryOperationalTaskFetchResult(
    val code: InventoryTaskFetchCode,
    val tasks: List<InventoryOperationalTask> = emptyList(),
) {
    val accepted: Boolean get() = code == InventoryTaskFetchCode.OK
}

data class InventoryOperationalClaim(
    val missionId: String,
    val claimId: String,
    val activeShiftId: String,
    val nextStep: OperationalStepKind,
    val resumeEvidence: List<OperationalStepEvidence> = emptyList(),
)

data class InventoryOperationalClaimResult(
    val code: InventoryTaskFetchCode,
    val claim: InventoryOperationalClaim? = null,
) {
    val accepted: Boolean get() = code == InventoryTaskFetchCode.OK && claim != null
}

object InventoryOperationalTaskContract {
    private val forbidden = setOf("item_value_hash", "item_barcode", "result_hash", "payload_hash")

    fun rejectForbiddenFields(names: Set<String>) {
        require(names.map { it.trim().lowercase() }.intersect(forbidden).isEmpty()) {
            "Operational task response leaked execution-only fields"
        }
    }

    fun validate(task: InventoryOperationalTask): InventoryOperationalTask {
        val canonical = when (task.missionType) {
            OperationalMissionType.PICKING -> OperationalMissionDefinition.picking(task.missionId)
            OperationalMissionType.PUTAWAY -> OperationalMissionDefinition.putaway(task.missionId)
            OperationalMissionType.RECEIVING -> OperationalMissionDefinition.receiving(task.missionId)
            OperationalMissionType.TRANSFER -> OperationalMissionDefinition.transfer(task.missionId)
        }
        require(task.operation == canonical.operation)
        require(task.steps == canonical.steps)
        require(task.totalSteps == task.steps.size)
        require(task.completedSteps in 0 until task.totalSteps)
        require(task.nextStep == task.steps[task.completedSteps])
        require(task.activeShiftId.matches(Regex("^[A-Za-z0-9._:-]{1,128}$")))
        require(task.warehouseId.isNotBlank())
        require(task.state in setOf("OPEN", "CLAIMED"))
        require(task.claimStatus in setOf("AVAILABLE", "RESUMABLE"))
        require(task.skuId.isNotBlank())
        require(task.externalReference.isNotBlank())
        task.dueAt?.let { OffsetDateTime.parse(it) }
        task.estimatedSeconds?.let { require(it in 1..86_400) }
        OperationalValueCanonicalizer.normalize(OperationalStepKind.QUANTITY, task.plannedQuantity)

        if (OperationalStepKind.SOURCE_LOCATION in task.steps) {
            require(!task.sourceLocationId.isNullOrBlank()) { "Missing server-frozen source location" }
        }
        if (OperationalStepKind.DESTINATION_LOCATION in task.steps) {
            require(!task.destinationLocationId.isNullOrBlank()) { "Missing server-frozen destination location" }
        }
        if (OperationalStepKind.CONTAINER in task.steps) {
            require(!task.containerId.isNullOrBlank()) { "Missing server-frozen container" }
        }

        val normalizedConditions = task.allowedConditions.map { value ->
            OperationalValueCanonicalizer.normalize(OperationalStepKind.CONDITION, value)
        }
        require(normalizedConditions.distinct().size == normalizedConditions.size) {
            "Duplicate operational condition"
        }
        if (OperationalStepKind.CONDITION in task.steps) {
            require(normalizedConditions.isNotEmpty()) { "Missing server-frozen condition choices" }
        } else {
            require(normalizedConditions.isEmpty()) { "Unexpected condition choices for mission type" }
        }
        return task
    }
}

/** Cross-language claim proof contract matching backend operational_claim_hash. */
object InventoryOperationalClaimContract {
    fun hash(missionId: String, activeShiftId: String): String {
        val mission = UUID.fromString(missionId.trim()).toString()
        val shift = activeShiftId.trim()
        require(shift.matches(Regex("^[A-Za-z0-9._:-]{1,128}$")))
        val canonical = buildString {
            append('{')
            append("\"active_shift_id\":").append(JSONObject.quote(shift)).append(',')
            append("\"mission_id\":").append(JSONObject.quote(mission))
            append('}')
        }
        return MessageDigest.getInstance("SHA-256")
            .digest(canonical.toByteArray(StandardCharsets.UTF_8))
            .joinToString("") { "%02x".format(Locale.ROOT, it) }
    }
}

class InventoryOperationalTaskClient(context: Context) {
    private val appContext = context.applicationContext

    fun fetch(): InventoryOperationalTaskFetchResult {
        val token = AccessTokenMemory.freshOrNull()
            ?: return InventoryOperationalTaskFetchResult(InventoryTaskFetchCode.AUTH_REQUIRED)
        val deviceId = runCatching { ManagedDeviceIdentity(appContext).requireDeviceId() }.getOrElse {
            return InventoryOperationalTaskFetchResult(InventoryTaskFetchCode.DEVICE_REJECTED)
        }
        val request = Request.Builder()
            .url(BuildConfig.API_BASE_URL.trimEnd('/') + "/api/inventory/v1/mobile/operational-missions")
            .header("Authorization", "Bearer $token")
            .header("X-EAY-Device-ID", deviceId.toString())
            .get()
            .build()
        val response = try {
            PinnedApi.client.newCall(request).execute()
        } catch (_: IOException) {
            return InventoryOperationalTaskFetchResult(InventoryTaskFetchCode.RETRYABLE)
        }
        response.use {
            val code = InventoryTerminalTaskContract.classifyHttp(it.code)
            if (code != InventoryTaskFetchCode.OK) {
                if (code == InventoryTaskFetchCode.AUTH_REQUIRED) AccessTokenMemory.clear()
                return InventoryOperationalTaskFetchResult(code)
            }
            return try {
                InventoryOperationalTaskFetchResult(
                    InventoryTaskFetchCode.OK,
                    parseRows(it.body?.string().orEmpty()),
                )
            } catch (_: IllegalArgumentException) {
                InventoryOperationalTaskFetchResult(InventoryTaskFetchCode.CONTRACT_REJECTED)
            } catch (_: JSONException) {
                InventoryOperationalTaskFetchResult(InventoryTaskFetchCode.CONTRACT_REJECTED)
            }
        }
    }

    private fun parseRows(body: String): List<InventoryOperationalTask> {
        val rows = JSONObject(body).getJSONArray("rows")
        val missionIds = HashSet<String>()
        return buildList(rows.length()) {
            for (index in 0 until rows.length()) {
                val row = rows.getJSONObject(index)
                val names = buildSet {
                    val keys = row.keys()
                    while (keys.hasNext()) add(keys.next())
                }
                InventoryOperationalTaskContract.rejectForbiddenFields(names)
                val type = OperationalMissionType.valueOf(row.getString("mission_type"))
                val steps = parseSteps(row.getJSONArray("steps"))
                val missionId = UUID.fromString(row.getString("mission_id")).toString()
                require(missionIds.add(missionId)) { "Duplicate operational mission ID" }
                add(
                    InventoryOperationalTaskContract.validate(
                        InventoryOperationalTask(
                            missionId = missionId,
                            activeShiftId = row.getString("active_shift_id"),
                            warehouseId = row.getString("warehouse_id"),
                            missionType = type,
                            operation = row.getString("operation"),
                            externalReference = row.getString("external_reference"),
                            state = row.getString("state"),
                            steps = steps,
                            completedSteps = row.getInt("completed_steps"),
                            totalSteps = row.getInt("total_steps"),
                            nextStep = OperationalStepKind.valueOf(row.getString("next_step")),
                            claimStatus = row.getString("claim_status"),
                            priority = InventoryMissionPriority.valueOf(row.optString("priority", "NORMAL")),
                            dueAt = nullableString(row, "due_at"),
                            estimatedSeconds = nullableInt(row, "estimated_seconds"),
                            skuId = row.getString("sku_id"),
                            plannedQuantity = row.getString("planned_quantity"),
                            sourceLocationId = nullableString(row, "source_location_id"),
                            destinationLocationId = nullableString(row, "destination_location_id"),
                            containerId = nullableString(row, "container_id"),
                            allowedConditions = parseStrings(row.getJSONArray("allowed_conditions")),
                        ),
                    ),
                )
            }
        }
    }

    private fun parseSteps(values: JSONArray): List<OperationalStepKind> = buildList(values.length()) {
        for (index in 0 until values.length()) add(OperationalStepKind.valueOf(values.getString(index)))
    }

    private fun parseStrings(values: JSONArray): List<String> = buildList(values.length()) {
        for (index in 0 until values.length()) add(values.getString(index))
    }

    private fun nullableString(row: JSONObject, key: String): String? =
        if (!row.has(key) || row.isNull(key)) null else row.getString(key).takeIf { it.isNotBlank() }

    private fun nullableInt(row: JSONObject, key: String): Int? =
        if (!row.has(key) || row.isNull(key)) null else row.getInt(key)
}

class InventoryOperationalClaimClient(context: Context) {
    private val appContext = context.applicationContext

    fun claim(task: InventoryOperationalTask): InventoryOperationalClaimResult {
        val token = AccessTokenMemory.freshOrNull()
            ?: return InventoryOperationalClaimResult(InventoryTaskFetchCode.AUTH_REQUIRED)
        val deviceId = runCatching { ManagedDeviceIdentity(appContext).requireDeviceId() }.getOrElse {
            return InventoryOperationalClaimResult(InventoryTaskFetchCode.DEVICE_REJECTED)
        }
        val commandHash = runCatching {
            InventoryOperationalClaimContract.hash(task.missionId, task.activeShiftId)
        }.getOrElse {
            return InventoryOperationalClaimResult(InventoryTaskFetchCode.CONTRACT_REJECTED)
        }
        val timestamp = Instant.now().toString()
        val nonce = UUID.randomUUID().toString()
        val proof = "$deviceId\n$timestamp\n$nonce\n$commandHash".toByteArray(Charsets.UTF_8)
        val signature = runCatching { DeviceRequestSigner.sign(proof) }.getOrElse {
            return InventoryOperationalClaimResult(InventoryTaskFetchCode.DEVICE_REJECTED)
        }
        val request = Request.Builder()
            .url(BuildConfig.API_BASE_URL.trimEnd('/') + "/api/inventory/v1/mobile/operational-missions/${task.missionId}/claim")
            .header("Authorization", "Bearer $token")
            .header("X-EAY-Device-ID", deviceId.toString())
            .header("X-EAY-Request-Timestamp", timestamp)
            .header("X-EAY-Request-Nonce", nonce)
            .header("X-EAY-Device-Signature", signature)
            .post("{}".toRequestBody("application/json".toMediaType()))
            .build()
        val response = try {
            PinnedApi.client.newCall(request).execute()
        } catch (_: IOException) {
            return InventoryOperationalClaimResult(InventoryTaskFetchCode.RETRYABLE)
        }
        response.use {
            val code = InventoryTerminalTaskContract.classifyHttp(it.code)
            if (code != InventoryTaskFetchCode.OK) {
                if (code == InventoryTaskFetchCode.AUTH_REQUIRED) AccessTokenMemory.clear()
                return InventoryOperationalClaimResult(code)
            }
            return try {
                val json = JSONObject(it.body?.string().orEmpty())
                val missionId = UUID.fromString(json.getString("mission_id")).toString()
                val claimId = UUID.fromString(json.getString("claim_id")).toString()
                val shiftId = json.getString("active_shift_id")
                val next = OperationalStepKind.valueOf(json.getString("next_step"))
                require(missionId == task.missionId)
                require(shiftId == task.activeShiftId)
                require(next == task.nextStep)
                attachLocalResume(
                    task,
                    InventoryOperationalClaim(missionId, claimId, shiftId, next),
                )
            } catch (_: Exception) {
                InventoryOperationalClaimResult(InventoryTaskFetchCode.CONTRACT_REJECTED)
            }
        }
    }

    private fun attachLocalResume(
        task: InventoryOperationalTask,
        claim: InventoryOperationalClaim,
    ): InventoryOperationalClaimResult {
        val projection = runCatching {
            runBlocking {
                val database = InventoryDatabase.get(appContext)
                val session = database.sessions().get()
                    ?: error("Missing durable auth session for operational execution")
                val unsettled = database.events().unsettledBefore(Long.MAX_VALUE)
                InventoryOperationalLocalTruth.project(
                    task = task,
                    unsettledEvents = unsettled,
                    currentAuthBindingId = session.authBindingId,
                    expectedClaimId = claim.claimId,
                )
            }
        }.getOrElse {
            InventorySyncWorker.enqueue(appContext)
            return InventoryOperationalClaimResult(InventoryTaskFetchCode.CONTRACT_REJECTED)
        }

        return when (projection.state) {
            InventoryLocalCompletionState.OPEN -> InventoryOperationalClaimResult(
                code = InventoryTaskFetchCode.OK,
                claim = claim.copy(resumeEvidence = projection.evidence),
            )
            InventoryLocalCompletionState.AWAITING_SERVER -> {
                InventorySyncWorker.enqueue(appContext)
                InventoryOperationalClaimResult(InventoryTaskFetchCode.RETRYABLE)
            }
            InventoryLocalCompletionState.REQUIRES_REVIEW -> {
                InventorySyncWorker.enqueue(appContext)
                InventoryOperationalClaimResult(InventoryTaskFetchCode.CONTRACT_REJECTED)
            }
        }
    }
}
