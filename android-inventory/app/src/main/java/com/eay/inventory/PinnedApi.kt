package com.eay.inventory

import okhttp3.CertificatePinner
import okhttp3.OkHttpClient
import java.net.URI
import java.util.concurrent.TimeUnit

object PinnedApi {
    val client: OkHttpClient by lazy {
        val host = URI(BuildConfig.API_BASE_URL).host ?: throw IllegalStateException("Managed API host invalid")
        require(BuildConfig.API_BASE_URL.startsWith("https://")) { "HTTPS required" }
        require(BuildConfig.TLS_PIN_PRIMARY != BuildConfig.TLS_PIN_BACKUP) { "TLS pin rotation pair required" }
        OkHttpClient.Builder()
            .certificatePinner(CertificatePinner.Builder()
                .add(host, BuildConfig.TLS_PIN_PRIMARY)
                .add(host, BuildConfig.TLS_PIN_BACKUP)
                .build())
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .retryOnConnectionFailure(false)
            .build()
    }
}
