package com.eay.mobile.core

import java.nio.charset.StandardCharsets
import java.security.MessageDigest

data class MobileEventEnvelope(
    val eventId: String,
    val tenantId: String,
    val actorId: String,
    val deviceId: String,
    val installationId: String,
    val authBindingId: String,
    val missionId: String?,
    val operation: String,
    val deviceSequence: Long,
    val occurredAt: String,
    val payloadHash: String,
    val previousLedgerHash: String?,
    val policyFingerprint: String,
    val appVersion: String,
) {
    fun proofMaterial(): String = listOf(
        eventId.lowercase(),
        tenantId,
        actorId,
        deviceId,
        installationId,
        authBindingId,
        missionId.orEmpty(),
        operation,
        deviceSequence.toString(),
        occurredAt,
        payloadHash.lowercase(),
        previousLedgerHash.orEmpty().lowercase(),
        policyFingerprint.lowercase(),
        appVersion,
    ).joinToString("|") { lengthPrefix(it) }

    fun ledgerHash(): String = sha256(proofMaterial())

    fun isStructurallyValid(): Boolean =
        eventId.isNotBlank() && tenantId.isNotBlank() && actorId.isNotBlank() &&
            deviceId.isNotBlank() && installationId.isNotBlank() && authBindingId.isNotBlank() &&
            operation.isNotBlank() && deviceSequence > 0 && occurredAt.isNotBlank() &&
            payloadHash.matches(Regex("^[a-fA-F0-9]{64}$")) &&
            policyFingerprint.matches(Regex("^[a-fA-F0-9]{64}$"))

    private fun lengthPrefix(value: String): String {
        val size = value.toByteArray(StandardCharsets.UTF_8).size
        return "$size:$value"
    }
}

enum class ReplayDisposition {
    NEW,
    EXACT_REPLAY,
    PAYLOAD_SUBSTITUTION,
    SEQUENCE_COLLISION,
    CHAIN_MISMATCH,
}

object MobileLedgerGuard {
    fun compare(existing: MobileEventEnvelope?, incoming: MobileEventEnvelope): ReplayDisposition {
        if (existing == null) return ReplayDisposition.NEW
        if (existing.eventId == incoming.eventId) {
            return if (
                existing.deviceSequence == incoming.deviceSequence &&
                existing.payloadHash.equals(incoming.payloadHash, ignoreCase = true) &&
                existing.ledgerHash() == incoming.ledgerHash()
            ) ReplayDisposition.EXACT_REPLAY else ReplayDisposition.PAYLOAD_SUBSTITUTION
        }
        if (existing.deviceId == incoming.deviceId && existing.deviceSequence == incoming.deviceSequence) {
            return ReplayDisposition.SEQUENCE_COLLISION
        }
        return ReplayDisposition.NEW
    }

    fun verifyChain(expectedPreviousHash: String?, incoming: MobileEventEnvelope): ReplayDisposition {
        val expected = expectedPreviousHash.orEmpty().lowercase()
        val actual = incoming.previousLedgerHash.orEmpty().lowercase()
        return if (expected == actual) ReplayDisposition.NEW else ReplayDisposition.CHAIN_MISMATCH
    }
}

fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
    .digest(value.toByteArray(StandardCharsets.UTF_8))
    .joinToString("") { "%02x".format(it) }
