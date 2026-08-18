package com.eay.mobile.core

object MobileTelemetryPolicy {
    private val forbiddenKeys = setOf(
        "authorization",
        "access_token",
        "refresh_token",
        "id_token",
        "password",
        "client_secret",
        "signature",
        "canonical_payload",
        "payload",
        "barcode",
        "raw_barcode",
        "national_id",
        "tc",
        "biometric",
        "biometric_template",
        "precise_location",
        "latitude",
        "longitude",
    )

    private val fingerprintKeys = setOf("actor_id", "employee_id", "device_id", "installation_id")

    fun sanitize(attributes: Map<String, String>): Map<String, String> = attributes.mapValues { (rawKey, value) ->
        val key = rawKey.trim().lowercase()
        when {
            key in forbiddenKeys -> "[REDACTED]"
            key in fingerprintKeys -> "sha256:${sha256(value)}"
            else -> value.take(256)
        }
    }

    fun containsForbiddenRawData(attributes: Map<String, String>): Boolean = attributes.any { (rawKey, value) ->
        val key = rawKey.trim().lowercase()
        key in forbiddenKeys && value != "[REDACTED]"
    }
}
