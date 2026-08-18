package com.eay.mobile.core

object MobileTelemetryPolicy {
    private const val REDACTED = "[REDACTED]"

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
        "actor_id",
        "employee_id",
        "device_id",
        "installation_id",
        "location_id",
        "warehouse_id",
        "email",
        "phone",
        "name",
    )

    private val opaqueCorrelationKeys = setOf(
        "fleet_device_token",
        "fleet_site_token",
        "session_correlation_token",
        "release_id",
    )

    private val opaqueTokenPattern = Regex("^[A-Za-z0-9._:-]{16,128}$")

    fun sanitize(attributes: Map<String, String>): Map<String, String> =
        attributes.mapValues { (rawKey, value) ->
            val key = rawKey.trim().lowercase()
            when {
                key in forbiddenKeys -> REDACTED
                key in opaqueCorrelationKeys && !opaqueTokenPattern.matches(value) -> REDACTED
                else -> value.take(256)
            }
        }

    fun containsForbiddenRawData(attributes: Map<String, String>): Boolean =
        attributes.any { (rawKey, value) ->
            val key = rawKey.trim().lowercase()
            key in forbiddenKeys && value != REDACTED
        }
}
