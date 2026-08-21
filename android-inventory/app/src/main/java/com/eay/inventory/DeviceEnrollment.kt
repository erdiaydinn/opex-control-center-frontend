package com.eay.inventory

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

object DeviceEnrollment {
    private val io = Executors.newSingleThreadExecutor()

    fun enroll(context: Context, done: (Result<Unit>) -> Unit) = io.execute {
        val result = runCatching {
            val managed = ManagedDeviceIdentity(context)
            val deviceId = managed.requireDeviceId()
            val body = JSONObject()
                .put("activation_code", managed.requireEnrollmentCode())
                .put("public_key_pem", DeviceRequestSigner.publicKeyPem())
                .toString()
            val request = Request.Builder()
                .url("${BuildConfig.API_BASE_URL.trimEnd('/')}/api/inventory/v1/devices/enroll")
                .header("Authorization", "Bearer ${AccessTokenMemory.requireFresh()}")
                .header("X-EAY-Device-ID", deviceId.toString())
                .post(body.toRequestBody("application/json".toMediaType()))
                .build()
            PinnedApi.client.newCall(request).execute().use { response ->
                check(response.isSuccessful) { "enrollment HTTP ${response.code}" }
            }
            scheduleSync(context)
        }
        done(result)
    }

    private fun scheduleSync(context: Context) {
        val constraints = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
        val request = PeriodicWorkRequestBuilder<InventorySyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            "eay-inventory-sync",
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }
}
