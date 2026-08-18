package com.eay.inventory

import com.eay.mobile.core.AcceptedScan
import com.eay.mobile.core.BlindCountLineEvidence
import java.math.BigDecimal
import java.util.UUID

data class InventoryCountEventContext(
    val missionId: String,
    val documentId: String,
    val activeShiftId: String,
    val attemptId: String,
    val leaseId: String,
    val locationId: String,
) {
    init {
        require(missionId.isNotBlank())
        UUID.fromString(documentId)
        require(activeShiftId.matches(Regex("^[A-Za-z0-9._:-]{1,128}$")))
        UUID.fromString(attemptId)
        UUID.fromString(leaseId)
        require(locationId.isNotBlank())
    }
}

/**
 * Converts one already-confirmed blind-count line into the immutable encrypted
 * queue contract. It does not grant authority and it does not accept raw scans;
 * callers must pass an AcceptedScan produced by ScannerIngressGuard.
 */
object InventoryCountEventFactory {
    fun create(
        context: InventoryCountEventContext,
        acceptedScan: AcceptedScan,
        evidence: BlindCountLineEvidence,
        deviceSequence: Long,
        eventId: String,
        occurredAt: String,
        authBindingId: String,
    ): OfflineEvent {
        require(context.missionId == evidence.missionId) {
            "blind-count evidence belongs to a different mission"
        }
        require(acceptedScan.payloadHash == evidence.itemPayloadHash) {
            "accepted scan does not match confirmed blind-count evidence"
        }
        require(deviceSequence > 0)
        require(authBindingId.isNotBlank())

        val normalizedEventId = UUID.fromString(eventId.trim()).toString()
        val canonicalBody = TerminalEventCanonical.body(
            TerminalEventInput(
                activeShiftId = context.activeShiftId,
                attemptId = context.attemptId,
                barcode = acceptedScan.value,
                deviceSequence = deviceSequence,
                documentId = context.documentId,
                eventId = normalizedEventId,
                leaseId = context.leaseId,
                locationId = context.locationId,
                occurredAt = occurredAt,
                quantity = BigDecimal.valueOf(evidence.quantity.toLong()),
                symbology = acceptedScan.symbology.name,
            ),
        )
        return OfflineEvent(
            eventId = normalizedEventId,
            deviceSequence = deviceSequence,
            canonicalPayload = canonicalBody,
            payloadHash = TerminalEventCanonical.hash(canonicalBody),
            authBindingId = authBindingId,
        )
    }
}
