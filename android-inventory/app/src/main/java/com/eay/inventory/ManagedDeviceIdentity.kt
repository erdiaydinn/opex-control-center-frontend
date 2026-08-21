package com.eay.inventory

import android.content.Context
import android.content.RestrictionsManager
import java.util.UUID

class ManagedDeviceIdentity(context: Context) {
    private val restrictions = context.getSystemService(RestrictionsManager::class.java).applicationRestrictions

    fun requireDeviceId(): UUID {
        val raw = restrictions.getString("eay_device_id").orEmpty()
        return runCatching { UUID.fromString(raw) }
            .getOrElse { throw IllegalStateException("MDM eay_device_id eksik veya geçersiz") }
    }

    fun requireEnrollmentCode(): String = restrictions.getString("eay_enrollment_code").orEmpty()
        .takeIf { it.length >= 32 } ?: throw IllegalStateException("Tek kullanımlık MDM enrollment code eksik")
}
