package com.eay.mobile.core

enum class ScannerSource {
    HARDWARE_DATAWEDGE,
    CAMERA,
    MANUAL,
}

enum class BarcodeSymbology {
    EAN8,
    EAN13,
    UPCA,
    CODE128,
    GS1_128,
    QR,
    DATAMATRIX,
    UNKNOWN,
}

data class ScannerIngress(
    val sourceEventId: String,
    val source: ScannerSource,
    val symbology: BarcodeSymbology,
    val rawValue: String,
    val capturedAtEpochMs: Long,
)

data class ScannerPolicy(
    val allowedSources: Set<ScannerSource>,
    val allowedSymbologies: Set<BarcodeSymbology>,
    val maxPayloadBytes: Int = 512,
    val maxAgeMs: Long = 30_000,
    val maxFutureSkewMs: Long = 2_000,
) {
    init {
        require(allowedSources.isNotEmpty())
        require(allowedSymbologies.isNotEmpty())
        require(maxPayloadBytes in 1..4096)
        require(maxAgeMs > 0)
        require(maxFutureSkewMs >= 0)
    }
}

enum class ScannerAdmissionCode {
    ACCEPT,
    DENY_EVENT_ID,
    DENY_SOURCE,
    DENY_SYMBOLOGY,
    DENY_EMPTY,
    DENY_OVERSIZE,
    DENY_CONTROL_CHARACTER,
    DENY_STALE,
    DENY_FUTURE,
}

data class AcceptedScan(
    val sourceEventId: String,
    val source: ScannerSource,
    val symbology: BarcodeSymbology,
    val value: String,
    val payloadHash: String,
    val capturedAtEpochMs: Long,
)

data class ScannerAdmission(
    val code: ScannerAdmissionCode,
    val scan: AcceptedScan? = null,
) {
    val accepted: Boolean get() = code == ScannerAdmissionCode.ACCEPT
}

enum class ScannerReplayDisposition {
    NEW,
    EXACT_REPLAY,
    EVENT_ID_PAYLOAD_SUBSTITUTION,
}

object ScannerIngressGuard {
    private val eventIdPattern = Regex("^[A-Za-z0-9._:-]{1,128}$")

    fun evaluate(
        ingress: ScannerIngress,
        policy: ScannerPolicy,
        nowEpochMs: Long,
    ): ScannerAdmission {
        if (!eventIdPattern.matches(ingress.sourceEventId)) {
            return denied(ScannerAdmissionCode.DENY_EVENT_ID)
        }
        if (ingress.source !in policy.allowedSources) {
            return denied(ScannerAdmissionCode.DENY_SOURCE)
        }
        if (ingress.symbology !in policy.allowedSymbologies) {
            return denied(ScannerAdmissionCode.DENY_SYMBOLOGY)
        }

        val normalized = normalizePayload(ingress.rawValue)
        if (normalized.isEmpty()) {
            return denied(ScannerAdmissionCode.DENY_EMPTY)
        }
        if (normalized.toByteArray(Charsets.UTF_8).size > policy.maxPayloadBytes) {
            return denied(ScannerAdmissionCode.DENY_OVERSIZE)
        }
        if (normalized.any(::isForbiddenControlCharacter)) {
            return denied(ScannerAdmissionCode.DENY_CONTROL_CHARACTER)
        }

        val age = nowEpochMs - ingress.capturedAtEpochMs
        if (age > policy.maxAgeMs) {
            return denied(ScannerAdmissionCode.DENY_STALE)
        }
        if (age < -policy.maxFutureSkewMs) {
            return denied(ScannerAdmissionCode.DENY_FUTURE)
        }

        return ScannerAdmission(
            code = ScannerAdmissionCode.ACCEPT,
            scan = AcceptedScan(
                sourceEventId = ingress.sourceEventId,
                source = ingress.source,
                symbology = ingress.symbology,
                value = normalized,
                payloadHash = sha256(normalized),
                capturedAtEpochMs = ingress.capturedAtEpochMs,
            ),
        )
    }

    fun compare(
        existing: AcceptedScan?,
        incoming: AcceptedScan,
    ): ScannerReplayDisposition {
        if (existing == null || existing.sourceEventId != incoming.sourceEventId) {
            return ScannerReplayDisposition.NEW
        }
        return if (
            existing.payloadHash == incoming.payloadHash &&
            existing.source == incoming.source &&
            existing.symbology == incoming.symbology
        ) {
            ScannerReplayDisposition.EXACT_REPLAY
        } else {
            ScannerReplayDisposition.EVENT_ID_PAYLOAD_SUBSTITUTION
        }
    }

    private fun normalizePayload(value: String): String =
        value.trimEnd('\r', '\n')

    private fun isForbiddenControlCharacter(character: Char): Boolean =
        character.code < 32 && character != '\u001D'

    private fun denied(code: ScannerAdmissionCode) = ScannerAdmission(code)
}
