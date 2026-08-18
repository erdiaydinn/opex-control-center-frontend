package com.eay.inventory

import android.content.Context
import com.eay.mobile.core.MobileRuntimeProfile
import okhttp3.Request
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.util.Locale

data class InventoryTerminalTaskWire(
    val missionId: String,
    val documentId: String,
    val activeShiftId: String,
    val warehouseId: String,
    val locationId: String,
    val name: String,
    val state: String,
    val revision: Int,
    val locationCount: Int,
    val claimStatus: String,
    val attemptId: String?,
    val leaseId: String?,
    val leaseValidUntil: String?,
    val operation: String,
    val runtimeProfile: String,
)

enum class InventoryTaskFetchCode {
    OK,
    AUTH_REQUIRED,
    POLICY_REJECTED,
    DEVICE_REJECTED,
    RETRYABLE,
    CONTRACT_REJECTED,
    PERMANENT_REJECTED,
}

data class InventoryTaskFetchResult(
    val code: InventoryTaskFetchCode,
    val tasks: List<InventoryTerminalCountTask> = emptyList(),
) {
    val accepted: Boolean get() = code == InventoryTaskFetchCode.OK
}

object InventoryTerminalTaskContract {
    private val forbiddenFieldNames = setOf(
        "expected_quantity",
        "expected_stock",
        "system_stock",
        "unit_cost",
        "variance",
        "variance_value",
        "sku",
        "skus",
        "products",
        "barcodes",
    )

    fun rejectForbiddenFieldNames(fieldNames: Set<String>) {
        val normalized = fieldNames.map { it.trim().lowercase(Locale.ROOT) }.toSet()
        require(normalized.intersect(forbiddenFieldNames).isEmpty()) {
            "Terminal task response leaked stock-truth fields"
        }
    }

    fun map(rows: List<InventoryTerminalTaskWire>): List<InventoryTerminalCountTask> {
        val missionIds = HashSet<String>()
        val locationBindings = HashSet<String>()
        return rows.map { row ->
            require(row.operation == "inventory.count") { "Unsupported terminal operation" }
            require(row.runtimeProfile == MobileRuntimeProfile.EAY_TERMINAL.name) {
                "Unsupported terminal runtime profile"
            }
            require(row.activeShiftId.matches(Regex("^[A-Za-z0-9._:-]{1,128}$"))) {
                "Missing or invalid server-issued active shift"
            }
            val claimStatus = InventoryMissionClaimStatus.valueOf(row.claimStatus)
            require(missionIds.add(row.missionId)) { "Duplicate terminal mission ID" }
            val binding = "${row.documentId}:${row.locationId.trim().uppercase(Locale.ROOT)}"
            require(locationBindings.add(binding)) { "Duplicate document/location mission" }
            InventoryTerminalCountTask(
                missionId = row.missionId,
                documentId = row.documentId,
                activeShiftId = row.activeShiftId,
                warehouseId = row.warehouseId,
                locationId = row.locationId,
                name = row.name,
                state = row.state,
                revision = row.revision,
                locationCount = row.locationCount,
                claimStatus = claimStatus,
                attemptId = row.attemptId,
                leaseId = row.leaseId,
                leaseValidUntil = row.leaseValidUntil,
                operation = row.operation,
                runtimeProfile = MobileRuntimeProfile.valueOf(row.runtimeProfile),
            )
        }
    }

    fun classifyHttp(httpCode: Int): InventoryTaskFetchCode = when {
        httpCode in 200..299 -> InventoryTaskFetchCode.OK
        httpCode == 401 -> InventoryTaskFetchCode.AUTH_REQUIRED
        httpCode == 403 -> InventoryTaskFetchCode.POLICY_REJECTED
        httpCode == 410 -> InventoryTaskFetchCode.DEVICE_REJECTED
        httpCode == 408 || httpCode == 429 || httpCode >= 500 -> InventoryTaskFetchCode.RETRYABLE
        else -> InventoryTaskFetchCode.PERMANENT_REJECTED
    }
}

/**
 * Read-only production COUNT-mission client. It deliberately reuses PinnedApi,
 * the in-memory OIDC access token and the MDM-provided device identity. There is
 * no anonymous fallback, secondary HTTP stack or client-owned permission truth.
 */
class InventoryTerminalTaskClient(context: Context) {
    private val appContext = context.applicationContext

    fun fetch(): InventoryTaskFetchResult {
        val token = AccessTokenMemory.freshOrNull()
            ?: return InventoryTaskFetchResult(InventoryTaskFetchCode.AUTH_REQUIRED)
        val deviceId = runCatching {
            ManagedDeviceIdentity(appContext).requireDeviceId()
        }.getOrElse {
            return InventoryTaskFetchResult(InventoryTaskFetchCode.DEVICE_REJECTED)
        }
        val request = Request.Builder()
            .url(BuildConfig.API_BASE_URL.trimEnd('/') + "/api/inventory/v1/terminal/tasks")
            .header("Authorization", "Bearer $token")
            .header("X-EAY-Device-ID", deviceId.toString())
            .get()
            .build()

        val response = try {
            PinnedApi.client.newCall(request).execute()
        } catch (_: IOException) {
            return InventoryTaskFetchResult(InventoryTaskFetchCode.RETRYABLE)
        }
        response.use {
            val classified = InventoryTerminalTaskContract.classifyHttp(it.code)
            if (classified != InventoryTaskFetchCode.OK) {
                if (classified == InventoryTaskFetchCode.AUTH_REQUIRED) AccessTokenMemory.clear()
                return InventoryTaskFetchResult(classified)
            }
            return try {
                InventoryTaskFetchResult(
                    code = InventoryTaskFetchCode.OK,
                    tasks = parseRows(it.body?.string().orEmpty()),
                )
            } catch (_: IllegalArgumentException) {
                InventoryTaskFetchResult(InventoryTaskFetchCode.CONTRACT_REJECTED)
            } catch (_: JSONException) {
                InventoryTaskFetchResult(InventoryTaskFetchCode.CONTRACT_REJECTED)
            }
        }
    }

    private fun parseRows(body: String): List<InventoryTerminalCountTask> {
        val root = JSONObject(body)
        val rows = root.getJSONArray("rows")
        val wireRows = ArrayList<InventoryTerminalTaskWire>(rows.length())
        for (index in 0 until rows.length()) {
            val row = rows.getJSONObject(index)
            val names = buildSet {
                val keys = row.keys()
                while (keys.hasNext()) add(keys.next())
            }
            InventoryTerminalTaskContract.rejectForbiddenFieldNames(names)
            wireRows += InventoryTerminalTaskWire(
                missionId = row.getString("mission_id"),
                documentId = row.getString("id"),
                activeShiftId = row.getString("active_shift_id"),
                warehouseId = row.getString("warehouse_id"),
                locationId = row.getString("location_id"),
                name = row.getString("name"),
                state = row.getString("state"),
                revision = row.getInt("revision"),
                locationCount = row.getInt("location_count"),
                claimStatus = row.getString("claim_status"),
                attemptId = nullableString(row, "attempt_id"),
                leaseId = nullableString(row, "lease_id"),
                leaseValidUntil = nullableString(row, "lease_valid_until"),
                operation = row.getString("operation"),
                runtimeProfile = row.getString("runtime_profile"),
            )
        }
        return InventoryTerminalTaskContract.map(wireRows)
    }

    private fun nullableString(row: JSONObject, key: String): String? {
        if (!row.has(key) || row.isNull(key)) return null
        return row.getString(key).takeIf { it.isNotBlank() }
    }
}
